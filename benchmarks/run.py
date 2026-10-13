#!/usr/bin/env python3
"""Run the benchmark set through the Cog and save every result.

    pixi run python benchmarks/run.py live --name NAME
        Ask the live model through the Cog's ask-composed entry point.
        Needs a provider activated in cog-workbench (see docs/suite-notes.md).
    pixi run python benchmarks/run.py replay --answers DIR --name NAME
        Decide from saved answers: DIR holds one <id>.json per document, either
        a System One result or a saved envelope. No model is called.

Results go to benchmarks/results/NAME/, which Git ignores. That folder holds
one envelope per document, the Guards' report for it, and run.json. Score a
run with benchmarks/score.py.
"""
import argparse
import json
import subprocess
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import bench  # noqa: E402

sys.path.insert(0, str(bench.ROOT / "src"))
import cog_cli    # noqa: E402  (the Cog's own replay helpers)
import cog_core   # noqa: E402
result_guard = bench.result_guard

LIVE_TIMEOUT_S = 900


def failed_envelope(detail):
    """A complete envelope v1 for a document whose invocation failed."""
    return cog_core.envelope("decide", False, error={"code": "invocation-failed", "detail": str(detail)[:500]})


def live_invoke(row, document):
    """One live call through the same entry point a user runs."""
    with tempfile.TemporaryDirectory() as tmp:
        request = Path(tmp) / "bundle.json"
        request.write_text(json.dumps(document))
        call = subprocess.run([sys.executable, str(bench.ROOT / "scripts" / "composed_usage.py"),
                               "--request", str(request)], cwd=bench.ROOT, capture_output=True,
                              text=True, timeout=LIVE_TIMEOUT_S)
    try:
        value = json.loads(call.stdout)
    except ValueError:
        raise RuntimeError(f"no JSON from ask-composed (exit {call.returncode}): {call.stderr[-300:]}")
    if "envelope" not in value:
        raise RuntimeError(value.get("error") or f"ask-composed exited {call.returncode}")
    return value


def replay_invoker(answers_dir):
    answers_dir = Path(answers_dir)

    def invoke(row, document):
        saved = json.loads((answers_dir / f"{row['id']}.json").read_text())
        return cog_core.finish(document, cog_cli.saved_result(saved), cog_cli.replay_binding())
    return invoke


def run(rows, invoke, out_dir, mode, name):
    """Run every row, save its envelope and Guard report, and return run.json."""
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=False)
    summary = {"name": name, "mode": mode, "started_at": datetime.now(timezone.utc).isoformat(),
               "cog": dict(cog_core.SELF_ID), "fingerprints": bench.fingerprints(),
               "documents": 0, "failed": [], "guard_failures": [], "guard_warnings": [], "models": {}}
    for row in rows:
        document = bench.bundle(row)
        try:
            envelope = invoke(row, document)
        except Exception as exc:  # noqa: BLE001 - a failed document must not stop the run
            envelope = failed_envelope(f"{type(exc).__name__}: {exc}")
        report = result_guard.run(document, envelope)
        (out_dir / f"{row['id']}.json").write_text(json.dumps(envelope, indent=2))
        (out_dir / f"{row['id']}.guard.json").write_text(json.dumps(report, indent=2))
        summary["documents"] += 1
        if envelope.get("ok") is not True:
            summary["failed"].append(row["id"])
        elif report["status"] == "fail":
            summary["guard_failures"].append(row["id"])
        elif report["status"] == "warn":
            summary["guard_warnings"].append(row["id"])
        answered = ((envelope.get("payload") or {}).get("answered_by") or {})
        if answered:
            key = f"{answered.get('answer_source')}:{answered.get('model')}"
            summary["models"][key] = summary["models"].get(key, 0) + 1
    summary["finished_at"] = datetime.now(timezone.utc).isoformat()
    (out_dir / "run.json").write_text(json.dumps(summary, indent=2))
    return summary


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest="mode", required=True)
    live = sub.add_parser("live", help="ask the live model")
    live.add_argument("--name", required=True)
    replay = sub.add_parser("replay", help="decide from saved answers")
    replay.add_argument("--name", required=True)
    replay.add_argument("--answers", required=True)
    for p in (live, replay):
        p.add_argument("--results", default=str(bench.RESULTS), help="where run folders are written")
    args = parser.parse_args(argv)
    header, rows = bench.load_labels()
    problems = bench.validate(header, rows, bench.vocabulary())
    if problems:
        print("The labels have problems; fix them first:\n" + "\n".join(problems), file=sys.stderr)
        return 2
    out_dir = Path(args.results) / args.name
    if out_dir.exists():
        print(f"{out_dir} already exists; choose another --name", file=sys.stderr)
        return 2
    invoke = live_invoke if args.mode == "live" else replay_invoker(args.answers)
    summary = run(rows, invoke, out_dir, args.mode, args.name)
    print(json.dumps({k: summary[k] for k in ("name", "mode", "documents", "failed", "guard_failures", "models")}, indent=2))
    print(f"saved to {out_dir}; score it with: pixi run python benchmarks/score.py {out_dir}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
