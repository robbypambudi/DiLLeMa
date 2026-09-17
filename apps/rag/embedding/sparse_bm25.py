"""Hashed-term BM25 sparse vectors. Qdrant applies collection IDF when modifier=IDF."""

from collections import Counter
from hashlib import blake2b
import re

from qdrant_client.models import SparseVector

_TOKEN = re.compile(r"[A-Za-zÀ-ÿ0-9]+")
_VOCAB = 2_147_483_647  # max signed 32-bit, Qdrant sparse index range


def tokenize(text: str) -> list[str]:
    return [token.lower() for token in _TOKEN.findall(text or "") if len(token) > 1]


def term_index(token: str) -> int:
    digest = blake2b(token.encode("utf-8"), digest_size=4).digest()
    return int.from_bytes(digest, "big") % _VOCAB


def encode_sparse(text: str) -> SparseVector:
    counts: Counter[int] = Counter()
    for token in tokenize(text):
        counts[term_index(token)] += 1
    items = sorted(counts.items())
    return SparseVector(
        indices=[index for index, _ in items],
        values=[float(value) for _, value in items],
    )
