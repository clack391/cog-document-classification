#!/usr/bin/env python3
"""Repository Guard: no credentials or real personal data are committed.

Two checks over every file in the repository except those Git ignores, so
new files are checked before they're committed:
- secrets: private keys, access tokens, API keys with a value, and .env files,
  in every text file;
- personal identifiers: email addresses, phone numbers, payment card numbers,
  IBANs and US Social Security numbers, in the sample, test and benchmark data,
  which must be synthetic. Contact details reserved for fiction are allowed
  there:
  - example.com, .org and .net emails;
  - the UK numbers Ofcom sets aside for drama;
  - US 555-0100 to 555-0199.

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
from result_guard import identifier_matches  # noqa: E402

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

# Reserved for fiction and documentation, so they never reach a real person:
# RFC 2606 and 6761 domains, Ofcom's drama number ranges, and US 555-01xx.
FICTIONAL_DOMAINS = ("example.com", "example.org", "example.net")
FICTIONAL_TLDS = (".example", ".test", ".invalid")
UK_DRAMA_PREFIXES = (
    "01134960", "01144960", "01154960", "01164960", "01174960", "01184960",   # 0113-0118 496 0xxx
    "01214960", "01314960", "01414960", "01514960", "01614960",               # 0121-0161 496 0xxx
    "01914980",                                                               # 0191 498 0xxx
    "02079460", "02896496", "02920180",                                       # London, Belfast, Cardiff
    "01632960", "07700900", "08081570", "09098790", "03069990",               # no area, mobile, freephone, premium, UK-wide
)


def fictional_email(address):
    domain = address.rsplit("@", 1)[-1].lower()
    return domain in FICTIONAL_DOMAINS or domain.endswith(FICTIONAL_TLDS) or \
        any(domain.endswith("." + d) for d in FICTIONAL_DOMAINS)


def fictional_phone(number):
    """True for a number reserved for fiction. Understands +44 and 0044,
    including the '+44 (0)20' style, and US numbers with or without +1."""
    text = number.strip()
    digits = re.sub(r"\D", "", text)
    if text.startswith(("+44", "0044")):
        digits = "0" + digits[4 if text.startswith("0044") else 2:].lstrip("0")
    if digits.startswith(UK_DRAMA_PREFIXES):
        return True
    if text.startswith("+1") or (len(digits) == 11 and digits.startswith("1")):
        digits = digits[1:]
    return len(digits) == 10 and digits[3:6] == "555" and digits[6:8] == "01"


def fictional(kind, value):
    if kind == "email address":
        return fictional_email(value)
    if kind == "phone number":
        return fictional_phone(value)
    return False


def tracked_files(root):
    """Every file Git doesn't ignore, tracked or new. NUL-separated, so names
    with accents or spaces arrive exactly as they are on disk."""
    try:
        out = subprocess.run(["git", "-C", str(root), "ls-files", "-z", "--cached", "--others",
                              "--exclude-standard"], capture_output=True, text=True, check=True).stdout
        return [f for f in out.split("\0") if f]
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
                reported = set()
                for kind, value in identifier_matches(line):
                    if kind in reported or fictional(kind, value):
                        continue
                    reported.add(kind)
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
