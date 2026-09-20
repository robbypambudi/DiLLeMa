"""Reject what the corpus cannot answer before retrieval spends anything.

Two cheap checks, in cost order. `trivial_reason` runs no model at all and
catches greetings and fragments. The cross-encoder probe in
`RetrievalService` catches a well-formed question about something the corpus
simply does not cover -- the case no amount of string matching can decide.
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
# Letters in any script, so an Indonesian or English question counts alike.
_WORD = re.compile(r"[^\W\d_]{2,}", re.UNICODE)

MIN_QUESTION_CHARS = 3


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
