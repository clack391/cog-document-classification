#!/usr/bin/env python3
"""Score a benchmark run against the labels.

    pixi run python benchmarks/score.py benchmarks/results/NAME [--split tune|test|all]

Prints a summary and writes report.md and report.json into the run folder.

Each document's outcome is one of:
- classified: the Cog assigned a type;
- review: the Cog sent it to a person;
- blocked: a Guard failed, so the result is held for a person;
- failed: the invocation failed.

The headline number is the **silent error rate**: documents given a wrong type
without going to a person. The threshold sweep re-runs the Cog's own `decide`
on the saved answers at each threshold, so it shows exactly what the policy
would do. Pick thresholds on the tune split and report them on the test split.
"""
import argparse
import json
import math
import sys
from contextlib import contextmanager
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import bench  # noqa: E402

sys.path.insert(0, str(bench.ROOT / "src"))
import task_logic  # noqa: E402  (the Cog's real policy, for the threshold sweep)

SWEEP = [round(0.50 + 0.05 * i, 2) for i in range(10)]          # 0.50 .. 0.95
CONFIDENCE_BINS = [0.0, 0.5, 0.6, 0.7, 0.8, 0.9, 1.0000001]
PERSON = ("review", "blocked", "failed")


def wilson_upper(errors, n, z=1.96):
    """Upper end of the 95% Wilson interval for a rate. With few documents a
    zero count is not proof of a zero rate; this says how high it could be."""
    if n == 0:
        return None
    p = errors / n
    centre = p + z * z / (2 * n)
    margin = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n))
    return min(1.0, (centre + margin) / (1 + z * z / n))


def load_run(run_dir):
    run_dir = Path(run_dir)
    envelopes, guards = {}, {}
    for path in run_dir.glob("*.json"):
        if path.name == "run.json" or path.name.startswith("report") or path.name.endswith(".guard.json"):
            continue
        envelopes[path.stem] = json.loads(path.read_text())
        guard = run_dir / f"{path.stem}.guard.json"
        guards[path.stem] = json.loads(guard.read_text()) if guard.exists() else None
    return envelopes, guards


def outcome(envelope, guard):
    """(kind, type) for one result: kind is classified, review, blocked or failed."""
    if not envelope or envelope.get("ok") is not True or not envelope.get("payload"):
        return "failed", None
    if guard is not None and guard.get("status") == "fail":
        return "blocked", None
    decision = envelope["payload"]["decision"]
    if decision["status"] == "needs_review":
        return "review", None
    return "classified", decision["document_type"]


def judge(row, kind, kind_type):
    """correct, silent_error, or unnecessary_review for one document."""
    acceptable = ([row["expected"]] if row["expected"] != bench.REVIEW else []) + row["alternatives"]
    if kind == "classified":
        return "correct" if kind_type in acceptable else "silent_error"
    return "correct" if row["expected"] == bench.REVIEW else "unnecessary_review"


def _rate(part, whole):
    return part / whole if whole else None


def summarise(rows, outcomes, target):
    """The headline numbers for a set of rows and their (kind, type) outcomes."""
    n = len(rows)
    judged = [judge(row, *outcomes[row["id"]]) for row in rows]
    kinds = [outcomes[row["id"]][0] for row in rows]
    classified = kinds.count("classified")
    silent = [row["id"] for row, j in zip(rows, judged) if j == "silent_error"]
    to_person = sum(1 for k in kinds if k in PERSON)
    correct_classified = sum(1 for k, j in zip(kinds, judged) if k == "classified" and j == "correct")
    summary = {
        "documents": n,
        "classified": classified,
        "review": kinds.count("review"),
        "blocked": kinds.count("blocked"),
        "failed": kinds.count("failed"),
        "silent_errors": silent,
        "silent_error_rate": _rate(len(silent), n),
        "silent_error_rate_upper_95": wilson_upper(len(silent), n),
        "review_rate": _rate(to_person, n),
        "unnecessary_reviews": sum(1 for j in judged if j == "unnecessary_review"),
        "accuracy_when_classified": _rate(correct_classified, classified),
    }
    summary["meets_silent_error_target"] = (summary["silent_error_rate"] is not None
                                            and summary["silent_error_rate"] <= target["silent_error_rate_max"])
    summary["meets_review_rate_target"] = (summary["review_rate"] is not None
                                           and summary["review_rate"] <= target["review_rate_max"])
    return summary


