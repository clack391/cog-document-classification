"""The benchmark set and its tooling, model-free.

The scoring is tested with answers built from the labels ("oracle" answers),
then with deliberately wrong answers, and against hand-calculated numbers. No
model is called; live runs use the same code paths with real answers.
"""
import copy
import io
import json
import shutil
import sys
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
for folder in ("src", "guards", "benchmarks"):
    sys.path.insert(0, str(ROOT / folder))

import bench          # noqa: E402
import cog_core       # noqa: E402
import repo_guard     # noqa: E402
import run as bench_run    # noqa: E402
import score          # noqa: E402

VOCAB = bench.vocabulary()
HEADER, ROWS = bench.load_labels()
TYPES = VOCAB["types"]


def quietly(function, *args):
    """Run a command-line entry point without printing its report."""
    with redirect_stdout(io.StringIO()):
        return function(*args)


def oracle_result(row, top=None, probability=None):
    """A System One result that agrees with the labels. A document labeled for
    review gets an unsure answer. `top` and `probability` override the answer
    to the type question."""
    if top is None:
        top = row["expected"] if row["expected"] != bench.REVIEW else (row["alternatives"] or ["other"])[0]
    if probability is None:
        probability = 0.9 if row["expected"] != bench.REVIEW else 0.4
    rest = round((1 - probability) / (len(TYPES) - 1), 6)
    answers = {}
    for qid, question in cog_core.QUESTIONS.items():
        if question["type"] == "choice":
            confidence = round((probability - 1 / len(TYPES)) / (1 - 1 / len(TYPES)), 2)
            answers[qid] = {"type": "choice", "choice": top, "confidence": confidence,
                            "probabilities": {t: (probability if t == top else rest) for t in TYPES}}
        elif qid == "text_legible":
            answers[qid] = {"type": "noul", "noul": 0.1 if row["frame_rule"] == "garbled-text" else 0.95}
        else:
            answers[qid] = {"type": "noul", "noul": 0.9 if qid[len("tag_"):] in row["tags"] else 0.05}
    return {"model": "oracle", "answer_source": "system-one-model", "answers": answers,
            "usage": {"input_tokens": None, "output_tokens": None}}


class Workspace(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())

    def tearDown(self):
        shutil.rmtree(self.tmp)

    def run_with(self, results, name="run"):
        answers = self.tmp / f"answers-{name}"
        answers.mkdir()
        for row in ROWS:
            (answers / f"{row['id']}.json").write_text(json.dumps(results[row["id"]]))
        out = self.tmp / name
        bench_run.run(ROWS, bench_run.replay_invoker(answers), out, "replay", name)
        return out


class TheSet(unittest.TestCase):
    def test_the_labels_are_valid_and_cover_every_frame_rule(self):
        self.assertEqual(bench.validate(HEADER, ROWS, VOCAB), [])

    def test_every_document_is_accepted_by_the_cogs_input_contract(self):
        for row in ROWS:
            with self.subTest(document=row["id"]):
                prepared = cog_core.prepare(bench.bundle(row))
                self.assertEqual(prepared["task"]["state"], {"text": bench.document_text(row)})

    def test_both_splits_have_documents_and_review_cases(self):
        for split in bench.SPLITS:
            rows = [r for r in ROWS if r["split"] == split]
            self.assertGreater(len(rows), 0)
        self.assertGreaterEqual(sum(r["expected"] == bench.REVIEW for r in ROWS), 3)

    def test_the_targets_are_the_agreed_values(self):
        target = bench.targets()
        self.assertEqual((target["silent_error_rate_max"], target["review_rate_max"]), (0.02, 0.15))

    def test_the_benchmark_documents_hold_no_real_identifiers(self):
        files = [f"benchmarks/{r['file']}" for r in ROWS]
        self.assertEqual(repo_guard.scan(ROOT, files), [])


class Validation(unittest.TestCase):
    def broken(self, **change):
        rows = copy.deepcopy(ROWS)
        rows[0].update(change)
        return bench.validate(HEADER, rows, VOCAB)

    def test_bad_labels_are_reported(self):
        cases = {
            "tag": dict(tags=["not_a_tag"]),
            "type tag of another type": dict(tags=["contains_financial_amounts", "ticket_urgent"]),
            "invoice without amounts": dict(tags=["time_sensitive"]),
            "unknown type": dict(expected="receipt"),
            "missing file": dict(file="documents/does-not-exist.txt"),
            "file outside documents": dict(file="labels.csv"),
            "split": dict(split="train"),
            "source": dict(source="internet"),
            "reserved id": dict(id="report-1"),
            "rule": dict(frame_rule="made-up-rule"),
            "tag both expected and optional": dict(optional_tags=["time_sensitive"]),
        }
        for name, change in cases.items():
            with self.subTest(case=name):
                self.assertTrue(self.broken(**change), f"{name} was not caught")

    def test_duplicate_ids_and_missing_rules_are_reported(self):
        rows = copy.deepcopy(ROWS)
        rows[1]["id"] = rows[0]["id"]
        self.assertTrue(any("duplicate" in p for p in bench.validate(HEADER, rows, VOCAB)))
        rows = [r for r in copy.deepcopy(ROWS) if r["frame_rule"] != "payslip"]
        self.assertTrue(any("payslip" in p for p in bench.validate(HEADER, rows, VOCAB)))

    def test_wrong_columns_are_reported(self):
        self.assertTrue(bench.validate(HEADER[:-1], ROWS, VOCAB))


