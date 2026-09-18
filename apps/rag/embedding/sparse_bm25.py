"""Hashed-term BM25 sparse vectors. Qdrant applies collection IDF when modifier=IDF."""

from collections import Counter
from hashlib import blake2b

from qdrant_client.models import SparseVector

from rag.nlp.tokens import stems, tokenize

_VOCAB = 2_147_483_647  # max signed 32-bit, Qdrant sparse index range

__all__ = ["encode_sparse", "term_index", "tokenize"]


def term_index(token: str) -> int:
    digest = blake2b(token.encode("utf-8"), digest_size=4).digest()
    return int.from_bytes(digest, "big") % _VOCAB


def encode_sparse(text: str) -> SparseVector:
    counts: Counter[int] = Counter()
    # Indexed and queried through the same stemmer, so "penetapan" finds
    # "ditetapkan". Changing that setting requires reindexing the collection.
    for token in stems(text):
        counts[term_index(token)] += 1
    items = sorted(counts.items())
    return SparseVector(
        indices=[index for index, _ in items],
        values=[float(value) for _, value in items],
    )
