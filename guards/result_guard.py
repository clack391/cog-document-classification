#!/usr/bin/env python3
"""Output Guards for the Document Classification Cog.

Independent checks on one classification result, as listed in the Guards
section of taxonomy/document-taxonomy.frame.md. They read the Frame, the input
bundle and the result envelope, and nothing from the Cog's own code, so they
verify the result instead of repeating the Cog's self-checks.

    python guards/result_guard.py --bundle BUNDLE.json --envelope ENVELOPE.json

Prints one JSON report. Exits 1 when any guard fails; a warning alone exits 0.
Standard library only, so it runs in any Python 3.11+ environment.
"""
import argparse
import copy
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
FRAME = ROOT / "taxonomy" / "document-taxonomy.frame.md"
QUOTE_WINDOW = 30   # characters of document text that count as a copied passage

EMAIL = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")
US_SSN = re.compile(r"\b\d{3}-\d{2}-\d{4}\b")
CARD = re.compile(r"\b\d(?:[ -]?\d){12,18}\b")
IBAN = re.compile(r"\b[A-Z]{2}\d{2}(?: ?[A-Z0-9]){11,30}\b")
PHONE = re.compile(r"\+?\(?\d[\d\s().-]{8,18}\d")
# Where a phone number can start: not inside another number, so not straight after
# a digit or +, or after a digit followed by - or . ("2026-0142"). After a letter
# or other punctuation is fine: "Tel.020 7946 0123", "Call(020) 7946 0123".
PHONE_START = re.compile(r"(?<![\d+])(?<!\d[.-])[+(]?\d")
# A money amount ("350.00", "-128.20", "1,020.00", "1020.00", "0.84"): digits, then
# exactly two decimals. Amounts never start with 0 except "0.xx", while phone numbers
# do ("06.12 34 56 78"); "312.555.0164" has more digits after its dot; and a group
# straight after a digit and a hyphen is part of a number ("06-12.34 56 78").
MONEY = re.compile(r"(?<![\w.,])(?<!\d-)(?:0|[1-9]\d{0,2}(?:,\d{3})+|[1-9]\d*)\.\d{2}(?![\w.])")


def _luhn(digits):
    total = 0
    for i, d in enumerate(reversed(digits)):
        n = int(d)
        if i % 2:
            n = n * 2 - 9 if n > 4 else n * 2
        total += n
    return total % 10 == 0


def _iban_valid(text):
    s = text.replace(" ", "")
    moved = s[4:] + s[:4]
    return int("".join(str(int(c, 36)) for c in moved)) % 97 == 1


def _phone_candidates(text):
    """Phone-like spans of 10 to 15 digits. A longer run that starts like a
    phone number (+, 0 or a bracket) is two numbers side by side, so it is
    split and each number is still found. Any other run is consumed whole,
    as before, so a spaced reference number is not mistaken for a phone."""
    pos = 0
    while True:
        start = PHONE_START.search(text, pos)
        if not start:
            return
        begin = start.start()
        match = PHONE.match(text, begin)
        if not match:
            pos = start.end()
            continue
        span, best_end = match.group(), None
        total = sum(ch.isdigit() for ch in span)
        if total <= 15:
            best_end = len(span) if total >= 10 else None
        elif span[:1] in "+0(":
            digits = 0
            for group in re.finditer(r"\S+", span):
                digits += sum(ch.isdigit() for ch in group.group())
                if digits > 15:
                    break
                if digits >= 10:
                    best_end = group.end()
        candidate = span[:best_end] if best_end else None
        if candidate and (candidate.startswith("+") or re.search(r"[\s().-]", candidate)):
            yield candidate
            pos = begin + best_end
        else:
            pos = begin + len(span)


def _without_amounts(text):
    """The text with every money amount blanked out, keeping its length, so
    columns of amounts are never read as phone or card numbers."""
    return MONEY.sub(lambda m: "#" * len(m.group()), text)


def identifier_matches(text):
    """(kind, matched text) for every personal identifier found. Pattern-based:
    it catches common formats, not every possible identifier."""
    found = [("email address", m.group()) for m in EMAIL.finditer(text)]
    found += [("US Social Security number", m.group()) for m in US_SSN.finditer(text)]
    numbers = _without_amounts(text)
    for m in CARD.finditer(numbers):
        digits = re.sub(r"\D", "", m.group())
        if 13 <= len(digits) <= 19 and _luhn(digits):
            found.append(("payment card number", m.group()))
    found += [("IBAN", m.group()) for m in IBAN.finditer(text) if _iban_valid(m.group())]
    found += [("phone number", c) for c in _phone_candidates(numbers)]
    return found


def personal_identifiers(text):
    """Names of the identifier kinds found in the text, each once. There is
    no way to relax this check: it guards a Cog's output."""
    kinds = []
    for kind, _ in identifier_matches(text):
        if kind not in kinds:
            kinds.append(kind)
    return kinds


def _section(text, title):
    match = re.search(rf"^## {title}\n(.*?)(?=^## |\Z)", text, re.S | re.M)
    if not match:
        raise ValueError(f"Frame has no '{title}' section")
    return match.group(1)


def frame_vocabulary(frame_text):
    """Types, tags and type-tag owners as the Frame states them."""
    types = re.findall(r"^- \*\*`([a-z_]+)`\*\*:", _section(frame_text, "Terminology"), re.M)
    vocabulary = _section(frame_text, "Tag Vocabulary")
    tags = re.findall(r"^\| `([a-z_]+)` \|", vocabulary, re.M)
    owners = dict(re.findall(r"^\| `([a-z_]+)` \| `([a-z_]+)` \|", vocabulary, re.M))
    return {"types": types, "tags": tags, "type_tags": owners}


