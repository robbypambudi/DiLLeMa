"""Exercise the real chunker -> payload -> pack -> citation evidence contract."""

import unittest
from types import SimpleNamespace
from unittest.mock import Mock, patch
from uuid import uuid4

from app.pipeline.pipeline_service import PipelineService
from app.services.retrieval_service import pack_parent_pages
from rag.nlp.doc_chunking import DocumentChunker


class EvidenceProvenanceTests(unittest.TestCase):
    def test_version_and_ids_are_stable_and_change_with_document(self):
        sections = [
            (None, "Biaya", "Biaya 100 rupiah."),
            (None, "Biaya", "Biaya 200 rupiah."),
        ]
        chunker = DocumentChunker()
        first = chunker.chunk_sections(sections)
        self.assertEqual(first, chunker.chunk_sections(sections))
        self.assertNotEqual(first[0]["parent_id"], first[1]["parent_id"])
        changed = chunker.chunk_sections([(None, "Biaya", "Biaya 300 rupiah.")])
        self.assertNotEqual(
            first[0]["document_version"], changed[0]["document_version"]
        )

    def test_late_answer_is_located_and_windowed_without_truncation(self):
        body = (
            "Informasi pendahuluan layanan. " * 240
            + "\n\n"
            + "rincian " * 65
            + "KODEBUKTI7391 berlaku."
        )
        chunks = DocumentChunker().chunk_sections([(1, "", body)])
        leaf = next(c for c in chunks if "KODEBUKTI7391" in c["text"])
        self.assertGreater(leaf["source_start"], 5000)
        self.assertEqual(
            body[leaf["source_start"] : leaf["source_end"]], leaf["evidence_text"]
        )
        self.assertIn("KODEBUKTI7391", leaf["parent_window"])
        packed = pack_parent_pages([["q", leaf["text"], dict(leaf, file_id="1")]])
        self.assertIn("KODEBUKTI7391", packed[0][1])
        self.assertEqual(
            packed[0][2]["evidence_spans"][0]["source_start"], leaf["source_start"]
        )

    def test_table_header_survives_when_retrieved_row_is_far_from_header(self):
        text = "| Kode | Nama | Biaya |\n" + "\n".join(
            f"| K{i:03} | Layanan {i} | {i} rupiah |" for i in range(200)
        )
        leaf = next(
            c
            for c in DocumentChunker().chunk_sections([(1, "", text)])
            if "K199" in c["text"]
        )
        packed = pack_parent_pages([["q", leaf["text"], dict(leaf, file_id="1")]])
        self.assertIn("K199", packed[0][1])
        self.assertIn("| Kode | Nama | Biaya |", packed[0][1])
        for source in packed[0][2]["citation_texts"]:
            self.assertIn(source, text)
        from rag.llm.chat_model import OpenAIChat

        packed[0][2]["file_name"] = "services.md"
        quote = OpenAIChat.source_items(packed, "Biaya K199 199 rupiah [S1].")[0][
            "quote"
        ]
        self.assertTrue(quote)
        self.assertIn(quote, text)

    def test_ingestion_passes_provenance_to_the_vector_payload(self):
        sections = [(None, "Biaya", "Biaya 100 rupiah.")]
        repo, client = Mock(), Mock()
        repo.get_collection_name.return_value = "pilot"
        repo.get_vectordb_collection_name.return_value = "pilot-index"
        file = SimpleNamespace(
            id=uuid4(),
            collection_id=uuid4(),
            file_path="unused",
            file_type="text/plain",
            file_name="pilot.txt",
        )
        service = PipelineService(
            repo, client, embedding_model=Mock(), doc_chunker=DocumentChunker()
        )
        with (
            patch("app.pipeline.pipeline_service.read_sections", return_value=sections),
            patch("app.pipeline.pipeline_service.document_pages", return_value=None),
        ):
            service.run_pipeline(file)
        client.add_documents.assert_called_once()
        meta = client.add_documents.call_args.kwargs["metadatas"][0]
        for field in [
            "document_version",
            "parent_id",
            "chunk_id",
            "section_id",
            "evidence_text",
            "parent_window",
        ]:
            self.assertTrue(meta[field], field)
        self.assertEqual(meta["source_start"], 0)
        self.assertEqual(meta["offset_basis"], "cleaned_unit_unicode")


if __name__ == "__main__":
    unittest.main()
