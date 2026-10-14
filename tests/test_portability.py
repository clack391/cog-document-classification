"""Our code reads and writes files the same way on every platform. CI runs on
Linux and macOS only, so this catches what would break on Windows, where a
file opened without an encoding uses the local code page instead of UTF-8."""
import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
# Our own code. src/ and scripts/ come from Smith's starter templates, except
# the decision code.
OURS = [*ROOT.glob("guards/*.py"), *ROOT.glob("benchmarks/*.py"), *ROOT.glob("tests/*.py"),
        ROOT / "src" / "task_logic.py"]
CALL = re.compile(r"\.(read_text|write_text)\(|\bopen\(")


class Encodings(unittest.TestCase):
    def test_every_text_file_read_or_write_names_its_encoding(self):
        missing = []
        for path in OURS:
            for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
                if CALL.search(line) and "encoding=" not in line and "CALL" not in line:
                    missing.append(f"{path.relative_to(ROOT)}:{number}: {line.strip()}")
        self.assertEqual(missing, [], "add encoding=\"utf-8\"")


if __name__ == "__main__":
    unittest.main()
