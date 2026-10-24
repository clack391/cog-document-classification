"""Decision policy, model-free: each case edits the saved answers and checks
the decision code, not a model."""
import json
import re
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

import cog_core      # noqa: E402
import task_logic    # noqa: E402

TYPES = ("invoice", "contract", "resume", "support_ticket", "bank_statement", "other")


def bundle():
    return json.loads((ROOT / "examples" / "sample-bundle.json").read_text(encoding="utf-8"))


ISSUERS = ("bank_or_card_issuer", "supplier_or_seller", "lender", "employer",
           "investment_or_pension_provider", "anyone_else")


def result(top=None, confidence=None, issuer=None, **nouls):
    """The saved sample answers, with the top type, its confidence, the issuer
    and any yes/no answers (by question id) replaced."""
    value = json.loads((ROOT / "examples" / "sample-result.json").read_text(encoding="utf-8"))
    answer = value["answers"]["document_type"]
    if top:
        answer["choice"] = top
        rest = round(0.2 / (len(TYPES) - 1), 6)
        answer["probabilities"] = {t: (0.8 if t == top else rest) for t in TYPES}
    if confidence is not None:
        answer["confidence"] = confidence
    if issuer:
        value["answers"]["issuer"].update(choice=issuer, confidence=0.88,
                                          probabilities={i: (0.9 if i == issuer else 0.02) for i in ISSUERS})
    for qid, probability in nouls.items():
        value["answers"][qid]["noul"] = probability
    return value


def run(r, text=None):
    document = bundle()
    if text is not None:
        document["text"] = text
    envelope = cog_core.finish(document, r, {"kind": "test"})
    assert envelope["ok"], envelope
    return envelope["payload"]["decision"], envelope["problems"]


class Classified(unittest.TestCase):
    def test_sample_invoice_is_classified_cleanly(self):
        decision, problems = run(result())
        self.assertEqual(problems, [])
        self.assertEqual((decision["status"], decision["document_type"]), ("classified", "invoice"))
        self.assertEqual(decision["tags"], ["contains_financial_amounts", "time_sensitive"])
        self.assertEqual(decision["flags"], [])

    def test_confidence_at_the_threshold_is_enough(self):
        decision, _ = run(result(confidence=task_logic.MIN_TYPE_CONFIDENCE))
        self.assertEqual(decision["status"], "classified")

    def test_a_type_tag_is_reported_only_with_its_own_type(self):
        decision, _ = run(result(top="support_ticket", tag_ticket_urgent=0.8,
                                 tag_invoice_reminder=0.8, tag_contains_financial_amounts=0.1))
        self.assertIn("ticket_urgent", decision["tags"])
        self.assertNotIn("invoice_reminder", decision["tags"])

    def test_a_bank_statement_is_classified_with_general_tags_only(self):
        decision, problems = run(result(top="bank_statement", issuer="bank_or_card_issuer",
                                        tag_contains_personal_data=0.9, tag_time_sensitive=0.1))
        self.assertEqual(problems, [])
        self.assertEqual((decision["status"], decision["document_type"]), ("classified", "bank_statement"))
        self.assertEqual(decision["tags"], ["contains_personal_data", "contains_financial_amounts"])

    def test_the_issuer_only_matters_for_a_bank_statement(self):
        decision, _ = run(result(top="other", issuer="lender"))
        self.assertEqual((decision["status"], decision["document_type"]), ("classified", "other"))

    def test_text_at_the_word_floor_is_enough(self):
        decision, _ = run(result(), text=" ".join(["word"] * task_logic.MIN_WORDS))
        self.assertEqual(decision["status"], "classified")

    def test_numbers_are_not_words_but_cjk_characters_are(self):
        self.assertEqual(task_logic.word_count("Page 2 of 2"), 2)
        self.assertEqual(task_logic.word_count("Total GBP 40.00, invoice 12"), 3)
        self.assertEqual(task_logic.word_count("这是一份合同"), 6)

    def test_a_tag_needs_the_tag_threshold(self):
        decision, _ = run(result(tag_signed=task_logic.TAG_THRESHOLD - 0.01))
        self.assertNotIn("signed", decision["tags"])
        decision, _ = run(result(tag_signed=task_logic.TAG_THRESHOLD))
        self.assertIn("signed", decision["tags"])


