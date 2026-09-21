"""Measure retrieval against a golden set of question -> answer-page pairs.

Indexes each golden document into a throwaway Qdrant collection through the
same chunker and client the ingestion pipeline uses, then asks every question
through `RetrievalService` (hybrid search + rerank + page packing) and scores
the pages it would hand to the generator.

    uv run python evaluation/retrieval_eval.py --pdf-dir ~/Downloads

A page counts as correct when it lies in the question's range and its text
contains the answer string, so the ground truth is checked against the PDF
rather than typed in by hand.
"""

import argparse
import json
import re
import sys
import time
import unicodedata
from pathlib import Path
from types import SimpleNamespace
from uuid import uuid4

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.core.config import settings
from app.services.retrieval_service import RetrievalService
from rag.nlp.doc_chunking import DocumentChunker
from rag.nlp.doc_parse import read_sections
from rag.qdrant.client import QdrantHttpClient

POOL = settings.RETRIEVAL_CANDIDATES


def normalize(text: str) -> str:
    text = unicodedata.normalize("NFKD", text)
    text = "".join(char for char in text if not unicodedata.combining(char))
    return re.sub(r"\s+", " ", text).casefold()


def truth_pages(pdf: Path, question: dict) -> set[int]:
    import pymupdf

    first, last = question["range"]
    answer = normalize(question["answer"])
    with pymupdf.open(pdf) as document:
        pages = {
            number
            for number in range(first, last + 1)
            if answer in normalize(document[number - 1].get_text())
        }
    if not pages:
        raise SystemExit(
            f"answer {question['answer']!r} not found for {question['q']!r}"
        )
    return pages