def frame_guards(frame_text):
    """Guard names declared in the Frame's Guards table, in order."""
    return re.findall(r"^\| `([a-z-]+)` \|", _section(frame_text, "Guards"), re.M)


def _strings(value):
    if isinstance(value, str):
        yield value
    elif isinstance(value, dict):
        for item in value.values():
            yield from _strings(item)
    elif isinstance(value, list):
        for item in value:
            yield from _strings(item)


def _squash(text):
    return " ".join(text.split())


def _output_strings(bundle, envelope):
    """Everything the Cog produced: every string in the payload except the
    caller's own document_id, which is input echoed back, not model output.
    It is left out only when it equals the input's, so an altered one is checked."""
    payload = copy.deepcopy(envelope.get("payload")) or {}
    decision = payload.get("decision")
    if isinstance(decision, dict) and "document_id" in decision \
            and decision["document_id"] == bundle.get("document_id"):
        del decision["document_id"]
    return "\n".join(_strings(payload))


def no_document_text(bundle, envelope, vocab):
    document = _squash(str(bundle.get("text", "")))
    output = _squash(_output_strings(bundle, envelope))
    if len(document) < QUOTE_WINDOW:
        copied = len(document) >= 12 and document in output
    else:
        windows = {output[i:i + QUOTE_WINDOW] for i in range(len(output) - QUOTE_WINDOW + 1)}
        copied = any(document[i:i + QUOTE_WINDOW] in windows
                     for i in range(len(document) - QUOTE_WINDOW + 1))
    if copied:
        return "fail", f"the result repeats {QUOTE_WINDOW} or more characters of the document's text"
    return "pass", "no passage of the document appears in the result"


def no_personal_identifiers(bundle, envelope, vocab):
    found = personal_identifiers(_output_strings(bundle, envelope))
    if found:
        return "fail", "the result contains: " + ", ".join(found)
    return "pass", "no personal identifiers in the result"


def known_vocabulary(bundle, envelope, vocab):
    decision = (envelope.get("payload") or {}).get("decision") or {}
    kind, status, tags = decision.get("document_type"), decision.get("status"), decision.get("tags") or []
    issues = []
    if kind is not None and kind not in vocab["types"]:
        issues.append(f"type {kind!r} is not in the Frame")
    for tag in tags:
        if tag not in vocab["tags"]:
            issues.append(f"tag {tag!r} is not in the Frame")
        elif tag in vocab["type_tags"] and vocab["type_tags"][tag] != kind:
            issues.append(f"type tag {tag!r} reported with type {kind!r}")
    if status == "needs_review" and (kind is not None or not decision.get("reasons")):
        issues.append("a result in review must have no type and at least one reason")
    if status == "classified" and kind is None:
        issues.append("a classified result needs a type")
    if status not in ("classified", "needs_review"):
        issues.append(f"unknown status {status!r}")
    if issues:
        return "fail", "; ".join(issues)
    return "pass", "type, tags and status follow the Frame"


def review_is_visible(bundle, envelope, vocab):
    decision = (envelope.get("payload") or {}).get("decision") or {}
    if decision.get("status") != "needs_review":
        return "pass", "the result is not in review"
    warned = any(p.get("severity") in ("warning", "warn") for p in envelope.get("problems") or [])
    if warned:
        return "pass", "the review is reported as a warning"
    return "fail", "a result in review is not reported as a warning, so a workflow could pass it as clean"


def calibrated_answers(bundle, envelope, vocab):
    source = ((envelope.get("payload") or {}).get("answered_by") or {}).get("answer_source")
    if source == "system-one-model":
        return "pass", "answered by a System One model trained for calibration"
    return "warn", f"answer source is {source!r}: its confidence is not calibrated, so treat the threshold with care"


GUARDS = {
    "no-document-text": no_document_text,
    "no-personal-identifiers": no_personal_identifiers,
    "known-vocabulary": known_vocabulary,
    "review-is-visible": review_is_visible,
    "calibrated-answers": calibrated_answers,
}


def run(bundle, envelope, frame_text=None):
    frame_text = FRAME.read_text(encoding="utf-8") if frame_text is None else frame_text
    if not isinstance(envelope, dict) or envelope.get("ok") is not True or not envelope.get("payload"):
        results = [{"guard": "result-present", "status": "fail", "detail": "there is no successful result to check"}]
    else:
        vocab = frame_vocabulary(frame_text)
        results = []
        for name in frame_guards(frame_text):
            check = GUARDS.get(name)
            if check is None:
                results.append({"guard": name, "status": "fail", "detail": "the Frame names a guard that is not implemented"})
                continue
            status, detail = check(bundle, envelope, vocab)
            results.append({"guard": name, "status": status, "detail": detail})
    statuses = {r["status"] for r in results}
    overall = "fail" if "fail" in statuses else "warn" if "warn" in statuses else "pass"
    return {"status": overall, "guards": results}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--bundle", required=True, help="the input bundle the result was produced from")
    parser.add_argument("--envelope", required=True, help="the result envelope to check")
    parser.add_argument("--frame", default=str(FRAME), help="the taxonomy Frame (default: this repo's)")
    args = parser.parse_args(argv)
    report = run(json.loads(Path(args.bundle).read_text(encoding="utf-8")),
                 json.loads(Path(args.envelope).read_text(encoding="utf-8")),
                 Path(args.frame).read_text(encoding="utf-8"))
    print(json.dumps(report, indent=2))
    return 1 if report["status"] == "fail" else 0


if __name__ == "__main__":
    sys.exit(main())
