"""Name what a message is before the corpus is asked to answer it.

Three kinds of message never belong in retrieval, and lumping them together
is what made the assistant answer "di luar cakupan dokumen" to "apa yang bisa
saya tanyakan di sini?". Measured against the live index, that question and
its variants score 0.0008-0.093 -- correctly, because no passage answers a
question about the collection itself. They need a different source of truth
(the collection's own metadata), not a lower threshold.

`local_intent` names them so the caller can answer from metadata; the
cross-encoder probe in `RetrievalService` still decides everything else,
which is the case no amount of string matching can settle.
"""

import re

# A greeting, a thank-you, or a test ping: complete utterances that carry no
# question. Matched whole, so "halo, apa syarat pendaftaran?" still passes.
_SMALL_TALK = re.compile(
    r"^(h[ae]?i+|h[ae]llo+|halo+|hey+|oi+|p+|ping|test(ing)?|cek|assalamu.?alaikum|"
    r"pagi|siang|sore|malam|selamat\s+(pagi|siang|sore|malam)|"
    r"(terima\s*kasih|makasih|thanks?|thank\s+you|tq|ok[ae]?y?|sip|mantap|bye|dadah)"
    r")[\s!.?,]*$",
    re.IGNORECASE,
)
# Asking what this assistant is for, what it holds, or what may be asked of
# it. Answerable from the collection and its file list, never from a passage.
_CAPABILITY = re.compile(
    r"(apa|apa\s+saja)\s+(yang\s+)?(bisa|dapat|boleh)\s+"
    r"(saya\s+|aku\s+|kita\s+)?(di)?(tanya|tanyakan|nanya)"
    r"|bisa\s+(tanya|nanya|ditanya|ditanyakan)\s+apa"
    r"|(dokumen|file|berkas)\s+apa\s*(saja|aja)?"
    r"|ada\s+(dokumen|file|berkas)\s+apa"
    r"|isi\s+(dari\s+)?(koleksi|dokumen)"
    r"|(kamu|kau|anda|bot|chatbot|kamu)\s+(bisa|dapat)\s+(bantu\s+)?apa"
    r"|bisa\s+bantu\s+apa"
    r"|(kamu|anda)\s+(ini\s+)?siapa"
    r"|topik\s+apa\s*(saja|aja)?"
    r"|what\s+can\s+(i|you)\s+(ask|do)"
    r"|(which|what)\s+(documents?|files?)",
    re.IGNORECASE,
)
# Letters in any script, so an Indonesian or English question counts alike.
_WORD = re.compile(r"[^\W\d_]{2,}", re.UNICODE)

MIN_QUESTION_CHARS = 3
# A meta phrase inside a long sentence is usually part of a real question
# ("dokumen apa saja yang mengatur kewajiban publikasi dosen?"), so the match
# only counts for a short one. Guessing wrong here costs a document list
# instead of an answer, which is the milder of the two failures.
MAX_CAPABILITY_WORDS = 10


def local_intent(question: str) -> str | None:
    """What this message is, when it can be settled without the corpus.

    Returns "capability", "small_talk", "too_short", "no_words", or None when
    the message is a question the documents should be searched for.
    """
    text = (question or "").strip()
    if _CAPABILITY.search(text) and len(text.split()) <= MAX_CAPABILITY_WORDS:
        return "capability"
    return trivial_reason(text)


def trivial_reason(question: str) -> str | None:
    """Name why a question cannot be searched at all, or None if it can.

    Deliberately narrow: it rejects only what no retrieval could serve. A bare
    keyword ("beasiswa") is a legitimate search, so it passes here and the
    probe decides it on evidence instead of on its length.
    """
    text = (question or "").strip()
    if len(text) < MIN_QUESTION_CHARS:
        return "too_short"
    if _SMALL_TALK.match(text):
        return "small_talk"
    if not _WORD.search(text):
        return "no_words"
    return None
