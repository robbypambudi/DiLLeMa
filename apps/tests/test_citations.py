"""Citations must point at a source the answer used, and at the right lines."""

import unittest
from types import SimpleNamespace
from unittest.mock import Mock, patch
from uuid import uuid4

from app.schema.question_schema import CreateQuestion
from app.services.retrieval_service import RetrievalService
from rag.llm.chat_model import OpenAIChat
from rag.llm.re_rank import ReRanking
from rag.nlp.doc_chunking import DocumentChunker
from rag.nlp.doc_parse import Section
from rag.nlp.quote_select import select_quote, sentence_spans

PAGE = (
    "RENSTRA ITS 2026-2030\n"
    "Bab II Arah Kebijakan. Dokumen ini disusun sebagai acuan unit kerja.\n"
    "Anggaran penelitian ditetapkan sebesar Rp 45 miliar pada tahun 2027 "
    "untuk seluruh fakultas.\n"
    "Penutup."
)


def pair(name, page, quote, page_text, file_id="1", **meta):
    return [
        "pertanyaan",
        page_text,
        {
            "file_name": name,
            "file_id": file_id,
            "page": page,
            "quote": quote,
            "page_text": page_text,
            **meta,
        },
    ]


class CitedSourceTests(unittest.TestCase):
    def setUp(self):
        self.pairs = [
            pair("renstra.pdf", 3, "RENSTRA ITS 2026-2030", PAGE, page_label="iii"),
            pair("lain.pdf", 9, "Tidak relevan", "Halaman lain.", file_id="2"),
        ]

    def test_only_sources_the_answer_cites_are_reported(self):
        items = OpenAIChat.source_items(self.pairs, "<li>Anggaran Rp 45 miliar [S1].</li>")
        self.assertEqual([item["file_name"] for item in items], ["renstra.pdf"])

    def test_labels_keep_their_number_when_an_earlier_source_is_dropped(self):
        items = OpenAIChat.source_items(self.pairs, "<li>Lihat [S2].</li>")
        # The answer says [S2], so the surviving source must still be S2.
        self.assertEqual([item["index"] for item in items], [2])
        self.assertEqual(items[0]["file_name"], "lain.pdf")

    def test_an_answer_without_markers_reports_only_the_best_source(self):
        items = OpenAIChat.source_items(self.pairs, "Jawaban tanpa penanda apa pun.")
        self.assertEqual([item["index"] for item in items], [1])

    def test_retrieval_only_callers_still_see_every_source(self):
        self.assertEqual(len(OpenAIChat.source_items(self.pairs)), 2)

    def test_a_model_written_source_list_cannot_cite_itself(self):
        answer = "<p>Jawaban.</p><p><b>Sumber konteks:</b></p><ul><li>[S2] lain.pdf</li></ul>"
        items = OpenAIChat.source_items(
            self.pairs, OpenAIChat.strip_source_footer(answer)
        )
        self.assertEqual([item["index"] for item in items], [1])

    def test_claims_are_attributed_per_list_item(self):
        claims = OpenAIChat.cited_claims(
            "<li>Anggaran [S1].</li><li>Struktur [S2].</li>"
        )
        self.assertIn("Anggaran", claims[1])
        self.assertNotIn("Struktur", claims[1])


