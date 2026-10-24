"""Document Classification task logic: the only file in src/ this Cog owns.

A System One model answers the typed questions in context/questions.json about
one document's text: which of six types it is, whether the text is legible,
who issued it, and one yes/no question per tag. This code turns those answers
into the classification, applying the policy in
taxonomy/document-taxonomy.frame.md:

- the type is the model's `document_type` choice when its confidence is at
  least MIN_TYPE_CONFIDENCE;
- low confidence, illegible or too little text, or contradicting answers send
  the document to review instead; a document in review gets no type, and every
  reason is stated;
- tags apply at TAG_THRESHOLD, and a type's own tags are reported only with
  that type.

Provisional: the input is the document's extracted text until extraction is
built (Phase 2), and the thresholds are placeholders until the benchmark sets
tune them.
"""
import re

# Placeholder thresholds (taxonomy/README.md). decide() is not told which model
# answered, so one set of thresholds applies to every provider for now.
MIN_TYPE_CONFIDENCE = 0.85
TAG_THRESHOLD = 0.7
MIN_LEGIBLE = 0.5
CONTRADICTION = 0.9         # a type tag this strong for another type contradicts the type
INVOICE_MIN_AMOUNTS = 0.3   # an invoice whose amounts answer is below this is suspect
MIN_WORDS = 20              # fewer words than this is too little text to classify

# Only these issue a bank statement (Frame: a bank, card issuer or payment provider).
BANK_ISSUER = "bank_or_card_issuer"
# Chinese, Japanese and Korean script, where each character counts as a word,
# since those languages don't put spaces between words.
CJK = re.compile(r"[぀-ヿ㐀-䶿一-鿿가-힯]")
WORD = re.compile(r"[^\W\d_]{2,}")  # two or more letters; numbers are not words

TAG_PREFIX = "tag_"
GENERAL_TAGS = ("contains_personal_data", "contains_financial_amounts", "time_sensitive",
                "signed", "draft_or_template", "multiple_documents", "non_english")
TYPE_TAGS = {
    "invoice": ("invoice_reminder", "invoice_credit_note"),
    "contract": ("contract_nda", "contract_employment", "contract_amendment"),
    "resume": (),
    "support_ticket": ("ticket_urgent", "ticket_complaint", "ticket_billing", "ticket_bug_report"),
    "bank_statement": (),
    "other": (),
}


def check_input(bundle):
    """Input checks beyond the input schema. An `error` refuses the run."""
    import cog_core
    problems = []
    if not str(bundle.get("text", "")).strip():
        problems.append(cog_core.problem("input", "text must contain more than whitespace"))
    return problems


def state(bundle):
    """Only the document's text. The caller's ID stays here, and the filename
    is never part of the input (Frame: Inputs)."""
    return {"text": bundle["text"]}


def questions(bundle, declared):
    return declared


def _probability(answers, tag):
    return answers[TAG_PREFIX + tag]["noul"]


def word_count(text):
    return len(WORD.findall(CJK.sub(" ", text))) + len(CJK.findall(text))


def decide(bundle, answers):
    answer = answers["document_type"]
    top, confidence = answer["choice"], answer["confidence"]
    flags, reasons = [], []

    if confidence < MIN_TYPE_CONFIDENCE:
        flags.append("low-confidence")
        reasons.append(f"type confidence {confidence:.2f} is below {MIN_TYPE_CONFIDENCE} (top type: {top})")
    legible = answers["text_legible"]["noul"]
    if legible < MIN_LEGIBLE:
        flags.append("illegible-text")
        reasons.append(f"text legibility {legible:.2f} is below {MIN_LEGIBLE}")
    words = word_count(bundle["text"])
    if words < MIN_WORDS:
        if "illegible-text" not in flags:
            flags.append("illegible-text")
        reasons.append(f"the text has {words} words, fewer than {MIN_WORDS}: too little to classify")
    issuer = answers["issuer"]["choice"]
    if top == "bank_statement" and issuer != BANK_ISSUER:
        flags.append("signals-disagree")
        reasons.append(f"the top type is bank_statement but the issuer is {issuer}")
    for other_type, tags in TYPE_TAGS.items():
        for tag in tags if other_type != top else ():
            if _probability(answers, tag) >= CONTRADICTION:
                if "signals-disagree" not in flags:
                    flags.append("signals-disagree")
                reasons.append(f"{tag} is {_probability(answers, tag):.2f} but the top type is {top}")
    amounts = _probability(answers, "contains_financial_amounts")
    if top == "invoice" and amounts < INVOICE_MIN_AMOUNTS:
        flags.append("invoice-without-amounts")
        reasons.append(f"top type is invoice but contains_financial_amounts is {amounts:.2f}")

    review = bool(flags)
    candidates = GENERAL_TAGS if review else GENERAL_TAGS + TYPE_TAGS[top]
    if not review:
        reasons.insert(0, f"document_type {top} (confidence {confidence:.2f})")
    return {"document_id": bundle["document_id"],
            "status": "needs_review" if review else "classified",
            "document_type": None if review else top,
            "confidence": confidence,
            "tags": [tag for tag in candidates if _probability(answers, tag) >= TAG_THRESHOLD],
            "flags": flags,
            "reasons": reasons}


def check_output(payload, bundle):
    """Contract checks, reported in `problems`. A document in review is also
    reported as a warning, so an Op's Gate passes it with problems rather than
    as clean."""
    import cog_core
    problems = []
    decision = payload["decision"]
    if decision["document_id"] != bundle["document_id"]:
        problems.append(cog_core.problem("consistency", "decision names a different document"))
    if decision["status"] == "classified" and decision["document_type"] is None:
        problems.append(cog_core.problem("consistency", "a classified document needs a type"))
    if decision["status"] == "needs_review":
        if decision["document_type"] is not None:
            problems.append(cog_core.problem("consistency", "a document in review must not get a type"))
        if not decision["flags"] or not decision["reasons"]:
            problems.append(cog_core.problem("consistency", "review needs a flag and a stated reason"))
        else:
            problems.append(cog_core.problem(
                "needs-review", "document needs review: " + "; ".join(decision["reasons"]), "warning"))
    return problems
