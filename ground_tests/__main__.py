"""Run from repository root: python -m ground_tests --help."""

import argparse
from datetime import datetime, timezone
from pathlib import Path
import sys

from .protocol import DEFAULT_DATASET, ROOT, digest, load_dataset, provenance, read_json, source_fingerprint, write_json
from .reporting import END, START, compare, markdown, update_readme, validate_result
from .scoring import SCORER_VERSION, aggregate, score_case

SCOPE = "production-rag-stream/frozen-corpus/embedded-qdrant/empty-approved-graph-v1"
DEFAULT_LATEST = ROOT / "ground_tests/results/latest.json"
DEFAULT_BASELINE = ROOT / "ground_tests/baseline.json"


def parser():
    root = argparse.ArgumentParser(description="Ground-truth RAG evaluation with an explicit, fixed baseline")
    sub = root.add_subparsers(dest="command", required=True)
    run = sub.add_parser("run", help="Run real configured models; no production data is changed")
    run.add_argument("--dataset", type=Path, default=DEFAULT_DATASET)
    run.add_argument("--output", type=Path, default=DEFAULT_LATEST)
    run.add_argument("--baseline", type=Path, default=DEFAULT_BASELINE)
    run.add_argument("--repeats", type=int, default=3)
    run.add_argument("--timeout", type=float, default=120)
    run.add_argument("--no-augment", action="store_true")
    run.add_argument("--update-readme", action="store_true")
    run.add_argument("--max-drop", type=float, default=0.0)
    promote = sub.add_parser("baseline", help="Explicitly adopt a completed run as the fixed baseline")
    promote.add_argument("--result", type=Path, default=DEFAULT_LATEST)
    promote.add_argument("--output", type=Path, default=DEFAULT_BASELINE)
    promote.add_argument("--dataset", type=Path, default=DEFAULT_DATASET)
    promote.add_argument("--replace", action="store_true")
    promote.add_argument("--update-readme", action="store_true")
    verify = sub.add_parser("verify", help="CI gate: scores, dataset, code freshness, regression and README")
    verify.add_argument("--result", type=Path, default=DEFAULT_LATEST)
    verify.add_argument("--baseline", type=Path, default=DEFAULT_BASELINE)
    verify.add_argument("--dataset", type=Path, default=DEFAULT_DATASET)
    verify.add_argument("--max-drop", type=float, default=0.0)
    return root


def run(args):
    if not 1 <= args.repeats <= 20 or not 0 < args.timeout <= 600:
        raise ValueError("repeats must be 1–20; timeout must be 0–600 seconds")
    dataset = load_dataset(args.dataset)
    now = datetime.now(timezone.utc)
    result = {
        "run_id": now.strftime("%Y%m%dT%H%M%S%fZ"), "created_at": now.isoformat(),
        "dataset_id": dataset["id"], "dataset_sha256": digest(dataset),
        "scorer_version": SCORER_VERSION, "mode": "live", "scope": SCOPE,
        "status": "blocked", "repeats": args.repeats, "provenance": provenance(),
        "configuration": {}, "rows": [], "metrics": {},
    }
    runner = None
    try:
        # Keep import of dashboard configuration, credentials and model libraries
        # out of offline scorer tests and CI verification.
        sys.path.insert(0, str(ROOT / "apps"))
        from .live import LiveRunner
        runner = LiveRunner(dataset, augment=not args.no_augment, timeout=args.timeout)
        result["configuration"] = runner.configuration
        for repeat in range(args.repeats):
            for case in dataset["cases"]:
                print(f"[{repeat + 1}/{args.repeats}] {case['id']}", flush=True)
                prediction = runner.predict(case, repeat)
                result["rows"].append({"id": case["id"], "category": case["category"], "repeat": repeat,
                                       "prediction": prediction, "scores": score_case(case, prediction)})
                write_json(args.output, result)  # interrupted runs remain explicitly incomplete
        result["status"] = "complete"
        result["metrics"] = aggregate(result["rows"])
    except Exception as exc:
        result["error"] = f"{type(exc).__name__}: runtime initialization/evaluation failed; inspect local runtime prerequisites."
        print(result["error"], file=sys.stderr)
    finally:
        if runner:
            runner.close()
    if source_fingerprint() != result["provenance"]["source_sha256"]:
        result["status"] = "blocked"
        result["error"] = "Source code changed during evaluation; rerun against a stable working tree."
    write_json(args.output, result)
    write_json(args.output.parent / f"{result['run_id']}.json", result)
    baseline = read_json(args.baseline) if args.baseline.exists() else None
    if baseline:
        validate_result(baseline, dataset)
    if args.update_readme:
        update_readme(ROOT / "README.md", markdown(result, baseline, args.max_drop))
    if result["status"] != "complete":
        return 2
    validate_result(result, dataset)
    if result["metrics"]["error_rate"]["value"]:
        return 2
    if baseline:
        comparison = compare(result, baseline, args.max_drop)
        print(comparison["verdict"], comparison["deltas"])
        return int(bool(comparison["regressions"]))
    print("Run complete. No baseline yet; review results before running the baseline command.")
    return 0


def main():
    args = parser().parse_args()
    try:
        if args.command == "run":
            return run(args)
        dataset = load_dataset(args.dataset)
        result = read_json(args.result)
        validate_result(result, dataset)
        if result["metrics"]["error_rate"]["value"]:
            raise ValueError("Runs with request errors cannot pass the gate or become a baseline")
        if source_fingerprint() != result["provenance"]["source_sha256"]:
            raise ValueError("Stale result: RAG/evaluator source changed. Run ground_tests again.")
        if args.command == "baseline":
            if args.output.exists() and not args.replace:
                raise ValueError("Baseline exists; replacement requires explicit --replace after review")
            write_json(args.output, result)
            if args.update_readme:
                update_readme(ROOT / "README.md", markdown(result, result))
            print("Baseline saved. Future runs compare against this file; it is never auto-promoted.")
            return 0
        baseline = read_json(args.baseline)
        validate_result(baseline, dataset)
        comparison = compare(result, baseline, args.max_drop)
        expected = markdown(result, baseline, args.max_drop)
        readme = (ROOT / "README.md").read_text()
        if readme.count(START) != 1 or readme.count(END) != 1 or expected not in readme:
            raise ValueError("README report is stale; regenerate it with --update-readme")
        print(comparison["verdict"], comparison["deltas"])
        return int(bool(comparison["regressions"]))
    except (ValueError, KeyError, FileNotFoundError) as exc:
        print(f"Ground test rejected: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
