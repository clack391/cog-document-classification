#!/usr/bin/env python3
"""Repository Guard: no credentials or real personal data are committed.

Two checks over the files Git tracks:
- secrets: private keys, access tokens, API keys with a value, and .env files,
  in every text file;
- personal identifiers: email addresses, phone numbers, payment card numbers,
  IBANs and US Social Security numbers, in the sample and test data, which must
  be synthetic.

    python guards/repo_guard.py [--root PATH]

Prints each finding with its file and line, values masked, and exits 1 if
there is any. Standard library only.
"""
import argparse
import re
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from result_guard import personal_identifiers  # noqa: E402

SECRETS = {
    "private key": re.compile(r"-----BEGIN (?:[A-Z]+ )*PRIVATE KEY-----"),
    "GitHub token": re.compile(r"\bgh[pousr]_[A-Za-z0-9]{36,}\b"),
    "AWS access key": re.compile(r"\bAKIA[0-9A-Z]{16}\b"),
    "Anthropic or OpenAI key": re.compile(r"\bsk-(?:ant-)?[A-Za-z0-9_-]{20,}\b"),
    "credential with a value": re.compile(
        r"(?i)\b[\w-]*(?:api[_-]?key|secret|token|password)\s*[:=]\s*['\"]?[A-Za-z0-9_\-./+=]{16,}"),
}
DATA_DIRS = ("examples/", "tests/fixtures/", "benchmarks/")
DATA_FILES = ("context/output-example.json",)
SKIP = ("pixi.lock",)


def tracked_files(root):
    try:
        out = subprocess.run(["git", "-C", str(root), "ls-files"], capture_output=True, text=True, check=True).stdout
        return [f for f in out.splitlines() if f]
    except (OSError, subprocess.CalledProcessError):
        return [str(p.relative_to(root)) for p in Path(root).rglob("*")
                if p.is_file() and not {".git", ".pixi"} & set(p.relative_to(root).parts)]


def _mask(text):
    return text[:4] + "…" if len(text) > 4 else "…"


def scan(root, files):
    findings = []
    for name in files:
        if name in SKIP:
            continue
        if Path(name).name == ".env" or Path(name).name.startswith(".env."):
            findings.append(f"{name}: an environment file is committed")
            continue
        try:
            text = (Path(root) / name).read_text(encoding="utf-8")
        except (UnicodeDecodeError, OSError):
            continue
        is_data = name.startswith(DATA_DIRS) or name in DATA_FILES
        for number, line in enumerate(text.splitlines(), 1):
            for kind, pattern in SECRETS.items():
                match = pattern.search(line)
                if match:
                    findings.append(f"{name}:{number}: {kind} ({_mask(match.group())})")
            if is_data:
                for kind in personal_identifiers(line):
                    findings.append(f"{name}:{number}: {kind} in sample or test data")
    return findings


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--root", default=str(Path(__file__).resolve().parent.parent))
    args = parser.parse_args(argv)
    findings = scan(args.root, tracked_files(args.root))
    for finding in findings:
        print(finding)
    print("repo guard: " + ("FAIL, %d finding(s)" % len(findings) if findings else "PASS"))
    return 1 if findings else 0


if __name__ == "__main__":
    sys.exit(main())