def confusion(rows, outcomes, vocab):
    columns = vocab["types"] + list(PERSON)
    table = {}
    for row in rows:
        kind, kind_type = outcomes[row["id"]]
        column = kind_type if kind == "classified" else kind
        table.setdefault(row["expected"], {c: 0 for c in columns})[column] += 1
    return {"columns": columns, "rows": table}


def tag_scores(rows, envelopes, outcomes, vocab):
    """Per-tag precision and recall over the tags each result could report.
    Optional tags are never counted as right or wrong."""
    counts = {t: {"tp": 0, "fp": 0, "fn": 0} for t in vocab["tags"]}
    for row in rows:
        kind, kind_type = outcomes[row["id"]]
        if kind not in ("classified", "review"):
            continue
        predicted = set(envelopes[row["id"]]["payload"]["decision"]["tags"])
        reportable = set(bench.reportable_tags(vocab, kind_type))
        expected = set(row["tags"]) & reportable
        optional = set(row["optional_tags"])
        for tag in predicted & expected:
            counts[tag]["tp"] += 1
        for tag in predicted - expected - optional:
            counts[tag]["fp"] += 1
        for tag in expected - predicted:
            counts[tag]["fn"] += 1
    for c in counts.values():
        c["precision"] = _rate(c["tp"], c["tp"] + c["fp"])
        c["recall"] = _rate(c["tp"], c["tp"] + c["fn"])
    total = {k: sum(c[k] for c in counts.values()) for k in ("tp", "fp", "fn")}
    total["precision"] = _rate(total["tp"], total["tp"] + total["fp"])
    total["recall"] = _rate(total["tp"], total["tp"] + total["fn"])
    return {"per_tag": counts, "overall": total}


def calibration(rows, envelopes):
    """Is the model right as often as its confidence suggests? Uses the
    model's top type for documents that have a true type."""
    bins = [{"from": lo, "to": min(hi, 1.0), "documents": 0, "right": 0, "confidence_sum": 0.0, "probability_sum": 0.0}
            for lo, hi in zip(CONFIDENCE_BINS, CONFIDENCE_BINS[1:])]
    ece_terms, counted = 0.0, 0
    for row in rows:
        envelope = envelopes.get(row["id"])
        if row["expected"] == bench.REVIEW or not envelope or not envelope.get("payload"):
            continue
        answer = envelope["payload"]["answers"]["document_type"]
        right = answer["choice"] in [row["expected"]] + row["alternatives"]
        confidence, probability = answer["confidence"], answer["probabilities"][answer["choice"]]
        for b in bins:
            if b["from"] <= confidence < (b["to"] if b["to"] < 1.0 else 1.0000001):
                b["documents"] += 1
                b["right"] += right
                b["confidence_sum"] += confidence
                b["probability_sum"] += probability
                break
        counted += 1
    for b in bins:
        b["accuracy"] = _rate(b["right"], b["documents"])
        b["mean_confidence"] = _rate(b.pop("confidence_sum"), b["documents"])
        mean_probability = _rate(b.pop("probability_sum"), b["documents"])
        b["mean_top_probability"] = mean_probability
        if b["documents"]:
            ece_terms += b["documents"] * abs(b["accuracy"] - mean_probability)
    return {"bins": bins, "documents": counted,
            "expected_calibration_error": (ece_terms / counted) if counted else None}


@contextmanager
def threshold(value):
    saved = task_logic.MIN_TYPE_CONFIDENCE
    task_logic.MIN_TYPE_CONFIDENCE = value
    try:
        yield
    finally:
        task_logic.MIN_TYPE_CONFIDENCE = saved