class NeedsReview(unittest.TestCase):
    def assert_review(self, r, flag, text=None):
        decision, problems = run(r, text)
        self.assertEqual(decision["status"], "needs_review")
        self.assertIsNone(decision["document_type"])
        self.assertIn(flag, decision["flags"])
        self.assertTrue(decision["reasons"])
        warnings = [p for p in problems if p["check"] == "needs-review"]
        self.assertEqual(len(warnings), 1)
        self.assertEqual(warnings[0]["severity"], "warning")
        self.assertFalse([p for p in problems if p["severity"] == "error"], problems)
        return decision

    def test_low_confidence(self):
        decision = self.assert_review(result(confidence=0.84), "low-confidence")
        self.assertEqual(decision["confidence"], 0.84)

    def test_illegible_text(self):
        self.assert_review(result(text_legible=0.2), "illegible-text")

    def test_too_little_text(self):
        decision = self.assert_review(result(), "illegible-text", text="Page 2 of 2")
        self.assertIn("2 words", decision["reasons"][0])
        self.assert_review(result(), "illegible-text", text=" ".join(["word"] * (task_logic.MIN_WORDS - 1)))

    def test_too_little_and_illegible_text_give_one_flag_and_both_reasons(self):
        decision = self.assert_review(result(text_legible=0.1), "illegible-text", text="Page 2 of 2")
        self.assertEqual(decision["flags"], ["illegible-text"])
        self.assertEqual(len(decision["reasons"]), 2)

    def test_a_bank_statement_from_someone_other_than_a_bank(self):
        for issuer in ISSUERS[1:]:
            with self.subTest(issuer=issuer):
                decision = self.assert_review(result(top="bank_statement", issuer=issuer), "signals-disagree")
                self.assertIn(f"the issuer is {issuer}", " ".join(decision["reasons"]))

    def test_a_strong_tag_for_another_type(self):
        self.assert_review(result(top="other", tag_contract_nda=0.95), "signals-disagree")

    def test_an_invoice_without_amounts(self):
        self.assert_review(result(tag_contains_financial_amounts=0.1), "invoice-without-amounts")

    def test_review_reports_general_tags_only(self):
        decision = self.assert_review(result(confidence=0.5, tag_invoice_reminder=0.9), "low-confidence")
        self.assertIn("contains_financial_amounts", decision["tags"])
        self.assertNotIn("invoice_reminder", decision["tags"])

    def test_every_reason_is_kept(self):
        decision = self.assert_review(result(confidence=0.5, text_legible=0.1), "low-confidence")
        self.assertEqual(decision["flags"], ["low-confidence", "illegible-text"])
        self.assertEqual(len(decision["reasons"]), 2)


class Inputs(unittest.TestCase):
    def test_only_the_text_is_sent_to_the_model(self):
        task = cog_core.prepare(bundle())["task"]
        self.assertEqual(task["state"], {"text": bundle()["text"]})

    def test_blank_text_is_refused(self):
        with self.assertRaises(ValueError):
            cog_core.prepare({"document_id": "doc-1", "text": "   \n "})


class ContractDocument(unittest.TestCase):
    def test_cog_md_states_the_thresholds_decide_uses(self):
        text = (ROOT / "COG.md").read_text(encoding="utf-8")
        stated = {name: float(value) for name, value in re.findall(r"`([A-Z_]+)` = ([0-9]+(?:\.[0-9]+)?)", text)}
        # Every threshold in the decision code, so one added only to the code fails too.
        used = {name: value for name, value in vars(task_logic).items()
                if name.isupper() and isinstance(value, (int, float)) and not isinstance(value, bool)}
        self.assertEqual(stated, used, "COG.md must state every threshold in src/task_logic.py, with its value")


if __name__ == "__main__":
    unittest.main()
