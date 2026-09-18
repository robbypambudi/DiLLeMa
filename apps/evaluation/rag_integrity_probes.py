"""Small synthetic probes of evidence preservation, separate from TyDi QA."""

import argparse
import json
from pathlib import Path

from public_rag_eval import DocumentChunker, encode_sparse
from app.services.retrieval_service import pack_parent_pages


def probes():
    chunker = DocumentChunker()
    sections = [
        (None, "Biaya", "Biaya layanan adalah 175 ribu rupiah untuk peserta reguler."),
        (None, "Batas waktu", "Batas waktu pendaftaran adalah 12 November 2027."),
    ]
    chunks = chunker.chunk_sections(sections)
    pairs = [
        ["biaya dan batas waktu", c["text"], dict(c, file_id="same-document")]
        for c in chunks
    ]
    packed = pack_parent_pages(pairs)
    nonpaged = {
        "input_sections": len(sections),
        "retrieved_chunks": len(pairs),
        "packed_sources": len(packed),
        "deadline_preserved": any("12 November 2027" in p[1] for p in packed),
    }

    marker = "KODEBUKTI7391"
    long_page = None
    for padding in range(350, 850, 25):
        text = (
            "Informasi pendahuluan untuk pembaca tentang tata cara layanan. " * 100
            + "\n\n"
            + "rincian " * (padding // 8)
            + marker
            + " adalah kode akses."
        )
        for chunk in chunker.chunk_sections([(1, "", text)]):
            if marker in chunk["text"] and marker not in chunk["quote"]:
                result = pack_parent_pages(
                    [["kode akses", chunk["text"], dict(chunk, file_id="long")]]
                )
                long_page = {
                    "source_chars": len(text),
                    "marker_offset": text.index(marker),
                    "retrieved_leaf_has_answer": True,
                    "quote_has_answer": marker in chunk["quote"],
                    "parent_chars": len(chunk["page_text"]),
                    "packed_has_answer": any(marker in p[1] for p in result),
                }
                break
        if long_page:
            break
    if long_page is None:
        raise RuntimeError(
            "Synthetic long-page probe did not construct its target case"
        )
    once, repeated = encode_sparse("dokumen"), encode_sparse("dokumen " * 10)
    return {
        "unpaginated_sections": nonpaged,
        "long_parent_truncation": long_page,
        "sparse_term_frequency": {
            "once": once.values,
            "ten_times": repeated.values,
            "ratio": repeated.values[0] / once.values[0],
        },
    }


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", required=True, type=Path)
    args = parser.parse_args()
    result = probes()
    args.out.write_text(json.dumps(result, indent=2))
    print(json.dumps(result, indent=2))