def sweep(rows, envelopes, outcomes, target):
    """Silent error and review rates if MIN_TYPE_CONFIDENCE were each value.
    Blocked and failed documents stay with a person at every threshold."""
    points = []
    values = sorted(set(SWEEP + [task_logic.MIN_TYPE_CONFIDENCE]))
    for value in values:
        redone = {}
        with threshold(value):
            for row in rows:
                kind, kind_type = outcomes[row["id"]]
                if kind in ("blocked", "failed"):
                    redone[row["id"]] = (kind, None)
                    continue
                decision = task_logic.decide({"document_id": row["id"]}, envelopes[row["id"]]["payload"]["answers"])
                redone[row["id"]] = (("review", None) if decision["status"] == "needs_review"
                                     else ("classified", decision["document_type"]))
        s = summarise(rows, redone, target)
        points.append({"threshold": value, "silent_error_rate": s["silent_error_rate"], "review_rate": s["review_rate"],
                       "silent_errors": len(s["silent_errors"]), "meets_both_targets":
                       s["meets_silent_error_target"] and s["meets_review_rate_target"],
                       "meets_silent_error_target": s["meets_silent_error_target"]})
    safe = [p for p in points if p["meets_silent_error_target"]]
    pick = min(safe, key=lambda p: (p["review_rate"], -p["threshold"])) if safe else None
    return {"points": points, "current": task_logic.MIN_TYPE_CONFIDENCE,
            "recommended": pick["threshold"] if pick else None,
            "recommended_meets_review_target": pick["meets_both_targets"] if pick else False}


def score(run_dir, split="all", labels_path=bench.LABELS):
    header, rows = bench.load_labels(labels_path)
    vocab = bench.vocabulary()
    target = bench.targets()
    if split != "all":
        rows = [row for row in rows if row["split"] == split]
    envelopes, guards = load_run(run_dir)
    missing = [row["id"] for row in rows if row["id"] not in envelopes]
    rows = [row for row in rows if row["id"] in envelopes]
    outcomes = {row["id"]: outcome(envelopes[row["id"]], guards[row["id"]]) for row in rows}
    groups = {}
    for row in rows:
        answered = ((envelopes[row["id"]].get("payload") or {}).get("answered_by") or {})
        key = f"{answered.get('answer_source', 'none')}:{answered.get('model', 'none')}"
        groups.setdefault(key, []).append(row)
    report = {"run": str(run_dir), "split": split, "targets": target, "missing": missing,
              "overall": summarise(rows, outcomes, target),
              "per_model": {k: summarise(v, outcomes, target) for k, v in groups.items()},
              "per_type": {}, "confusion": confusion(rows, outcomes, vocab),
              "tags": tag_scores(rows, envelopes, outcomes, vocab),
              "calibration": calibration(rows, envelopes),
              "threshold_sweep": sweep(rows, envelopes, outcomes, target)}
    for kind in vocab["types"] + [bench.REVIEW]:
        subset = [row for row in rows if row["expected"] == kind]
        if subset:
            report["per_type"][kind] = summarise(subset, outcomes, target)
    report["by_document"] = {row["id"]: {"expected": row["expected"], "outcome": outcomes[row["id"]][0],
                                         "type": outcomes[row["id"]][1],
                                         "judged": judge(row, *outcomes[row["id"]]),
                                         "frame_rule": row["frame_rule"]} for row in rows}
    return report


def _pct(value):
    return "n/a" if value is None else f"{100 * value:.1f}%"


