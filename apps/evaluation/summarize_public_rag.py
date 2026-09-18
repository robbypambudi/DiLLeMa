"""Recompute paired uncertainty and source fingerprints for a completed run."""

import argparse
import hashlib
import json
from pathlib import Path

import numpy as np


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--results", type=Path, required=True)
    args = parser.parse_args()
    summary = json.loads((args.results / "summary.json").read_text())
    rows = [
        json.loads(line)
        for line in (args.results / "generation.jsonl").read_text().splitlines()
    ]
    grouped = {
        mode: {r["id"]: r for r in rows if r["mode"] == mode}
        for mode in summary["generation"]
    }
    rng = np.random.default_rng(summary["seed"])
    comparisons = {}
    for reference in ["closed_book", "dense_baseline", "oracle"]:
        current = grouped["current_production"]
        assert current.keys() == grouped[reference].keys()
        ids = sorted(current)
        samples = rng.integers(0, len(ids), size=(10000, len(ids)))
        comparisons[reference] = {}
        for metric in ["exact_match", "token_f1"]:
            differences = np.array(
                [current[i][metric] - grouped[reference][i][metric] for i in ids]
            )
            low, high = np.quantile(differences[samples].mean(1), [0.025, 0.975])
            comparisons[reference][metric] = {
                "difference": float(differences.mean()),
                "paired_bootstrap_95_ci": [float(low), float(high)],
                "resamples": 10000,
                "n": len(ids),
            }
    production = grouped["current_production"]
    supported = [r for r in production.values() if r["evidence_answer_hit"]]
    result = {
        "current_minus_reference": comparisons,
        "answer_present_but_not_exact": sum(not r["exact_match"] for r in supported),
        "answer_present_questions": len(supported),
        "note": "Bootstrap resamples questions, not article clusters; intervals are exploratory.",
    }
    (args.results / "analysis.json").write_text(json.dumps(result, indent=2))
    root = Path(__file__).resolve().parents[2]
    paths = [
        "apps/rag/nlp/doc_chunking.py",
        "apps/rag/nlp/doc_parse.py",
        "apps/rag/nlp/structure.py",
        "apps/rag/nlp/tables.py",
        "apps/rag/nlp/boilerplate.py",
        "apps/rag/nlp/tokens.py",
        "apps/rag/nlp/stemmer.py",
        "apps/rag/embedding/default_embedding.py",
        "apps/rag/embedding/sparse_bm25.py",
        "apps/rag/qdrant/client/__init__.py",
        "apps/rag/llm/re_rank.py",
        "apps/app/services/retrieval_service.py",
        "apps/evaluation/public_rag_eval.py",
        "apps/evaluation/rag_integrity_probes.py",
        "apps/evaluation/public_rag_controls.py",
    ]
    (args.results / "source-manifest.json").write_text(
        json.dumps(
            {
                name: hashlib.sha256((root / name).read_bytes()).hexdigest()
                for name in paths
            },
            indent=2,
        )
    )
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
