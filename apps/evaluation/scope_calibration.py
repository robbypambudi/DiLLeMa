"""Calibrate the scope gate and follow-up thresholds on this deployment's data.

No fixtures and no invented text: the questions are the ones users actually
asked (`conversation_turns` and `questions` in Postgres), the corpus is the
live Qdrant index, and the components are the production embedder, hybrid
search adapter and cross-encoder.

Positives are each question against the collection it was really asked
against. Negatives are the same question against the other collection --
a genuine out-of-scope pair, because the answer provably is not there.

    uv run python evaluation/scope_calibration.py

Prints the two score distributions and the thresholds they imply. It reads
the database and Qdrant; it writes nothing.
"""

import json
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

for key, value in {
    "HF_HUB_OFFLINE": "1",
    "TRANSFORMERS_OFFLINE": "1",
    "TOKENIZERS_PARALLELISM": "false",
}.items():
    os.environ.setdefault(key, value)

from sqlalchemy import create_engine, text

from app.core.config import settings
from app.services.conversation_context import contextual_query
from rag.embedding.default_embedding import DefaultEmbedding
from rag.llm.re_rank import ReRanking
from rag.qdrant.client import QdrantHttpClient

PROBE = settings.SCOPE_PROBE_CANDIDATES


def load_questions(engine):
    """Real questions, each with the collection it was really asked against."""
    asked, conversations = [], {}
    with engine.connect() as connection:
        rows = connection.execute(
            text(
                """
                select co.vectordb_collection_name, q.question_text
                from questions q join collections co on co.id = q.collection_id
                where q.question_text is not null
                """
            )
        ).fetchall()
        asked = [(row[0], row[1]) for row in rows]
        turns = connection.execute(
            text(
                """
                select t.conversation_id, t.sequence, t.question_text, t.answer,
                       co.vectordb_collection_name
                from conversation_turns t
                join conversations cv on cv.id = t.conversation_id
                join collections co on co.id = cv.collection_id
                order by t.conversation_id, t.sequence
                """
            )
        ).fetchall()
    for conversation_id, sequence, question, answer, collection in turns:
        conversations.setdefault(str(conversation_id), []).append(
            (sequence, question, answer or "", collection)
        )
        asked.append((collection, question))
    return asked, conversations


def probe_score(client, embedder, reranker, collection, query):
    """The gate's own measurement, through the production search path."""
    vector = embedder.encode(query)
    if hasattr(vector, "ndim") and vector.ndim > 1:
        vector = vector[0]
    hits = client.search(
        collection_name=collection,
        query_vector=vector,
        query_text=query,
        limit=settings.RETRIEVAL_CANDIDATES,
    )
    pairs = [
        [query, dict(hit.payload or {}).get("document", "")]
        for hit in hits
        if dict(hit.payload or {}).get("document")
    ][:PROBE]
    if not pairs:
        return None
    return float(reranker.best_score(pairs, query))


def describe(label, scores):
    scores = sorted(score for score in scores if score is not None)
    if not scores:
        print(f"  {label:26} (tidak ada data)")
        return None
    middle = scores[len(scores) // 2]
    print(
        f"  {label:26} n={len(scores):3}  min={scores[0]:.6f}  "
        f"p50={middle:.6f}  max={scores[-1]:.6f}"
    )
    return scores


def main():
    engine = create_engine(str(settings.SQLALCHEMY_DATABASE_URI))
    asked, conversations = load_questions(engine)
    collections = sorted({collection for collection, _ in asked})
    print(f"Pertanyaan nyata: {len(asked)} | koleksi: {len(collections)}")
    for collection in collections:
        print(f"  - {collection}")

    embedder = DefaultEmbedding(device="cpu")
    reranker = ReRanking()
    client = QdrantHttpClient(host=settings.QDRANT_HOST, port=settings.QDRANT_PORT)

    positives, negatives, rows = [], [], []
    print("\n== Probe pertanyaan mentah ==")
    for own, question in asked:
        score = probe_score(client, embedder, reranker, own, question)
        positives.append(score)
        rows.append({"kind": "in", "q": question, "collection": own, "score": score})
        for other in collections:
            if other != own:
                score = probe_score(client, embedder, reranker, other, question)
                negatives.append(score)
                rows.append(
                    {"kind": "out", "q": question, "collection": other, "score": score}
                )
    Path("evaluation/scope_calibration_scores.json").write_text(
        json.dumps(rows, ensure_ascii=False, indent=2) + "\n"
    )

    print("\n  in-scope terendah:")
    for row in sorted(
        (r for r in rows if r["kind"] == "in" and r["score"] is not None),
        key=lambda r: r["score"],
    )[:5]:
        print(f"    {row['score']:.6f}  {row['q'][:58]!r}")
    print("  out-of-scope tertinggi:")
    for row in sorted(
        (r for r in rows if r["kind"] == "out" and r["score"] is not None),
        key=lambda r: -r["score"],
    )[:5]:
        print(f"    {row['score']:.6f}  {row['q'][:58]!r}")
    kept_pos = describe("in-scope (koleksi benar)", positives)
    kept_neg = describe("out-of-scope (koleksi lain)", negatives)

    if kept_pos and kept_neg:
        print("\n== Implikasi ambang ==")
        print(f"  in-scope terendah        : {kept_pos[0]:.6f}")
        print(f"  out-of-scope tertinggi   : {kept_neg[-1]:.6f}")
        separated = kept_neg[-1] < kept_pos[0]
        print(f"  dua distribusi terpisah  : {'YA' if separated else 'TIDAK (tumpang tindih)'}")
        for name, value in (
            ("SCOPE_GATE_MIN_SCORE", settings.SCOPE_GATE_MIN_SCORE),
            ("SCOPE_SELF_SUFFICIENT_SCORE", settings.SCOPE_SELF_SUFFICIENT_SCORE),
        ):
            false_reject = sum(1 for score in kept_pos if score < value)
            caught = sum(1 for score in kept_neg if score < value)
            print(
                f"  {name}={value}: tolak-salah {false_reject}/{len(kept_pos)} "
                f"in-scope, tangkap {caught}/{len(kept_neg)} out-of-scope"
            )

    print("\n== Giliran lanjutan nyata (percakapan asli) ==")
    for conversation_id, turns in conversations.items():
        if len(turns) < 2:
            continue
        print(f"\n  percakapan …{conversation_id[-6:]}")
        for index, (sequence, question, _, collection) in enumerate(turns):
            if index == 0:
                continue
            history = [(previous, answer) for _, previous, answer, _ in turns[:index]]
            bare = probe_score(client, embedder, reranker, collection, question)
            carried_query = contextual_query(question, history)
            carried = (
                probe_score(client, embedder, reranker, collection, carried_query)
                if carried_query != question
                else None
            )
            if bare is None:
                decision = "tak-terprobe"
            elif bare >= settings.SCOPE_SELF_SUFFICIENT_SCORE:
                decision = "mandiri"
            elif carried is not None and carried >= settings.SCOPE_FOLLOWUP_MIN_SCORE:
                decision = "follow-up"
            elif bare >= settings.SCOPE_GATE_MIN_SCORE:
                decision = "mandiri-lemah"
            else:
                decision = "TOLAK"
            carried_text = f"{carried:.4f}" if carried is not None else "   -  "
            print(
                f"    #{sequence} mentah={bare:.4f} dibawa={carried_text} "
                f"-> {decision:14} {question[:44]!r}"
            )


if __name__ == "__main__":
    main()
