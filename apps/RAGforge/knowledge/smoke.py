"""Extract the fictional pilot using the configured live model, without a database."""

import argparse
import json
import time
from datetime import datetime, timezone
from pathlib import Path
from uuid import NAMESPACE_URL, uuid5

from knowledge.contracts import KnowledgeProfile, PIPELINE_VERSION
from knowledge.documents import chunks_fingerprint, parse_document, parser_provenance
from knowledge.extraction import ExtractionFailure, KnowledgeExtractor, PROMPT_VERSION


def check_expectations(results, expectations):
    """Deterministic checks for a small annotated smoke fixture, not a corpus eval."""
    checks = []
    for expected in expectations:
        matches = []
        for row in results:
            entities = {e["key"]: e for e in row["extraction"]["entities"]}
            for claim in row["extraction"]["claims"]:
                if (
                    claim["predicate"] == expected["predicate"]
                    and entities[claim["subject"]]["mention"] == expected["subject"]
                    and expected["object_contains"]
                    in entities[claim["object"]]["mention"]
                ):
                    matches.append(claim)
        qualifiers = expected.get("qualifiers", {})
        matched = any(
            all(
                claim["qualifiers"].get(key) == value
                for key, value in qualifiers.items()
            )
            for claim in matches
        )
        checks.append(
            {"id": expected["id"], "claim_found": bool(matches), "passed": matched}
        )
    return {"passed": all(check["passed"] for check in checks), "checks": checks}


def run(extractor, source, profile, max_chunks=200, expectations=None):
    """Return inspectable evidence; schema validity is not a quality benchmark."""
    started = time.monotonic()
    content_hash, chunks = parse_document(
        str(source), "", uuid5(NAMESPACE_URL, "dillema:knowledge:smoke"), max_chunks
    )
    results = []
    for chunk in chunks:
        result = extractor.extract(chunk, profile)
        results.append(
            {"chunk": chunk.model_dump(mode="json"), "extraction": result.model_dump()}
        )
    report = {
        "executed_at": datetime.now(timezone.utc).isoformat(),
        "validation": "schema_and_exact_source_evidence",
        "semantic_review_required": True,
        "pipeline": PIPELINE_VERSION,
        "prompt": PROMPT_VERSION,
        "model": extractor.model,
        "max_tokens": extractor.max_tokens,
        "output_format": getattr(extractor, "output_format", "text"),
        "source_sha256": content_hash,
        "parser": parser_provenance(str(source), ""),
        "chunks_fingerprint": chunks_fingerprint(chunks),
        "profile_revision": profile.revision,
        "elapsed_seconds": round(time.monotonic() - started, 3),
        "chunk_count": len(chunks),
        "claim_count": sum(len(row["extraction"]["claims"]) for row in results),
        "results": results,
    }
    if expectations is not None:
        report["fixture_check"] = check_expectations(results, expectations)
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    examples = Path(__file__).parent / "examples"
    parser.add_argument("--source", type=Path, default=examples / "pilot.txt")
    parser.add_argument(
        "--profile", type=Path, default=examples / "academic-profile.json"
    )
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--expectations", type=Path)
    args = parser.parse_args()

    # Runtime-only imports: importing smoke never loads credentials or a model.
    from app.core.config import settings
    from openai import OpenAI

    profile = KnowledgeProfile.model_validate_json(args.profile.read_text())
    expectations_path = args.expectations
    if expectations_path is None and args.source == examples / "pilot.txt":
        expectations_path = examples / "pilot.expected.json"
    expectations = (
        json.loads(expectations_path.read_text()) if expectations_path else None
    )
    try:
        with OpenAI(
            base_url=settings.KG_LLM_BASE_URL,
            api_key=settings.KG_LLM_API_KEY,
            timeout=120,
            max_retries=0,
        ) as client:
            report = run(
                KnowledgeExtractor(
                    client,
                    settings.KG_LLM_MODEL,
                    settings.KG_MAX_OUTPUT_TOKENS,
                    settings.KG_EXTRACTION_FORMAT,
                ),
                args.source,
                profile,
                settings.KG_MAX_CHUNKS,
                expectations,
            )
    except ExtractionFailure as exc:
        args.output.write_text(
            json.dumps(
                {
                    "status": "failed",
                    "prompt": PROMPT_VERSION,
                    "model": settings.KG_LLM_MODEL,
                    "output_format": settings.KG_EXTRACTION_FORMAT,
                    "attempts": exc.attempts,
                },
                ensure_ascii=False,
                indent=2,
            )
            + "\n",
            encoding="utf-8",
        )
        print(f"Live extraction failed validation. Inspect {args.output}.")
        return 1
    except Exception as exc:
        # Never print provider exceptions containing URLs or credentials.
        detail = str(exc) if isinstance(exc, ValueError) else type(exc).__name__
        print(f"Live extraction failed: {detail}")
        return 1
    args.output.write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(
        f"Validated {report['claim_count']} claims from {report['chunk_count']} chunks "
        f"in {report['elapsed_seconds']}s. Review evidence in {args.output}."
    )
    if not report.get("fixture_check", {}).get("passed", True):
        print(
            "Fixture coverage/qualifier checks failed; JSON validity alone is insufficient."
        )
        return 1
    return 0 if report["claim_count"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
