"""Replies the assistant can give about itself, without asking the corpus.

A question about the collection ("apa yang bisa saya tanyakan di sini?") has
no passage that answers it, so retrieval rightly scores it near zero. Answered
from the collection's own metadata it is trivial, and costs no search and no
LLM call at all.

Nothing here describes what the documents *say*: only their names, which the
database knows. Inventing example topics from a filename would be guessing at
content nobody has read.
"""

MAX_LISTED_FILES = 10


def _documents(collection_name: str, file_names: list[str]) -> str:
    if not file_names:
        return (
            f"Koleksi **{collection_name}** belum memiliki dokumen yang terindeks, "
            "jadi belum ada yang bisa saya jawab dari sini."
        )
    listed = file_names[:MAX_LISTED_FILES]
    lines = "\n".join(f"- {name}" for name in listed)
    rest = len(file_names) - len(listed)
    if rest > 0:
        lines += f"\n- …dan {rest} dokumen lainnya"
    return f"Dokumen pada koleksi **{collection_name}**:\n{lines}"


def capability_answer(collection_name: str, file_names: list[str]) -> str:
    """What this assistant is for, and what it currently holds."""
    body = _documents(collection_name, file_names)
    if not file_names:
        return body + "\n\nUnggah dokumen terlebih dahulu melalui menu koleksi."
    return (
        "Saya menjawab pertanyaan berdasarkan isi dokumen yang ada di koleksi ini.\n\n"
        f"{body}\n\n"
        "Silakan tanyakan apa pun yang dibahas di dalamnya. Setiap jawaban saya "
        "sertai sitasi ke halaman sumbernya, dan bila jawabannya tidak ada di "
        "dokumen, saya akan mengatakannya."
    )


def small_talk_answer(collection_name: str, file_names: list[str]) -> str:
    """A greeting deserves a greeting, not a refusal."""
    if not file_names:
        return _documents(collection_name, file_names)
    return (
        f"Halo! Saya asisten untuk koleksi **{collection_name}**. "
        "Silakan ajukan pertanyaan tentang isi dokumennya — saya jawab beserta "
        "sitasi sumbernya."
    )


def incomplete_answer(collection_name: str, file_names: list[str]) -> str:
    """Too short or wordless to search for."""
    return (
        "Pertanyaannya belum cukup jelas untuk saya cari. "
        f"Coba tuliskan pertanyaan lengkap tentang isi koleksi **{collection_name}**."
    )


def out_of_scope_answer(collection_name: str, file_names: list[str]) -> str:
    """A refusal that still tells the user where they are.

    A dead end invites the same question reworded; naming the documents lets
    the user judge for themselves whether to ask something else or switch
    collection.
    """
    return (
        f"Pertanyaan ini di luar cakupan dokumen pada koleksi **{collection_name}**.\n\n"
        f"{_documents(collection_name, file_names)}\n\n"
        "Silakan ajukan pertanyaan mengenai isi dokumen tersebut."
    )


# Which reply answers which locally-decided intent.
BY_INTENT = {
    "capability": capability_answer,
    "small_talk": small_talk_answer,
    "too_short": incomplete_answer,
    "no_words": incomplete_answer,
}
