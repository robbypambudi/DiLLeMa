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
    parser.add_argument("--pdf-dir", required=True, type=Path)
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

    golden = json.loads(args.golden.read_text())
    client = QdrantHttpClient()
    augmenter = None
    if args.augment:
        from agents.augment_query_generated import AugmentQueryGenerated

        augmenter = AugmentQueryGenerated(api_key=None)
    retrieval = RetrievalService(None, client, augmenter)
    embedding = retrieval.embedding_model
    chunker = DocumentChunker()

    collections = {}
    for key, name in golden["documents"].items():
        collection = f"eval_{key}_{uuid4().hex[:8]}"
        started = time.time()
        count = index(client, embedding, args.pdf_dir / name, collection, chunker)
        print(f"indexed {name}: {count} chunks in {time.time() - started:.0f}s")
        collections[key] = collection

    rows = []
    try:
        for question in golden["questions"]:
            pdf = args.pdf_dir / golden["documents"][question["doc"]]
            truth = truth_pages(pdf, question)
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
        if not args.keep:
            for collection in collections.values():
                client.delete_collection(collection)

    width = max(len(row["q"]) for row in rows)
    for row in rows:
        mark = "OK " if row["hit1"] else ("~  " if row["hit_k"] else "MISS")
        print(f"{mark:4} {row['q']:<{width}}  truth={row['truth']} got={row['pages']}")

    count = len(rows)
    summary = {
        "label": args.label,
        "questions": count,
        f"pool_recall@{POOL}": sum(r["pool_recall"] for r in rows) / count,
        "hit@1": sum(r["hit1"] for r in rows) / count,
        "hit@packed": sum(r["hit_k"] for r in rows) / count,
        "MRR": sum(r["rr"] for r in rows) / count,
        "precision@packed": sum(r["precision"] for r in rows) / count,
    }
    print(json.dumps(summary, indent=2))
    if args.out:
        args.out.write_text(json.dumps({"summary": summary, "rows": rows}, indent=2))


if __name__ == "__main__":
    main()
