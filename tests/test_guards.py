"""Guards, model-free: the output Guards on saved results, and the repository
Guard on this repo and on planted files. Secrets and personal data used here
are built at run time and written only to temporary folders."""
import copy
import inspect
import json
import re
import subprocess
import sys
import tempfile
import unittest
from unittest import mock
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "guards"))

import cog_core       # noqa: E402
import repo_guard     # noqa: E402
import result_guard   # noqa: E402

FRAME_TEXT = (ROOT / "taxonomy" / "document-taxonomy.frame.md").read_text(encoding="utf-8")


def bundle():
    return json.loads((ROOT / "examples" / "sample-bundle.json").read_text(encoding="utf-8"))


def envelope():
    result = json.loads((ROOT / "examples" / "sample-result.json").read_text(encoding="utf-8"))
    return cog_core.finish(bundle(), result, {"kind": "test"})


def statuses(env, b=None):
    report = result_guard.run(b or bundle(), env, FRAME_TEXT)
    return report["status"], {r["guard"]: r["status"] for r in report["guards"]}


class OutputGuards(unittest.TestCase):
    def test_the_frame_and_the_code_name_the_same_guards(self):
        self.assertEqual(result_guard.frame_guards(FRAME_TEXT), list(result_guard.GUARDS))

    def test_cog_md_and_the_readme_list_the_frames_guards(self):
        for name in ("COG.md", "README.md"):
            with self.subTest(file=name):
                text = (ROOT / name).read_text(encoding="utf-8")
                listed = re.findall(r"^\| `([a-z]+(?:-[a-z]+)+)` \|", text, re.M)
                self.assertEqual(listed, result_guard.frame_guards(FRAME_TEXT))

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
                result = json.loads((ROOT / "examples" / "sample-result.json").read_text(encoding="utf-8"))
                env = cog_core.finish(b, result, {"kind": "test"})
                self.assertEqual(statuses(env, b)[0], "pass")

    def test_an_altered_document_id_is_checked(self):
        b = bundle()
        result = json.loads((ROOT / "examples" / "sample-result.json").read_text(encoding="utf-8"))
        env = cog_core.finish(b, result, {"kind": "test"})
        env["payload"]["decision"]["document_id"] = "jo" + "@" + "mailhost.co.uk"
        self.assertEqual(statuses(env, b)[1]["no-personal-identifiers"], "fail")

    def test_numbers_right_after_a_letter_or_punctuation_are_found(self):
        for text in ("Tel.020 " + "7946 0123", "Call(020) " + "7946 0123",
                     "ph-07911 " + "123456", "tel_07911 " + "123456"):
            with self.subTest(text=text):
                self.assertEqual(result_guard.personal_identifiers(text), ["phone number"])

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
        result = json.loads((ROOT / "examples" / "sample-result.json").read_text(encoding="utf-8"))
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
            b.write_text(json.dumps(bundle()), encoding="utf-8")
            e.write_text(json.dumps(envelope()), encoding="utf-8")
            self.assertEqual(result_guard.main(["--bundle", str(b), "--envelope", str(e)]), 0)
            bad = envelope()
            bad["payload"]["decision"]["tags"] = ["not_a_tag"]
            e.write_text(json.dumps(bad), encoding="utf-8")
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
                (Path(tmp) / name).write_text(text, encoding="utf-8")
            findings = repo_guard.scan(tmp, list(planted))
        self.assertEqual(len(findings), 4, findings)

    def test_personal_data_in_sample_data_is_found(self):
        with tempfile.TemporaryDirectory() as tmp:
            (Path(tmp) / "examples").mkdir()
            (Path(tmp) / "examples" / "doc.json").write_text('{"text": "mail ' + "jo" + "@" + 'mailhost.co.uk"}\n', encoding="utf-8")
            (Path(tmp) / "README.md").write_text("owner: " + "jo" + "@" + "mailhost.co.uk\n", encoding="utf-8")
            findings = repo_guard.scan(tmp, ["examples/doc.json", "README.md"])
        self.assertEqual(len(findings), 1, findings)
        self.assertIn("examples/doc.json", findings[0])

    def test_reserved_fictional_contacts_are_allowed_in_sample_data(self):
        allowed = ["a.person" + "@" + "example.com", "x" + "@" + "team.example.org", "+44 20 " + "7946 0123",
                   "0161 " + "496 0721", "07700 " + "900341", "(312) " + "555-0142", "+44 (0)20 " + "7946 0123",
                   "0114 " + "496 0555", "029 2018 " + "0123", "028 9649 " + "6001", "(440) " + "555-0123",
                   "+1 312 " + "555 0142", "0044 20 " + "7946 0123", "+44 20 " + "7946 0123 07700 900123"]
        flagged = ["a.person" + "@" + "realmail.co", "+44 20 " + "7123 4567", "(312) " + "555-7788",
                   "+44 20 " + "7946 0123 07123 456789",
                   "(07) " + "1555 0123", "+912 " + "555 0123",    # 555-01xx outside the US
                   "020 7946 " + "0123 999"]                        # a drama prefix with extra digits
        with tempfile.TemporaryDirectory() as tmp:
            (Path(tmp) / "benchmarks").mkdir()
            for i, text in enumerate(allowed + flagged):
                (Path(tmp) / "benchmarks" / f"d{i}.txt").write_text(f"contact {text}\n", encoding="utf-8")
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
            (Path(tmp) / "benchmarks" / "r\u00e9sum\u00e9 cv.txt").write_text("mail jo" + "@" + "mailhost.co.uk\n", encoding="utf-8")
            findings = repo_guard.scan(tmp, repo_guard.tracked_files(tmp))
        self.assertEqual(len(findings), 1, findings)
        self.assertIn("r\u00e9sum\u00e9 cv.txt", findings[0])

    def test_files_that_cannot_be_checked_are_reported_not_skipped(self):
        with tempfile.TemporaryDirectory() as tmp:
            (Path(tmp) / "benchmarks").mkdir()
            (Path(tmp) / "benchmarks" / "scan.txt").write_bytes(b"caf\xe9 owner\n")   # cp1252, not UTF-8
            (Path(tmp) / "logo.png").write_bytes(b"\x89PNG\r\n\x1a\n\xff\xfe")
            findings = repo_guard.scan(tmp, ["benchmarks/scan.txt", "logo.png", "benchmarks/missing.txt"])
        self.assertEqual(len(findings), 2, findings)
        self.assertIn("benchmarks/scan.txt: not UTF-8", findings[0])
        self.assertIn("benchmarks/missing.txt: can't be read", findings[1])

    def test_files_deleted_but_not_yet_committed_are_not_reported(self):
        with tempfile.TemporaryDirectory() as tmp:
            subprocess.run(["git", "init", "-q", tmp], check=True)
            (Path(tmp) / "old.md").write_text("old\n", encoding="utf-8")
            subprocess.run(["git", "-C", tmp, "add", "old.md"], check=True)
            (Path(tmp) / "old.md").unlink()
            files = repo_guard.tracked_files(tmp)
            self.assertNotIn("old.md", files)
            self.assertEqual(repo_guard.scan(tmp, files), [])

    def test_outside_git_the_listing_still_uses_forward_slashes(self):
        with tempfile.TemporaryDirectory() as tmp:
            (Path(tmp) / "benchmarks").mkdir()
            (Path(tmp) / "benchmarks" / "a.txt").write_text("x\n", encoding="utf-8")
            with mock.patch.object(repo_guard.subprocess, "run", side_effect=OSError("no git")):
                self.assertEqual(repo_guard.tracked_files(tmp), ["benchmarks/a.txt"])

    def test_new_files_are_scanned_before_they_are_committed(self):
        with tempfile.TemporaryDirectory() as tmp:
            subprocess.run(["git", "init", "-q", tmp], check=True)
            (Path(tmp) / ".gitignore").write_text("ignored/\n", encoding="utf-8")
            (Path(tmp) / "ignored").mkdir()
            (Path(tmp) / "ignored" / "secret.txt").write_text("x", encoding="utf-8")
            (Path(tmp) / "new.md").write_text("draft\n", encoding="utf-8")
            files = repo_guard.tracked_files(tmp)
        self.assertIn("new.md", files)
        self.assertNotIn("ignored/secret.txt", files)


if __name__ == "__main__":
    unittest.main()
