"""Guards, model-free: the output Guards on saved results, and the repository
Guard on this repo and on planted files. Secrets and personal data used here
are built at run time and written only to temporary folders."""
import copy
import inspect
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "guards"))

import cog_core       # noqa: E402
import repo_guard     # noqa: E402
import result_guard   # noqa: E402

FRAME_TEXT = (ROOT / "taxonomy" / "document-taxonomy.frame.md").read_text()


def bundle():
    return json.loads((ROOT / "examples" / "sample-bundle.json").read_text())


def envelope():
    result = json.loads((ROOT / "examples" / "sample-result.json").read_text())
    return cog_core.finish(bundle(), result, {"kind": "test"})


def statuses(env, b=None):
    report = result_guard.run(b or bundle(), env, FRAME_TEXT)
    return report["status"], {r["guard"]: r["status"] for r in report["guards"]}


class OutputGuards(unittest.TestCase):
    def test_the_frame_and_the_code_name_the_same_guards(self):
        self.assertEqual(result_guard.frame_guards(FRAME_TEXT), list(result_guard.GUARDS))

    def test_the_sample_result_passes_every_guard(self):
        overall, each = statuses(envelope())
        self.assertEqual(overall, "pass", each)

    def test_copied_document_text_fails(self):
        env = envelope()
        env["payload"]["decision"]["reasons"].append(bundle()["text"][20:80])
        self.assertEqual(statuses(env)[1]["no-document-text"], "fail")

    def test_personal_identifiers_fail(self):
        samples = {"email": "contact " + "jane.doe" + "@" + "example.org",
                   "card": "card 4111 1111 " + "1111 1111",
                   "ssn": "ssn 123-" + "45-6789",
                   "iban": "GB82 WEST 1234 " + "5698 7654 32",
                   "phone": "call +44 20 " + "7946 0958"}
        for name, text in samples.items():
            with self.subTest(identifier=name):
                env = envelope()
                env["payload"]["decision"]["reasons"].append(text)
                self.assertEqual(statuses(env)[1]["no-personal-identifiers"], "fail")

    def test_numbers_that_are_not_identifiers_pass(self):
        env = envelope()
        env["payload"]["decision"]["reasons"].append("doc-2026-0142 batch 1234 5678 9012 3456")
        self.assertEqual(statuses(env)[1]["no-personal-identifiers"], "pass")

    def test_the_callers_document_id_is_not_checked(self):
        for doc_id in ("2026-10-13-000123", "INV 2026 1014 7788", "jo" + "@" + "mailhost.co.uk"):
            with self.subTest(document_id=doc_id):
                b = dict(bundle(), document_id=doc_id)
                result = json.loads((ROOT / "examples" / "sample-result.json").read_text())
                env = cog_core.finish(b, result, {"kind": "test"})
                self.assertEqual(statuses(env, b)[0], "pass")

    def test_a_number_next_to_another_number_is_still_found(self):
        text = "call +44 20 " + "7123 4567 07700 " + "900123"
        self.assertEqual(result_guard.personal_identifiers(text), ["phone number"])
        self.assertEqual(result_guard.personal_identifiers("ref 2026 1014 " + "7788 1203 4455 6677"), [])

    def test_tags_and_types_outside_the_frame_fail(self):
        for change in ({"tags": ["not_a_tag"]}, {"document_type": "receipt"},
                       {"tags": ["ticket_urgent"]}):
            with self.subTest(change=change):
                env = envelope()
                env["payload"]["decision"].update(change)
                self.assertEqual(statuses(env)[1]["known-vocabulary"], "fail")

    def test_a_result_in_review_must_have_no_type(self):
        env = envelope()
        env["payload"]["decision"].update(status="needs_review", flags=["low-confidence"])
        self.assertEqual(statuses(env)[1]["known-vocabulary"], "fail")

    def test_review_must_be_reported_as_a_warning(self):
        env = envelope()
        env["payload"]["decision"].update(status="needs_review", document_type=None, tags=[],
                                          flags=["low-confidence"], reasons=["low confidence"])
        self.assertEqual(statuses(env)[1]["review-is-visible"], "fail")
        env["problems"] = [cog_core.problem("needs-review", "document needs review", "warning")]
        self.assertEqual(statuses(env)[1]["review-is-visible"], "pass")

    def test_the_real_review_path_passes_the_guards(self):
        result = json.loads((ROOT / "examples" / "sample-result.json").read_text())
        result["answers"]["document_type"]["confidence"] = 0.5
        overall, each = statuses(cog_core.finish(bundle(), result, {"kind": "test"}))
        self.assertEqual(overall, "pass", each)

    def test_llm_answers_only_warn(self):
        env = envelope()
        env["payload"]["answered_by"]["answer_source"] = "llm-adapter"
        overall, each = statuses(env)
        self.assertEqual((overall, each["calibrated-answers"]), ("warn", "warn"))

    def test_a_failed_invocation_fails(self):
        overall, _ = statuses({"ok": False, "payload": None, "problems": []})
        self.assertEqual(overall, "fail")

    def test_the_command_line_exit_code(self):
        with tempfile.TemporaryDirectory() as tmp:
            b, e = Path(tmp) / "bundle.json", Path(tmp) / "envelope.json"
            b.write_text(json.dumps(bundle()))
            e.write_text(json.dumps(envelope()))
            self.assertEqual(result_guard.main(["--bundle", str(b), "--envelope", str(e)]), 0)
            bad = envelope()
            bad["payload"]["decision"]["tags"] = ["not_a_tag"]
            e.write_text(json.dumps(bad))
            self.assertEqual(result_guard.main(["--bundle", str(b), "--envelope", str(e)]), 1)