def markdown(report):
    o, t, s = report["overall"], report["targets"], report["threshold_sweep"]
    ok = lambda flag: "meets target" if flag else "**misses target**"  # noqa: E731
    lines = [f"# Benchmark report: {Path(report['run']).name} ({report['split']} split)", "",
             f"{o['documents']} documents scored. " + (f"Not in this run: {', '.join(report['missing'])}." if report["missing"] else ""), "",
             "## Headline", "",
             "| Measure | Value | Target |", "|---|---|---|",
             f"| Silent error rate (wrong type, no review) | {_pct(o['silent_error_rate'])} "
             f"({len(o['silent_errors'])} of {o['documents']}; could be as high as {_pct(o['silent_error_rate_upper_95'])}) "
             f"| ≤ {_pct(t['silent_error_rate_max'])}: {ok(o['meets_silent_error_target'])} |",
             f"| Sent to a person (review, blocked, failed) | {_pct(o['review_rate'])} "
             f"| ≤ {_pct(t['review_rate_max'])}: {ok(o['meets_review_rate_target'])} |",
             f"| Accuracy when the Cog assigned a type | {_pct(o['accuracy_when_classified'])} | |",
             f"| Unnecessary reviews (clear documents sent to a person) | {o['unnecessary_reviews']} | |", ""]
    if o["silent_errors"]:
        lines += ["Silent errors: " + ", ".join(o["silent_errors"]), ""]
    lines += ["## Threshold sweep", "",
              f"Current `MIN_TYPE_CONFIDENCE`: {s['current']}. "
              + (f"Recommended on this split: **{s['recommended']}** (lowest review rate that meets the silent error target"
                 + ("" if s["recommended_meets_review_target"] else "; it still misses the review target") + ")."
                 if s["recommended"] is not None else "**No threshold meets the silent error target.**"), "",
              "| Threshold | Silent errors | Silent error rate | Sent to a person |", "|---|---|---|---|"]
    lines += [f"| {p['threshold']:.2f} | {p['silent_errors']} | {_pct(p['silent_error_rate'])} | {_pct(p['review_rate'])} |"
              for p in s["points"]]
    lines += ["", "## By expected type", "", "| Expected | Documents | Classified | Silent errors | Sent to a person |", "|---|---|---|---|---|"]
    for kind, v in report["per_type"].items():
        lines.append(f"| {kind} | {v['documents']} | {v['classified']} | {len(v['silent_errors'])} | {_pct(v['review_rate'])} |")
    c = report["confusion"]
    lines += ["", "## Confusion (rows: expected; columns: outcome)", "",
              "| Expected | " + " | ".join(c["columns"]) + " |", "|---|" + "---|" * len(c["columns"])]
    for expected, cells in c["rows"].items():
        lines.append(f"| {expected} | " + " | ".join(str(cells[col]) for col in c["columns"]) + " |")
    tg = report["tags"]
    lines += ["", "## Tags", "",
              f"Overall: precision {_pct(tg['overall']['precision'])}, recall {_pct(tg['overall']['recall'])}.", "",
              "| Tag | Right | Wrongly added | Missed | Precision | Recall |", "|---|---|---|---|---|---|"]
    for tag, v in tg["per_tag"].items():
        if v["tp"] or v["fp"] or v["fn"]:
            lines.append(f"| {tag} | {v['tp']} | {v['fp']} | {v['fn']} | {_pct(v['precision'])} | {_pct(v['recall'])} |")
    cal = report["calibration"]
    lines += ["", "## Calibration of the type answer", "",
              f"Expected calibration error (top probability against accuracy): "
              f"{_pct(cal['expected_calibration_error'])} over {cal['documents']} documents.", "",
              "| Confidence | Documents | Right | Mean confidence | Mean top probability |", "|---|---|---|---|---|"]
    for b in cal["bins"]:
        if b["documents"]:
            lines.append(f"| {b['from']:.1f}–{b['to']:.1f} | {b['documents']} | {_pct(b['accuracy'])} | "
                         f"{b['mean_confidence']:.2f} | {b['mean_top_probability']:.2f} |")
    if len(report["per_model"]) > 1:
        lines += ["", "## By model", "", "| Model | Documents | Silent error rate | Sent to a person |", "|---|---|---|---|"]
        for key, v in report["per_model"].items():
            lines.append(f"| {key} | {v['documents']} | {_pct(v['silent_error_rate'])} | {_pct(v['review_rate'])} |")
    return "\n".join(lines) + "\n"


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("run_dir")
    parser.add_argument("--split", choices=["tune", "test", "all"], default="all")
    args = parser.parse_args(argv)
    report = score(args.run_dir, args.split)
    run_dir = Path(args.run_dir)
    suffix = "" if args.split == "all" else f"-{args.split}"
    (run_dir / f"report{suffix}.json").write_text(json.dumps(report, indent=2))
    text = markdown(report)
    (run_dir / f"report{suffix}.md").write_text(text)
    print(text)
    return 0


if __name__ == "__main__":
    sys.exit(main())