class QuoteSelectionTests(unittest.TestCase):
    def test_quote_is_the_sentence_that_supports_the_claim(self):
        items = OpenAIChat.source_items(
            [pair("renstra.pdf", 3, "RENSTRA ITS 2026-2030", PAGE)],
            "<li><b>Anggaran:</b> penelitian Rp 45 miliar pada 2027 [S1].</li>",
        )
        self.assertIn("Rp 45 miliar", items[0]["quote"])
        self.assertNotIn("Bab II", items[0]["quote"])

    def test_quote_stays_a_verbatim_slice_so_the_viewer_can_highlight_it(self):
        quote = select_quote("anggaran penelitian 2027", PAGE)
        self.assertIn(quote, PAGE)

    def test_an_unused_source_keeps_its_indexed_quote(self):
        quote = select_quote("topik yang sama sekali berbeda", PAGE, "kutipan awal")
        self.assertEqual(quote, "kutipan awal")

    def test_a_short_sentence_grows_until_it_can_be_found(self):
        page = "Pasal 12. Dana penelitian dialokasikan setiap tahun anggaran berjalan."
        quote = select_quote("apa isi Pasal 12", page)
        self.assertIn(quote, page)
        self.assertGreaterEqual(len(quote), 60)

    def test_sentence_spans_are_verbatim(self):
        self.assertTrue(
            all(PAGE[start:end] == PAGE[start:end].strip() for start, end in sentence_spans(PAGE))
        )

    def test_graph_claims_without_a_page_keep_their_quote(self):
        items = OpenAIChat.source_items(
            [["q", "Klaim", {"file_name": "rules.pdf", "page": 3, "quote": "aturan", "claim_id": "abc"}]],
            "<li>Aturan berlaku [S1].</li>",
        )
        self.assertEqual(items[0]["quote"], "aturan")


class PageLabelTests(unittest.TestCase):
    def test_printed_label_is_indexed_next_to_the_physical_page(self):
        chunk = DocumentChunker().chunk_sections(
            [Section(3, "", "Isi kata pengantar.", "iii")]
        )[0]
        self.assertEqual((chunk["page"], chunk["page_label"]), (3, "iii"))

    def test_footer_shows_the_printed_label_and_the_panel_keeps_the_index(self):
        items = OpenAIChat.source_items(
            [pair("renstra.pdf", 3, "kutipan", PAGE, page_label="iii")],
            "<li>Isi [S1].</li>",
        )
        self.assertEqual(items[0]["pages"], [3])
        self.assertEqual(items[0]["page_labels"], ["iii"])
        footer = OpenAIChat.format_sources(
            [pair("renstra.pdf", 3, "kutipan", PAGE, page_label="iii")],
            "<li>Isi [S1].</li>",
        )
        self.assertIn("halaman iii", footer)

    def test_pages_without_a_label_still_cite_their_number(self):
        footer = OpenAIChat.format_sources(
            [pair("renstra.pdf", 4, "kutipan", PAGE)], "<li>Isi [S1].</li>"
        )
        self.assertIn("halaman 4", footer)


class RelevanceFloorTests(unittest.TestCase):
    def build(self, score):
        reranker = object.__new__(ReRanking)
        reranker.model = Mock()
        reranker.model.predict.return_value = [score]
        collections = Mock()
        collections.read_by_id.return_value = SimpleNamespace(
            vectordb_collection_name="pilot"
        )
        vectors = Mock()
        vectors.search.return_value = [
            SimpleNamespace(
                id=1,
                score=0.9,
                payload={
                    "document": "teks apa pun",
                    "file_name": "renstra.pdf",
                    "file_id": str(uuid4()),
                    "page": 1,
                    "page_text": PAGE,
                },
            )
        ]
        embedding = Mock()
        embedding.encode.return_value = SimpleNamespace(tolist=lambda: [0.1])
        service = RetrievalService(
            collections, vectors, Mock(), None, embedding, reranker
        )
        return service, CreateQuestion(
            question_id="q", question_text="Berapa anggaran?", collection_id=uuid4()
        )

    def test_evidence_below_the_floor_is_not_answered_from(self):
        service, payload = self.build(0.01)
        with patch("app.services.retrieval_service.settings.RERANK_MIN_SCORE", 0.05):
            self.assertEqual(service.retrieve(payload), [])

    def test_relevant_evidence_still_passes(self):
        service, payload = self.build(0.8)
        with patch("app.services.retrieval_service.settings.RERANK_MIN_SCORE", 0.05):
            self.assertEqual(len(service.retrieve(payload)), 1)


if __name__ == "__main__":
    unittest.main()
