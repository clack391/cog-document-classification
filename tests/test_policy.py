"""Decision policy, model-free: each case edits the saved answers and checks
the decision code, not a model."""
import json
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

import cog_core      # noqa: E402
import task_logic    # noqa: E402

TYPES = ("invoice", "contract", "resume", "support_ticket", "other")


def bundle():
    return json.loads((ROOT / "examples" / "sample-bundle.json").read_text())


def result(top=None, confidence=None, **nouls):
    """The saved sample answers, with the top type, its confidence and any
    yes/no answers (by question id) replaced."""
    value = json.loads((ROOT / "examples" / "sample-result.json").read_text())
    answer = value["answers"]["document_type"]
    if top:
        answer["choice"] = top
        answer["probabilities"] = {t: (0.8 if t == top else 0.05) for t in TYPES}
    if confidence is not None:
        answer["confidence"] = confidence
    for qid, probability in nouls.items():
        value["answers"][qid]["noul"] = probability
    return value


def run(r):
    envelope = cog_core.finish(bundle(), r, {"kind": "test"})
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

    def test_a_tag_needs_the_tag_threshold(self):
        decision, _ = run(result(tag_signed=task_logic.TAG_THRESHOLD - 0.01))
        self.assertNotIn("signed", decision["tags"])
        decision, _ = run(result(tag_signed=task_logic.TAG_THRESHOLD))
        self.assertIn("signed", decision["tags"])


class NeedsReview(unittest.TestCase):
    def assert_review(self, r, flag):
        decision, problems = run(r)
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


if __name__ == "__main__":
    unittest.main()
