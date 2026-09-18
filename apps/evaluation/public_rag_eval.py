"""Reproducible Indonesian RAG ablation on TyDi QA, without application data.

Uses the production chunker, embedding adapter, sparse encoder, Qdrant adapter,
reranker and RetrievalService. Qdrant runs in memory (not an ANN/server benchmark).
See README.md for the pinned dataset download and experiment limitations.
"""

import argparse
from collections import Counter
from datetime import datetime, timezone
import gc
import hashlib
import importlib.metadata
import json
import os
from pathlib import Path
import platform
import random
import re
import sys
import time
from types import SimpleNamespace
from uuid import NAMESPACE_URL, uuid5

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

# Experiments must not inherit database/model/feature choices from apps/.env.
for key, value in {
    "POSTGRES_SERVER": "localhost",
    "POSTGRES_USER": "evaluation",
    "POSTGRES_DB": "evaluation",
    "KG_ENABLED": "false",
    "QUERY_AUGMENTATION": "false",
    "BM25_STEMMING": "true",
    "HF_HUB_OFFLINE": "1",
    "TRANSFORMERS_OFFLINE": "1",
    "TOKENIZERS_PARALLELISM": "false",
}.items():
    os.environ[key] = value

import numpy as np
import pyarrow.parquet as pq
import torch
from loguru import logger
from qdrant_client import QdrantClient

from app.core.config import settings
from app.services.retrieval_service import RetrievalService, drop_weak_evidence
from rag.embedding.default_embedding import DefaultEmbedding
from rag.embedding.sparse_bm25 import encode_sparse
from rag.llm.re_rank import ReRanking
from rag.nlp.doc_chunking import DocumentChunker
from rag.qdrant.client import QdrantHttpClient, SPARSE_NAME

DATASET_REVISION = "da78f23f9119363459acbaf46bf89426ff26c259"
MODELS = {
    "embedding": (
        "intfloat/multilingual-e5-base",
        "d128750597153bb5987e10b1c3493a34e5a4502a",
    ),
    "reranker": ("BAAI/bge-reranker-v2-m3", "953dc6f6f85a1b2dbfca4c34a2796e7dde08d41e"),
    "generator": (
        "Qwen/Qwen2.5-0.5B-Instruct",
        "7ae557604adf67be50417f59c2c2f167def9a775",
    ),
}
CONFIGS = {
    "fixed_800_120": (800, 120, False),
    "structured_400_60": (400, 60, True),
    "structured_800_120": (800, 120, True),
    "structured_1600_240": (1600, 240, True),
}


def normalize(text):
    return " ".join(re.sub(r"[^\w\s]", " ", text.casefold()).split())


def identity(text):
    return hashlib.sha256(text.encode()).hexdigest()


def local_model(kind):
    name, revision = MODELS[kind]
    hub = Path(os.environ.get("HF_HUB_CACHE", Path.home() / ".cache/huggingface/hub"))
    path = hub / ("models--" + name.replace("/", "--")) / "snapshots" / revision
    if not path.is_dir():
        raise RuntimeError(f"Cache missing: download {name} at revision {revision}")
    return str(path)


