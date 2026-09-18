"""Shared lexical tokenizer for sparse retrieval and quote selection.

Both places compare a query or an answer against document text, so they have
to agree on what counts as a term; a second regex here would silently drift
from the one the BM25 index was built with.
"""

import re

_TOKEN = re.compile(r"[A-Za-zÀ-ÿ0-9]+")

# Indonesian function words, plus the English ones that survive in the mixed
# documents this app ingests. They are dropped only for quote selection: a
# sentence must not win because it also happens to say "yang" or "dan".
STOPWORDS = frozenset(
    """
    ada adalah adanya agar akan antara apa atas atau bagaimana bagi bahwa
    banyak berupa bila bisa dalam dan dapat dari demikian dengan di dia
    dilakukan dimana dll drg guna hal harus hingga ini itu jadi jika juga
    kami kapan karena ke kepada ketika kita lagi lain lalu lebih maka mana
    masih maupun melalui mempunyai mengapa menjadi merupakan mereka misalnya
    namun oleh pada padahal paling para per saat saja sampai sangat saya
    sebagai sebelum secara sehingga sejak selain seluruh semua seperti serta
    sesudah setelah setiap siapa suatu sudah supaya tapi telah tentang
    terdapat terhadap tersebut tetapi tidak untuk yaitu yakni yang
    a about an and are as at be been but by can did do does for from had has
    have how in into is it its of on or that the their there these this to
    was were what when where which who will with would you your
    """.split()
)


def tokenize(text: str) -> list[str]:
    """Lowercased alphanumeric terms. Single characters carry no signal."""
    return [token.lower() for token in _TOKEN.findall(text or "") if len(token) > 1]


def content_tokens(text: str) -> list[str]:
    """Tokens that can distinguish one sentence from another."""
    return [token for token in tokenize(text) if token not in STOPWORDS]


def stems(text: str) -> list[str]:
    """Index terms: tokens reduced to their root so affixes stop splitting them."""
    from rag.nlp.stemmer import stem

    return [stem(token) for token in tokenize(text)]


def content_stems(text: str) -> list[str]:
    """Roots of the tokens that carry meaning, for comparing two passages."""
    from rag.nlp.stemmer import stem

    return [stem(token) for token in content_tokens(text)]