class Scoring(Workspace):
    def test_perfect_answers_score_perfectly(self):
        out = self.run_with({r["id"]: oracle_result(r) for r in ROWS})
        report = score.score(out)
        overall = report["overall"]
        reviews = sum(r["expected"] == bench.REVIEW for r in ROWS)
        self.assertEqual(overall["documents"], len(ROWS))
        self.assertEqual(overall["silent_errors"], [])
        self.assertEqual((overall["review"], overall["blocked"], overall["failed"]), (reviews, 0, 0))
        self.assertEqual(overall["unnecessary_reviews"], 0)
        self.assertEqual(overall["accuracy_when_classified"], 1.0)
        self.assertAlmostEqual(overall["review_rate"], reviews / len(ROWS))
        self.assertTrue(overall["meets_silent_error_target"] and overall["meets_review_rate_target"])
        self.assertEqual((report["tags"]["overall"]["precision"], report["tags"]["overall"]["recall"]), (1.0, 1.0))
        self.assertEqual(report["threshold_sweep"]["recommended"], 0.85)
        run_summary = json.loads((out / "run.json").read_text())
        self.assertEqual((run_summary["failed"], run_summary["guard_failures"]), ([], []))

    def test_confident_wrong_answers_are_silent_errors(self):
        results = {r["id"]: oracle_result(r) for r in ROWS}
        results["inv-standard"] = oracle_result(next(r for r in ROWS if r["id"] == "inv-standard"), top="other")
        unclear = next(r for r in ROWS if r["id"] == "unclear-attachment-note")
        results[unclear["id"]] = oracle_result(unclear, top="other", probability=0.95)
        overall = score.score(self.run_with(results))["overall"]
        self.assertEqual(sorted(overall["silent_errors"]), ["inv-standard", "unclear-attachment-note"])
        self.assertAlmostEqual(overall["silent_error_rate"], 2 / len(ROWS))
        self.assertFalse(overall["meets_silent_error_target"])

    def test_unsure_wrong_answers_go_to_review_instead(self):
        results = {r["id"]: oracle_result(r) for r in ROWS}
        results["inv-standard"] = oracle_result(next(r for r in ROWS if r["id"] == "inv-standard"),
                                                top="other", probability=0.5)
        report = score.score(self.run_with(results))
        self.assertEqual(report["overall"]["silent_errors"], [])
        self.assertEqual(report["by_document"]["inv-standard"]["judged"], "unnecessary_review")

    def test_the_sweep_finds_the_threshold_that_removes_silent_errors(self):
        results = {r["id"]: oracle_result(r) for r in ROWS}
        wrong = next(r for r in ROWS if r["id"] == "quote")
        results["quote"] = oracle_result(wrong, top="invoice", probability=0.75)   # confidence 0.70
        report = score.score(self.run_with(results))
        self.assertEqual(report["overall"]["silent_errors"], [])                # 0.70 < 0.85 already
        points = {p["threshold"]: p for p in report["threshold_sweep"]["points"]}
        self.assertEqual(points[0.6]["silent_errors"], 1)
        self.assertEqual(points[0.75]["silent_errors"], 0)
        rates = [p["review_rate"] for p in report["threshold_sweep"]["points"]]
        self.assertEqual(rates, sorted(rates), "review rate must not fall as the threshold rises")
        self.assertEqual(report["threshold_sweep"]["recommended"], 0.85)

    def test_alternatives_are_accepted(self):
        row = dict(next(r for r in ROWS if r["id"] == "quote"), alternatives=["invoice"])
        self.assertEqual(score.judge(row, "classified", "invoice"), "correct")
        review_row = dict(next(r for r in ROWS if r["expected"] == bench.REVIEW), alternatives=["other"])
        self.assertEqual(score.judge(review_row, "classified", "other"), "correct")
        self.assertEqual(score.judge(review_row, "classified", "invoice"), "silent_error")

    def test_failed_and_blocked_results_go_to_a_person_and_are_never_silent(self):
        results = {r["id"]: oracle_result(r) for r in ROWS}

        def invoke(row, document):
            if row["id"] == "receipt":
                raise RuntimeError("provider unavailable")
            envelope = bench_run.replay_invoker(answers)(row, document)
            if row["id"] == "payslip":
                envelope["payload"]["decision"]["tags"].append("not_a_tag")   # the known-vocabulary Guard fails
            return envelope
        answers = self.tmp / "answers"
        answers.mkdir()
        for row in ROWS:
            (answers / f"{row['id']}.json").write_text(json.dumps(results[row["id"]]))
        out = self.tmp / "run"
        summary = bench_run.run(ROWS, invoke, out, "replay", "run")
        self.assertEqual((summary["failed"], summary["guard_failures"]), (["receipt"], ["payslip"]))
        overall = score.score(out)["overall"]
        self.assertEqual((overall["failed"], overall["blocked"], overall["silent_errors"]), (1, 1, []))

    def test_a_split_scores_only_its_documents(self):
        out = self.run_with({r["id"]: oracle_result(r) for r in ROWS})
        test_rows = [r for r in ROWS if r["split"] == "test"]
        self.assertEqual(score.score(out, "test")["overall"]["documents"], len(test_rows))

    def test_calibration_with_known_answers(self):
        out = self.run_with({r["id"]: oracle_result(r) for r in ROWS})
        cal = score.score(out)["calibration"]
        typed = sum(r["expected"] != bench.REVIEW for r in ROWS)
        busy = [b for b in cal["bins"] if b["documents"]]
        self.assertEqual(len(busy), 1)
        self.assertEqual((busy[0]["from"], busy[0]["documents"], busy[0]["accuracy"]), (0.8, typed, 1.0))
        self.assertAlmostEqual(cal["expected_calibration_error"], 0.1)    # always right at probability 0.9

    def test_the_report_is_written_and_readable(self):
        out = self.run_with({r["id"]: oracle_result(r) for r in ROWS})
        self.assertEqual(quietly(score.main, [str(out)]), 0)
        text = (out / "report.md").read_text()
        self.assertIn("Silent error rate", text)
        self.assertIn("Recommended on this split: **0.85**", text)
        self.assertEqual(json.loads((out / "report.json").read_text())["overall"]["documents"], len(ROWS))
        self.assertEqual(quietly(score.main, [str(out), "--split", "tune"]), 0)
        self.assertTrue((out / "report-tune.md").exists())
        self.assertEqual(score.score(out)["overall"]["documents"], len(ROWS), "reports must not be read as results")


