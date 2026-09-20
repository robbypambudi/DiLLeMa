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

    def test_a_split_table_keeps_the_group_its_rows_belong_to(self):
        """Rows cut away from `| SEMESTER 3 |` must not lose which semester.

        Measured on the live index before this: the course list was cut so
        that four semester-3 courses sat under a chunk whose only visible
        label was SEMESTER 4, and "apa saja matakuliah semester 3" could not
        reach them.
        """
        table = "\n".join(
            [
                "COURSE LIST OF BACHELOR PROGRAM",
                "| Course Code | Course Name | Credit |",
                "| SEMESTER 2 |",
                "| SM234201 | Calculus 2 | 3 |",
                "| SEMESTER 3 |",
                "| EF234301 | Discrete Mathematics | 3 |",
                "| EF234302 | Object Oriented Programming | 4 |",
                "| EF234307 | Software Development Principles | 2 |",
                "| SEMESTER 4 |",
                "| EF234401 | Network Programming | 3 |",
            ]
        )
        chunker = DocumentChunker(chunk_size=200, chunk_overlap=0, min_chunk_chars=10)
        chunks = chunker.chunk_sections([(4, "", table, "4")])
        for course in ("Discrete Mathematics", "Software Development Principles"):
            owning = [item["text"] for item in chunks if course in item["text"]]
            self.assertTrue(owning, course)
            self.assertTrue(
                any("SEMESTER 3" in text for text in owning),
                f"{course} lost its semester",
            )
        # The stranded rows are carried under SEMESTER 3, never mislabelled
        # with the group that happened to be in force before the cut.
        stranded = next(
            item["text"]
            for item in chunks
            if "Software Development Principles" in item["text"]
        )
        self.assertIn("SEMESTER 3", stranded)
        self.assertNotIn("SEMESTER 2", stranded)

    def test_plain_text_still_chunks_without_page(self):
        chunker = DocumentChunker(chunk_size=20, chunk_overlap=0)
        chunks = chunker.chunk_sections([(None, "", "Alpha. Beta. Gamma.")], file_name="note.txt")
        self.assertTrue(chunks)
        self.assertIsNone(chunks[0]["page"])
        self.assertTrue(chunks[0]["quote"])


if __name__ == "__main__":
    unittest.main()