def dataset(path, seed, dev_n, test_n):
    rows = [
        r for r in pq.read_table(path).to_pylist() if r["id"].startswith("indonesian-")
    ]
    documents = {}
    for row in rows:
        row["source_id"] = identity(row["context"])
        documents.setdefault(row["source_id"], row)
        # Some converted TyDi offsets do not slice Python Unicode strings
        # correctly. Verify the annotated text itself, never relocate a span
        # using a model prediction or silently discard these questions.
        assert any(answer in row["context"] for answer in row["answers"]["text"])
    titles = sorted({r["title"] for r in rows})
    rng = random.Random(seed)
    rng.shuffle(titles)
    dev_titles = set(titles[: len(titles) // 5])
    dev = [r for r in rows if r["title"] in dev_titles]
    test = [r for r in rows if r["title"] not in dev_titles]
    rng.shuffle(dev)
    rng.shuffle(test)
    assert len(dev) >= dev_n and len(test) >= test_n
    selected = dev[:dev_n] + test[:test_n]
    for row in selected:
        row["split"] = "dev" if row["title"] in dev_titles else "test"
    return rows, documents, selected


def make_chunks(documents, config):
    size, overlap, structured = CONFIGS[config]
    chunker = DocumentChunker(size, overlap)
    chunks = []
    for source_id, row in documents.items():
        if structured:
            parts = chunker.chunk_sections([(1, row["title"], row["context"])])
        else:
            parts = [
                {
                    "text": text,
                    "quote": text[:350],
                    "page_text": row["context"][:5000],
                    "page": 1,
                    "section": "",
                }
                for text in chunker.chunk_text(row["context"])
            ]
        for i, part in enumerate(parts):
            part.update(
                source_id=source_id,
                file_id=str(uuid5(NAMESPACE_URL, source_id)),
                file_name=row["title"],
                chunk_id=f"{source_id}:{i}",
            )
            chunks.append(part)
    return chunks


class CachedEmbedding:
    def __init__(self, vectors):
        self.vectors = vectors

    def encode(self, text):
        return self.vectors[text]


class CachedReranking(ReRanking):
    def __init__(self):
        super().__init__(model_name=local_model("reranker"))
        self.cache = {}

    def _scores(self, pairs, queries=None):
        keys = [(pair[0], pair[1]) for pair in pairs]
        missing = [pair for pair, key in zip(pairs, keys) if key not in self.cache]
        if missing:
            scores = super()._scores(missing, queries)
            self.cache.update(
                {(pair[0], pair[1]): score for pair, score in zip(missing, scores)}
            )
        return [self.cache[key] for key in keys]


def pairs_from_hits(question, hits):
    return [[question, hit.payload["document"], dict(hit.payload)] for hit in hits]


def evidence_metrics(row, pairs):
    matches = [p[2]["source_id"] == row["source_id"] for p in pairs]
    answers = [normalize(a) for a in row["answers"]["text"]]
    supported = [
        same and any(a and a in normalize(p[1]) for a in answers)
        for same, p in zip(matches, pairs)
    ]
    rank = next((i + 1 for i, ok in enumerate(supported) if ok), None)
    chars = sum(len(p[1]) for p in pairs)
    return {
        "source_hit": any(matches),
        "answer_hit": any(supported),
        "answer_hit1": bool(supported and supported[0]),
        "rr": 1 / rank if rank else 0,
        "source_precision": sum(matches) / len(pairs) if pairs else 0,
        "gold_char_fraction": (
            sum(len(p[1]) for p, match in zip(pairs, matches) if match) / chars
            if chars
            else 0
        ),
        "context_chars": chars,
        "evidence_count": len(pairs),
        "source_ids": [p[2]["source_id"] for p in pairs],
    }


def summarize(rows):
    keys = [
        "source_hit",
        "answer_hit",
        "answer_hit1",
        "rr",
        "source_precision",
        "gold_char_fraction",
        "context_chars",
        "evidence_count",
        "pool_answer_hit",
    ]
    return {"n": len(rows), **{k: float(np.mean([r[k] for r in rows])) for k in keys}}


def score_answer(prediction, answers):
    predicted = normalize(prediction)
    em, f1 = 0.0, 0.0
    for answer in answers:
        truth = normalize(answer)
        em = max(em, float(predicted == truth))
        common = sum((Counter(predicted.split()) & Counter(truth.split())).values())
        if common:
            precision, recall = common / len(predicted.split()), common / len(
                truth.split()
            )
            f1 = max(f1, 2 * precision * recall / (precision + recall))
    return {"exact_match": em, "token_f1": f1}


def generate(jobs, batch_size, allow_closed_book=True):
    from transformers import AutoModelForCausalLM, AutoTokenizer

    tokenizer = AutoTokenizer.from_pretrained(
        local_model("generator"), local_files_only=True
    )
    tokenizer.padding_side = "left"
    model = (
        AutoModelForCausalLM.from_pretrained(
            local_model("generator"),
            local_files_only=True,
            torch_dtype=torch.bfloat16,
            attn_implementation="sdpa",
        )
        .to("cuda")
        .eval()
    )
    system = (
        "Jawab pertanyaan dengan satu kutipan pendek yang persis menjawabnya. "
        "Jika BUKTI tersedia, gunakan hanya fakta dari BUKTI. "
        "Jika BUKTI tidak memuat jawabannya, jawab TIDAK DITEMUKAN. "
        + (
            "Jika tidak diberikan BUKTI, jawab berdasarkan pengetahuanmu. "
            if allow_closed_book
            else "Jangan gunakan pengetahuan di luar BUKTI, termasuk saat BUKTI kosong. "
        )
        + "Tulis hanya jawaban, tanpa penjelasan atau label."
    )
    for offset in range(0, len(jobs), batch_size):
        batch = jobs[offset : offset + batch_size]
        texts = []
        for job in batch:
            body = "\n\n".join(p[1] for p in job["pairs"])
            user = f"BUKTI:\n{body}\n\n" if job["mode"] != "closed_book" else ""
            user += "PERTANYAAN: " + job["question"]
            texts.append(
                tokenizer.apply_chat_template(
                    [
                        {"role": "system", "content": system},
                        {"role": "user", "content": user},
                    ],
                    tokenize=False,
                    add_generation_prompt=True,
                )
            )
        encoded = tokenizer(texts, padding=True, return_tensors="pt").to("cuda")
        lengths = encoded["attention_mask"].sum(1).tolist()
        assert max(lengths) + 64 <= 32768, "Never silently truncate evaluated evidence"
        with torch.inference_mode():
            output = model.generate(
                **encoded,
                max_new_tokens=64,
                do_sample=False,
                pad_token_id=tokenizer.pad_token_id,
            )
        predictions = tokenizer.batch_decode(
            output[:, encoded["input_ids"].shape[1] :], skip_special_tokens=True
        )
        for job, prediction, tokens in zip(batch, predictions, lengths):
            job["prediction"] = prediction.strip()
            job["input_tokens"] = tokens
            job.update(score_answer(prediction, job["answers"]))
            job["abstained"] = normalize(prediction) == "tidak ditemukan"
            job["extractive_support"] = bool(normalize(prediction)) and any(
                normalize(prediction) in normalize(p[1]) for p in job["pairs"]
            )
            del job["pairs"]
        print(
            f"generation {min(offset + batch_size, len(jobs))}/{len(jobs)}", flush=True
        )
    return jobs


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dataset", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--seed", type=int, default=20260918)
    parser.add_argument("--dev", type=int, default=40)
    parser.add_argument("--test", type=int, default=160)
    parser.add_argument("--generation", type=int, default=80)
    parser.add_argument("--batch-size", type=int, default=8)
    args = parser.parse_args()
    if not 0 < args.generation <= args.test:
        parser.error("--generation must be between 1 and --test")
    args.out.mkdir(parents=True, exist_ok=True)
    logger.remove()
    logger.add(sys.stderr, level="WARNING")
    torch.set_num_threads(8)
    torch.manual_seed(args.seed)
    if not torch.cuda.is_available():
        raise RuntimeError("This recorded experiment requires a CUDA GPU")
    settings.RETRIEVAL_CANDIDATES = 40
    settings.RERANK_MIN_SCORE = 0.05
    settings.RERANK_RELATIVE_FLOOR = 0.5
    all_rows, documents, selected = dataset(
        args.dataset, args.seed, args.dev, args.test
    )
    report = {
        "started_utc": datetime.now(timezone.utc).isoformat(),
        "seed": args.seed,
        "dataset": "google-research-datasets/tydiqa",
        "revision": DATASET_REVISION,
        "dataset_sha256": hashlib.sha256(args.dataset.read_bytes()).hexdigest(),
        "subset": "secondary_task/validation, Indonesian",
        "rows": len(all_rows),
        "documents": len(documents),
        "dev_n": args.dev,
        "test_n": args.test,
        "generation_n": args.generation,
        "models": MODELS,
        "gpu": torch.cuda.get_device_name(),
        "platform": platform.platform(),
        "versions": {
            p: importlib.metadata.version(p)
            for p in [
                "torch",
                "transformers",
                "sentence-transformers",
                "qdrant-client",
                "pyarrow",
            ]
        },
        "settings": {
            "pool": 40,
            "absolute_floor": 0.05,
            "relative_floor": 0.5,
            "max_parents": 4,
            "augmentation": False,
            "knowledge_graph": False,
            "index": "Qdrant in-memory exact search",
            "stemming": True,
        },
        "configs": {},
    }
    (args.out / "selection.json").write_text(
        json.dumps(
            [
                {k: r[k] for k in ["id", "title", "source_id", "split"]}
                for r in selected
            ],
            indent=2,
        )
    )
    embedding = DefaultEmbedding(device="cuda", model_name=local_model("embedding"))
    q_vectors = embedding.encode_queries([r["question"] for r in selected])
    cached_embedding = CachedEmbedding(
        dict(zip([r["question"] for r in selected], q_vectors))
    )
    reranker = CachedReranking()
    all_metrics, evidence = [], {}
    for config in CONFIGS:
        started = time.perf_counter()
        chunks = make_chunks(documents, config)
        client = QdrantHttpClient.__new__(QdrantHttpClient)
        client.client = QdrantClient(":memory:")
        client.create_collection(config, vector_size=embedding.vector_size)
        for start in range(0, len(chunks), 128):
            part = chunks[start : start + 128]
            client.add_documents(
                config,
                [p["chunk_id"] for p in part],
                [p["text"] for p in part],
                [{k: v for k, v in p.items() if k != "text"} for p in part],
                embedding.encode,
            )
        index_seconds = time.perf_counter() - started
        truncations = sum(
            len(t) > embedding.model.max_seq_length
            for t in embedding.model.tokenizer(
                ["passage: " + p["text"] for p in chunks], truncation=False
            )["input_ids"]
        )
        report["configs"][config] = {
            "chunks": len(chunks),
            "indexed_chars": sum(len(p["text"]) for p in chunks),
            "index_seconds": index_seconds,
            "embedding_truncated_chunks": truncations,
            "dense_vector_bytes": len(chunks) * embedding.vector_size * 4,
        }
        service = RetrievalService(
            SimpleNamespace(
                read_by_id=lambda _: SimpleNamespace(vectordb_collection_name=config)
            ),
            client,
            None,
            embedding_model=cached_embedding,
            re_ranking=reranker,
        )
        for number, row in enumerate(selected):
            query = row["question"]
            vector = cached_embedding.encode(query)
            dense = client.search(config, vector, limit=40)
            sparse = client.client.query_points(
                config, query=encode_sparse(query), using=SPARSE_NAME, limit=40
            ).points
            hybrid = client.search(config, vector, limit=40, query_text=query)
            pool = pairs_from_hits(query, hybrid)
            ranked = reranker.rank(pairs=pool, top_results=8, min_score=0.05)
            variants = {
                "dense_leaf": pairs_from_hits(query, dense[:4]),
                "sparse_leaf": pairs_from_hits(query, sparse[:4]),
                "hybrid_leaf": pool[:4],
                "rerank_leaf": drop_weak_evidence(ranked, 0.5)[:4],
                "production_parent": service.retrieve(
                    SimpleNamespace(collection_id="evaluation", question_text=query),
                    using_augment_query=False,
                ),
            }
            for mode, pairs in variants.items():
                metrics = evidence_metrics(row, pairs)
                source_pool = (
                    pairs_from_hits(query, dense if mode == "dense_leaf" else sparse)
                    if mode in {"dense_leaf", "sparse_leaf"}
                    else pool
                )
                metrics.update(
                    id=row["id"],
                    split=row["split"],
                    config=config,
                    mode=mode,
                    pool_answer_hit=evidence_metrics(row, source_pool)["answer_hit"],
                )
                all_metrics.append(metrics)
                evidence[(config, mode, row["id"])] = pairs
            if number % 20 == 0:
                print(
                    f"{config}: retrieval {number + 1}/{len(selected)} ({len(chunks)} chunks)",
                    flush=True,
                )
        for split in ["dev", "test"]:
            report["configs"][config][split] = {
                mode: summarize(
                    [
                        r
                        for r in all_metrics
                        if r["config"] == config
                        and r["mode"] == mode
                        and r["split"] == split
                    ]
                )
                for mode in variants
            }
        client.client.close()
        (args.out / "summary.json").write_text(json.dumps(report, indent=2))
        with (args.out / "retrieval.jsonl").open("w") as f:
            for row in all_metrics:
                f.write(json.dumps(row) + "\n")

    # Select only on dev, without looking at held-out answers or generations.
    choices = [(c, m) for c in CONFIGS for m in ["rerank_leaf", "production_parent"]]
    best = max(
        choices,
        key=lambda cm: (
            report["configs"][cm[0]]["dev"][cm[1]]["answer_hit"],
            report["configs"][cm[0]]["dev"][cm[1]]["rr"],
            -report["configs"][cm[0]]["dev"][cm[1]]["context_chars"],
        ),
    )
    report["dev_selected"] = best
    print("dev selected:", best, flush=True)
    jobs = []
    for row in [r for r in selected if r["split"] == "test"][: args.generation]:
        modes = {
            "closed_book": [],
            "dense_baseline": evidence[("fixed_800_120", "dense_leaf", row["id"])],
            "current_production": evidence[
                ("structured_800_120", "production_parent", row["id"])
            ],
            "dev_selected": evidence[(*best, row["id"])],
            "oracle": [
                [row["question"], row["context"], {"source_id": row["source_id"]}]
            ],
        }
        for mode, pairs in modes.items():
            jobs.append(
                {
                    "id": row["id"],
                    "question": row["question"],
                    "answers": row["answers"]["text"],
                    "mode": mode,
                    "pairs": pairs,
                    "evidence_answer_hit": evidence_metrics(row, pairs)["answer_hit"],
                }
            )
    del embedding, reranker, service, evidence, client
    gc.collect()
    torch.cuda.empty_cache()
    jobs = generate(jobs, args.batch_size)
    with (args.out / "generation.jsonl").open("w") as f:
        for job in jobs:
            f.write(json.dumps(job, ensure_ascii=False) + "\n")
    report["generation"] = {}
    for mode in modes:
        group = [j for j in jobs if j["mode"] == mode]
        report["generation"][mode] = {
            "n": len(group),
            **{
                k: float(np.mean([j[k] for j in group]))
                for k in [
                    "exact_match",
                    "token_f1",
                    "evidence_answer_hit",
                    "abstained",
                    "extractive_support",
                    "input_tokens",
                ]
            },
        }
    report["finished_utc"] = datetime.now(timezone.utc).isoformat()
    (args.out / "summary.json").write_text(json.dumps(report, indent=2))
    print(json.dumps(report["generation"], indent=2), flush=True)


if __name__ == "__main__":
    main()