class Statistics(unittest.TestCase):
    def test_wilson_upper_bound(self):
        self.assertAlmostEqual(score.wilson_upper(0, 30), 3.8416 / 33.8416, places=4)
        self.assertAlmostEqual(score.wilson_upper(1, 10), 0.4042, places=3)
        self.assertIsNone(score.wilson_upper(0, 0))

    def test_outcomes(self):
        ok = {"ok": True, "payload": {"decision": {"status": "classified", "document_type": "invoice"}}}
        self.assertEqual(score.outcome(ok, {"status": "pass"}), ("classified", "invoice"))
        self.assertEqual(score.outcome(ok, {"status": "warn"}), ("classified", "invoice"))
        self.assertEqual(score.outcome(ok, {"status": "fail"}), ("blocked", None))
        self.assertEqual(score.outcome({"ok": False, "payload": None}, None), ("failed", None))

    def test_the_sweep_restores_the_real_threshold(self):
        before = score.task_logic.MIN_TYPE_CONFIDENCE
        with score.threshold(0.5):
            self.assertEqual(score.task_logic.MIN_TYPE_CONFIDENCE, 0.5)
        self.assertEqual(score.task_logic.MIN_TYPE_CONFIDENCE, before)


class Runner(Workspace):
    def test_a_run_never_overwrites_an_earlier_one(self):
        out = self.run_with({r["id"]: oracle_result(r) for r in ROWS})
        with self.assertRaises(FileExistsError):
            bench_run.run(ROWS, lambda row, doc: {}, out, "replay", "again")

    def test_the_command_line_end_to_end(self):
        answers = self.tmp / "answers"
        answers.mkdir()
        for row in ROWS:
            (answers / f"{row['id']}.json").write_text(json.dumps(oracle_result(row)))
        args = ["replay", "--answers", str(answers), "--name", "cli", "--results", str(self.tmp)]
        self.assertEqual(quietly(bench_run.main, args), 0)
        self.assertEqual(quietly(bench_run.main, args), 2, "an existing run name is refused")
        self.assertEqual(len(list((self.tmp / "cli").glob("*.guard.json"))), len(ROWS))

    def test_saved_envelopes_can_be_replayed(self):
        first = self.run_with({r["id"]: oracle_result(r) for r in ROWS}, "first")
        answers = self.tmp / "from-envelopes"
        answers.mkdir()
        for row in ROWS:
            shutil.copy(first / f"{row['id']}.json", answers / f"{row['id']}.json")
        second = self.tmp / "second"
        bench_run.run(ROWS, bench_run.replay_invoker(answers), second, "replay", "second")
        self.assertEqual(score.score(first)["overall"], score.score(second)["overall"])

    def test_live_mode_reports_a_missing_activation_as_a_failure(self):
        row = ROWS[0]
        with self.assertRaises(RuntimeError):
            bench_run.live_invoke(row, bench.bundle(row))


if __name__ == "__main__":
    unittest.main()
