"""Indonesian stemming for lexical matching.

BM25 compares surface forms, and Indonesian carries meaning in affixes:
"menetapkan", "penetapan", "ditetapkan" and "ketetapan" are four index terms
for one root, so a question phrased with one form misses passages written with
another. Stemming both sides collapses them onto "tetap".

Disable with `BM25_STEMMING=false` -- but note that the sparse index stores the
terms it was built with, so flipping this without reindexing leaves queries
looking up terms no document has.
"""

import os
from functools import lru_cache

from loguru import logger

STEMMING_ENABLED = os.getenv("BM25_STEMMING", "true").strip().lower() not in {
    "0",
    "false",
    "no",
    "off",
}


@lru_cache(maxsize=1)
def _stemmer():
    from Sastrawi.Stemmer.StemmerFactory import StemmerFactory

    logger.info("Loading Indonesian stemmer for lexical matching")
    return StemmerFactory().create_stemmer()


@lru_cache(maxsize=200_000)
def stem(token: str) -> str:
    """The root of one token, or the token itself when it has none.

    Short tokens and anything with a digit are left alone: acronyms and
    identifiers ("ITS", "2026", "P3") are not inflected, and stripping what
    looks like an affix off them would merge unrelated terms.
    """
    if not STEMMING_ENABLED or len(token) <= 3 or any(c.isdigit() for c in token):
        return token
    try:
        root = _stemmer().stem(token)
    except Exception as exc:  # pragma: no cover - missing or broken dictionary
        logger.warning("Stemmer unavailable ({}); matching surface forms", type(exc).__name__)
        return token
    return root or token