class RepositoryGuard(unittest.TestCase):
    def test_this_repository_is_clean(self):
        self.assertEqual(repo_guard.scan(ROOT, repo_guard.tracked_files(ROOT)), [])

    def test_planted_secrets_are_found(self):
        planted = {"config.py": "API_KEY = '" + "a1b2c3d4" * 3 + "'\n",
                   "notes.md": "token " + "ghp_" + "x" * 36 + "\n",
                   "key.pem": "-----BEGIN " + "RSA PRIVATE KEY-----\n",
                   ".env": "ANYTHING=1\n"}
        with tempfile.TemporaryDirectory() as tmp:
            for name, text in planted.items():
                (Path(tmp) / name).write_text(text)
            findings = repo_guard.scan(tmp, list(planted))
        self.assertEqual(len(findings), 4, findings)

    def test_personal_data_in_sample_data_is_found(self):
        with tempfile.TemporaryDirectory() as tmp:
            (Path(tmp) / "examples").mkdir()
            (Path(tmp) / "examples" / "doc.json").write_text('{"text": "mail ' + "jo" + "@" + 'mailhost.co.uk"}\n')
            (Path(tmp) / "README.md").write_text("owner: " + "jo" + "@" + "mailhost.co.uk\n")
            findings = repo_guard.scan(tmp, ["examples/doc.json", "README.md"])
        self.assertEqual(len(findings), 1, findings)
        self.assertIn("examples/doc.json", findings[0])

    def test_reserved_fictional_contacts_are_allowed_in_sample_data(self):
        allowed = ["a.person" + "@" + "example.com", "x" + "@" + "team.example.org", "+44 20 " + "7946 0123",
                   "0161 " + "496 0721", "07700 " + "900341", "(312) " + "555-0142", "+44 (0)20 " + "7946 0123",
                   "0114 " + "496 0555", "029 2018 " + "0123", "028 9649 " + "6001", "(440) " + "555-0123",
                   "+1 312 " + "555 0142", "0044 20 " + "7946 0123", "+44 20 " + "7946 0123 07700 900123"]
        flagged = ["a.person" + "@" + "realmail.co", "+44 20 " + "7123 4567", "(312) " + "555-7788",
                   "+44 20 " + "7946 0123 07123 456789"]
        with tempfile.TemporaryDirectory() as tmp:
            (Path(tmp) / "benchmarks").mkdir()
            for i, text in enumerate(allowed + flagged):
                (Path(tmp) / "benchmarks" / f"d{i}.txt").write_text(f"contact {text}\n")
            names = [f"benchmarks/d{i}.txt" for i in range(len(allowed) + len(flagged))]
            findings = repo_guard.scan(tmp, names)
        flagged_files = sorted({f.split(":")[0] for f in findings})
        self.assertEqual(flagged_files, names[len(allowed):], findings)

    def test_the_output_guard_never_allows_fictional_contacts(self):
        self.assertEqual(result_guard.personal_identifiers("x" + "@" + "example.org"), ["email address"])
        self.assertEqual(result_guard.personal_identifiers("call 020 " + "7946 0123"), ["phone number"])
        self.assertEqual(list(inspect.signature(result_guard.personal_identifiers).parameters), ["text"],
                         "the output check must have no way to relax it")

    def test_files_with_accented_names_are_scanned(self):
        with tempfile.TemporaryDirectory() as tmp:
            subprocess.run(["git", "init", "-q", tmp], check=True)
            (Path(tmp) / "benchmarks").mkdir()
            (Path(tmp) / "benchmarks" / "r\u00e9sum\u00e9 cv.txt").write_text("mail jo" + "@" + "mailhost.co.uk\n")
            findings = repo_guard.scan(tmp, repo_guard.tracked_files(tmp))
        self.assertEqual(len(findings), 1, findings)
        self.assertIn("r\u00e9sum\u00e9 cv.txt", findings[0])

    def test_new_files_are_scanned_before_they_are_committed(self):
        with tempfile.TemporaryDirectory() as tmp:
            subprocess.run(["git", "init", "-q", tmp], check=True)
            (Path(tmp) / ".gitignore").write_text("ignored/\n")
            (Path(tmp) / "ignored").mkdir()
            (Path(tmp) / "ignored" / "secret.txt").write_text("x")
            (Path(tmp) / "new.md").write_text("draft\n")
            files = repo_guard.tracked_files(tmp)
        self.assertIn("new.md", files)
        self.assertNotIn("ignored/secret.txt", files)


if __name__ == "__main__":
    unittest.main()
