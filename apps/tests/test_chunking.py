import unittest

from rag.nlp.doc_chunking import DocumentChunker


class ChunkingTests(unittest.TestCase):
    def test_page_windows_keep_page_and_do_not_mix_pages(self):
        chunker = DocumentChunker(chunk_size=40, chunk_overlap=0)
        chunks = chunker.chunk_sections(
            [
                (1, "Pendahuluan", "Visi ITS adalah menjadi perguruan tinggi unggul."),
                (2, "Pendanaan", "Perencanaan pendanaan bersifat prudent dan adaptif."),
            ],
            file_name="RENSTRA.pdf",
        )
        self.assertGreaterEqual(len(chunks), 2)
        pages = {item["page"] for item in chunks}
        self.assertEqual(pages, {1, 2})
        page_one = next(item for item in chunks if item["page"] == 1)
        # Page and file stay in the metadata; in the text they would match every chunk.
        self.assertNotIn("halaman 1", page_one["text"])
        self.assertIn("Visi ITS", page_one["text"])
        self.assertNotIn("prudent", page_one["text"])
        self.assertEqual(page_one["section"], "Pendahuluan")
        self.assertIn("Visi ITS", page_one["page_text"])

    def test_plain_text_still_chunks_without_page(self):
        chunker = DocumentChunker(chunk_size=20, chunk_overlap=0)
        chunks = chunker.chunk_sections([(None, "", "Alpha. Beta. Gamma.")], file_name="note.txt")
        self.assertTrue(chunks)
        self.assertIsNone(chunks[0]["page"])
        self.assertTrue(chunks[0]["quote"])


if __name__ == "__main__":
    unittest.main()
