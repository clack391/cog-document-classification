"""Shared helpers for the benchmark set: the labels, the documents, the targets,
and the Frame's vocabulary. Standard library only, plus the repo's Guards."""
import csv
import json
import re
import sys
from pathlib import Path

BENCH = Path(__file__).resolve().parent
ROOT = BENCH.parent
sys.path.insert(0, str(ROOT / "guards"))
import result_guard  # noqa: E402

LABELS = BENCH / "labels.csv"
TARGETS = BENCH / "targets.json"
RESULTS = BENCH / "results"
REVIEW = "needs_review"
COLUMNS = ["id", "file", "expected", "alternatives", "tags", "optional_tags",
           "frame_rule", "split", "source", "notes"]
LIST_COLUMNS = ("alternatives", "tags", "optional_tags")
SPLITS = ("tune", "test")
MIN_PER_TYPE = 2        # clear examples per type now; the plan grows this to 10-12

# Every rule in the taxonomy Frame that a document can exercise. Update this
# list when the Frame's rules change; the tests require at least one labeled
# document per rule.
REQUIRED_RULES = (
    # Type boundaries
    "bill-complaint", "invoice-under-contract", "letter-about-contract", "quote",
    "purchase-order", "policy", "job-description", "incident-report",
    # Borderline cases (confirmed 12 October 2026)
    "pro-forma-invoice", "credit-note", "receipt", "offer-letter", "contract-template",
    "terms-of-use", "cover-letter", "exported-profile", "sales-enquiry", "support-reply",
    # Bank statements (13 October 2026)
    "card-statement", "transaction-export", "bank-transaction-complaint",
    "supplier-statement", "loan-statement", "payslip",
    # More than one document, review, language
    "multiple-documents", "no-main-document", "garbled-text", "unclear-type", "non-english",
    # Hard cases that are still classifiable
    "ocr-noise",
)


def vocabulary():
    """Types and tags exactly as the Frame states them."""
    vocab = result_guard.frame_vocabulary(result_guard.FRAME.read_text())
    vocab["general_tags"] = [t for t in vocab["tags"] if t not in vocab["type_tags"]]
    return vocab


def split_cell(cell):
    return [part.strip() for part in (cell or "").split(";") if part.strip()]


def load_labels(path=LABELS):
    with open(path, newline="", encoding="utf-8") as handle:
        reader = csv.DictReader(handle)
        header = reader.fieldnames
        rows = [dict(row) for row in reader]
    for row in rows:
        for column in LIST_COLUMNS:
            row[column] = split_cell(row.get(column))
    return header, rows


def document_text(row, root=BENCH):
    return (root / row["file"]).read_text(encoding="utf-8")


def bundle(row, root=BENCH):
    """The Cog's input for one document. Only the text is sent to the model."""
    return {"document_id": row["id"], "text": document_text(row, root)}


def targets(path=TARGETS):
    return json.loads(Path(path).read_text())


def reportable_tags(vocab, document_type):
    """Tags the Cog may report for a result of this type (None means review)."""
    owned = [t for t, owner in vocab["type_tags"].items() if owner == document_type]
    return vocab["general_tags"] + owned


def validate(header, rows, vocab, root=BENCH):
    """Problems with the labels, as sentences. Empty means the set is usable."""
    problems = []
    if header != COLUMNS:
        problems.append(f"labels.csv columns must be exactly: {', '.join(COLUMNS)}")
        return problems
    types = vocab["types"]
    seen = set()
    for number, row in enumerate(rows, 2):
        where = f"labels.csv line {number} ({row['id'] or 'no id'})"
        if not re.fullmatch(r"[a-z0-9][a-z0-9-]*", row["id"] or ""):
            problems.append(f"{where}: id must be lowercase letters, digits and hyphens")
        if row["id"] in seen:
            problems.append(f"{where}: duplicate id")
        if row["id"] == "run" or row["id"].startswith("report"):
            problems.append(f"{where}: ids 'run' and 'report…' are reserved for a run's own files")
        seen.add(row["id"])
        path = (root / row["file"]).resolve()
        if not row["file"].startswith("documents/") or not path.is_relative_to((root / "documents").resolve()):
            problems.append(f"{where}: file must be under documents/")
        elif not path.is_file():
            problems.append(f"{where}: file {row['file']} does not exist")
        elif not path.read_text(encoding="utf-8").strip():
            problems.append(f"{where}: document is empty")
        expected = row["expected"]
        if expected not in types and expected != REVIEW:
            problems.append(f"{where}: expected {expected!r} is not a Frame type or {REVIEW}")
        for alt in row["alternatives"]:
            if alt not in types or alt == expected:
                problems.append(f"{where}: alternative {alt!r} must be another Frame type")
        unknown = [t for t in row["tags"] + row["optional_tags"] if t not in vocab["tags"]]
        if unknown:
            problems.append(f"{where}: tags not in the Frame: {unknown}")
        if set(row["tags"]) & set(row["optional_tags"]):
            problems.append(f"{where}: a tag can't be both expected and optional")
        allowed = reportable_tags(vocab, expected if expected != REVIEW else None)
        misplaced = [t for t in row["tags"] if t in vocab["tags"] and t not in allowed]
        if misplaced:
            problems.append(f"{where}: tags {misplaced} can't be reported for {expected!r}")
        if expected == "invoice" and "contains_financial_amounts" not in row["tags"]:
            problems.append(f"{where}: an invoice is expected to state amounts (the Frame sends one without amounts to review)")
        rule = row["frame_rule"]
        if rule.startswith("type:"):
            if rule[5:] not in types or rule[5:] != expected:
                problems.append(f"{where}: frame_rule {rule!r} must name the expected type")
        elif rule not in REQUIRED_RULES:
            problems.append(f"{where}: frame_rule {rule!r} is not in REQUIRED_RULES or type:<type>")
        if row["split"] not in SPLITS:
            problems.append(f"{where}: split must be tune or test")
        if row["source"] != "synthetic" and not row["source"].startswith("public:"):
            problems.append(f"{where}: source must be synthetic, or public:<licence>")
    rules = {row["frame_rule"] for row in rows}
    for rule in REQUIRED_RULES:
        if rule not in rules:
            problems.append(f"no document exercises the Frame rule {rule!r}")
    for kind in types:
        clear = sum(1 for row in rows if row["frame_rule"] == f"type:{kind}")
        if clear < MIN_PER_TYPE:
            problems.append(f"type {kind!r} has {clear} clear example(s); at least {MIN_PER_TYPE} are needed")
    for split in SPLITS:
        if not any(row["split"] == split for row in rows):
            problems.append(f"no documents in the {split} split")
    return problems


def main(argv=None):
    header, rows = load_labels()
    problems = validate(header, rows, vocabulary())
    for problem in problems:
        print(problem)
    counts = {}
    for row in rows:
        counts[row["expected"]] = counts.get(row["expected"], 0) + 1
    print(f"{len(rows)} documents: " + ", ".join(f"{k} {v}" for k, v in sorted(counts.items())))
    print("labels: " + ("OK" if not problems else f"{len(problems)} problem(s)"))
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