def index(client, embedding, pdf: Path, collection: str, chunker) -> int:
    sections = read_sections(str(pdf), "application/pdf")
    chunks = chunker.chunk_sections(sections, file_name=pdf.name)
    file_id = str(uuid4())
    client.create_collection(collection, vector_size=embedding.vector_size)
    batch = 256
    for start in range(0, len(chunks), batch):
        part = chunks[start : start + batch]
        client.add_documents(
            collection_name=collection,
            ids=[f"{file_id}_{start + i}" for i in range(len(part))],
            documents=[item["text"] for item in part],
            metadatas=[
                {
                    **{key: value for key, value in item.items() if key != "text"},
                    "file_name": pdf.name,
                    "file_id": file_id,
                }
                for item in part
            ],
            embedding_function=embedding.encode,
        )
    return len(chunks)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--pdf-dir", type=Path)
    parser.add_argument(
        "--collection",
        action="append",
        default=[],
        metavar="DOC=NAME",
        help="score an already indexed collection instead of indexing its PDF",
    )
    parser.add_argument(
        "--golden",
        type=Path,
        default=Path(__file__).with_name("golden_retrieval.json"),
    )
    parser.add_argument("--label", default="run", help="name printed with the results")
    parser.add_argument("--out", type=Path, help="write per-question results as JSON")
    parser.add_argument("--keep", action="store_true", help="keep the eval collections")
    parser.add_argument(
        "--augment",
        action="store_true",
        help="rewrite each question with the LLM first (needs LLM_BASE_URL up)",
    )
    args = parser.parse_args()
    live = dict(item.split("=", 1) for item in args.collection)
    if not live and not args.pdf_dir:
        parser.error("pass --pdf-dir, or --collection DOC=NAME for a live index")

    golden = json.loads(args.golden.read_text())
    # Same host the application uses, so QDRANT_HOST points this at a live
    # deployment's index rather than only at a local one.
    client = QdrantHttpClient(host=settings.QDRANT_HOST, port=settings.QDRANT_PORT)
    augmenter = None
    if args.augment:
        from agents.augment_query_generated import AugmentQueryGenerated

        augmenter = AugmentQueryGenerated(api_key=None)
    retrieval = RetrievalService(None, client, augmenter)
    embedding = retrieval.embedding_model
    chunker = DocumentChunker()

    collections = dict(live)
    created = []
    for key, name in golden["documents"].items():
        if key in collections:
            print(f"scoring {name} against existing collection {collections[key]}")
            continue
        collection = f"eval_{key}_{uuid4().hex[:8]}"
        created.append(collection)
        started = time.time()
        count = index(client, embedding, args.pdf_dir / name, collection, chunker)
        print(f"indexed {name}: {count} chunks in {time.time() - started:.0f}s")
        collections[key] = collection

    rows = []
    try:
        for question in golden["questions"]:
            wanted = question.get("answers")
            truth = set()
            if not wanted:
                # Page truth is read from the PDF itself, so it needs one.
                if not args.pdf_dir:
                    print(f"skipped (needs --pdf-dir): {question['q']!r}")
                    continue
                truth = truth_pages(
                    args.pdf_dir / golden["documents"][question["doc"]], question
                )
            collection = collections[question["doc"]]
            retrieval.collections_repository = SimpleNamespace(
                read_by_id=lambda _id, c=collection: SimpleNamespace(
                    vectordb_collection_name=c
                )
            )
            query = question["q"]
            pool = client.search(
                collection,
                embedding.encode(query),
                limit=POOL,
                query_text=query,
            )
            pool_pages = [hit.payload.get("page") for hit in pool]
            payload = SimpleNamespace(
                collection_id=uuid4(),
                question_text=query,
                using_augment_query=args.augment,
            )
            packed = retrieval.retrieve(payload, using_augment_query=args.augment)
            if wanted:
                # A question asking for a set is scored on how much of that set
                # reached the generator, not on whether one page ranked first:
                # "apa saja mata kuliah semester 1" is wrong when it names four
                # of five, however confidently the four are cited.
                body = normalize(" ".join(pair[1] for pair in packed))
                found = [item for item in wanted if normalize(item) in body]
                rows.append(
                    {
                        "q": query,
                        "listing": True,
                        "wanted": len(wanted),
                        "found": len(found),
                        "missing": [i for i in wanted if i not in found],
                        "coverage": len(found) / len(wanted),
                        "pages": [pair[2].get("page") for pair in packed],
                    }
                )
                continue
            pages = [pair[2].get("page") for pair in packed]
            scores = [round(pair[2].get("rerank_score", 0.0), 4) for pair in packed]
            rank = next((i + 1 for i, page in enumerate(pages) if page in truth), None)
            rows.append(
                {
                    "q": query,
                    "truth": sorted(truth),
                    "pages": pages,
                    "scores": scores,
                    "hit1": rank == 1,
                    "hit_k": rank is not None,
                    "rr": 1 / rank if rank else 0.0,
                    "precision": (
                        sum(page in truth for page in pages) / len(pages)
                        if pages
                        else 0.0
                    ),
                    "pool_recall": any(page in truth for page in pool_pages),
                }
            )
    finally:
        # Only what this run indexed. A collection passed with --collection is
        # someone's live index and is never dropped by an evaluation.
        if not args.keep:
            for collection in created:
                client.delete_collection(collection)

    if not rows:
        raise SystemExit("no question could be scored")
    lookup = [row for row in rows if not row.get("listing")]
    listing = [row for row in rows if row.get("listing")]
    width = max(len(row["q"]) for row in rows)
    for row in lookup:
        mark = "OK " if row["hit1"] else ("~  " if row["hit_k"] else "MISS")
        print(f"{mark:4} {row['q']:<{width}}  truth={row['truth']} got={row['pages']}")
    for row in listing:
        mark = "OK " if row["coverage"] == 1 else ("~  " if row["coverage"] else "MISS")
        print(
            f"{mark:4} {row['q']:<{width}}  {row['found']}/{row['wanted']}"
            + (f"  belum: {row['missing']}" if row["missing"] else "")
        )

    summary = {"label": args.label, "questions": len(rows)}
    if lookup:
        count = len(lookup)
        summary.update(
            {
                "lookup_questions": count,
                f"pool_recall@{POOL}": sum(r["pool_recall"] for r in lookup) / count,
                "hit@1": sum(r["hit1"] for r in lookup) / count,
                "hit@packed": sum(r["hit_k"] for r in lookup) / count,
                "MRR": sum(r["rr"] for r in lookup) / count,
                "precision@packed": sum(r["precision"] for r in lookup) / count,
            }
        )
    if listing:
        # Coverage is averaged per question, and "complete" is the strict view:
        # a set answered four fifths is still an incomplete answer.
        summary.update(
            {
                "listing_questions": len(listing),
                "coverage": sum(r["coverage"] for r in listing) / len(listing),
                "complete": sum(r["coverage"] == 1 for r in listing) / len(listing),
            }
        )
    print(json.dumps(summary, indent=2))
    if args.out:
        args.out.write_text(json.dumps({"summary": summary, "rows": rows}, indent=2))


if __name__ == "__main__":
    main()
