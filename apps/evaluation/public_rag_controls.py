"""Controlled missing-evidence tests for the small generator, not a retrieval test."""

import argparse
import json
from pathlib import Path

import numpy as np

from public_rag_eval import dataset, generate, normalize, torch


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dataset", type=Path, required=True)
    parser.add_argument("--results", type=Path, required=True)
    parser.add_argument("--questions", type=int, default=20)
    args = parser.parse_args()
    summary = json.loads((args.results / "summary.json").read_text())
    _, documents, selected = dataset(
        args.dataset, summary["seed"], summary["dev_n"], summary["test_n"]
    )
    retrieval = [
        json.loads(line)
        for line in (args.results / "retrieval.jsonl").read_text().splitlines()
    ]
    baseline = {
        r["id"]: r
        for r in retrieval
        if r["config"] == "fixed_800_120" and r["mode"] == "dense_leaf"
    }
    jobs = []
    for row in [r for r in selected if r["split"] == "test"]:
        aliases = [normalize(a) for a in row["answers"]["text"]]
        if any(len(a) < 5 for a in aliases):
            continue
        wrong_sources = list(dict.fromkeys(baseline[row["id"]]["source_ids"]))
        pairs = [
            [row["question"], documents[s]["context"], {"source_id": s}]
            for s in wrong_sources
            if s != row["source_id"]
            and not any(a in normalize(documents[s]["context"]) for a in aliases)
        ]
        if not pairs:
            continue
        for mode, evidence in [("distractor_context", pairs), ("empty_context", [])]:
            jobs.append(
                {
                    "id": row["id"],
                    "question": row["question"],
                    "mode": mode,
                    "answers": ["TIDAK DITEMUKAN"],
                    "original_answers": row["answers"]["text"],
                    "source_ids": [p[2]["source_id"] for p in evidence],
                    "pairs": evidence,
                }
            )
        if len(jobs) == args.questions * 2:
            break
    if len(jobs) != args.questions * 2:
        raise RuntimeError(
            "Insufficient eligible controls; no silent denominator change"
        )
    torch.set_num_threads(8)
    torch.manual_seed(summary["seed"])
    jobs = generate(jobs, batch_size=8, allow_closed_book=False)
    with (args.results / "missing-evidence.jsonl").open("w") as f:
        for job in jobs:
            f.write(json.dumps(job, ensure_ascii=False) + "\n")
    result = {
        mode: {
            "n": args.questions,
            "exact_abstention_rate": float(
                np.mean([j["abstained"] for j in jobs if j["mode"] == mode])
            ),
        }
        for mode in ["distractor_context", "empty_context"]
    }
    (args.results / "missing-evidence-summary.json").write_text(
        json.dumps(result, indent=2)
    )
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
