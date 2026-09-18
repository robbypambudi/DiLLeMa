"""What gets indexed, and what a question is searched with."""

import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock
from uuid import uuid4

from agents.augment_query_generated import AugmentQueryGenerated, clean_queries
from rag.embedding.sparse_bm25 import encode_sparse
from rag.nlp.doc_chunking import DocumentChunker
from rag.nlp.doc_parse import Section, document_pages, read_sections
from rag.nlp.boilerplate import strip_boilerplate
from rag.nlp.stemmer import stem
from rag.nlp.structure import split_structure

PASAL = (
    "Pasal 12\n"
    "Pagu penelitian ditetapkan oleh rektor setiap tahun anggaran berjalan.\n"
)


def write_pdf(lines, path, table=None):
    import pymupdf

    document = pymupdf.open()
    page = document.new_page()
    for index, line in enumerate(lines):
        page.insert_text((60, 80 + index * 20), line, fontsize=11)
    if table:
        top, height, columns = 200, 24, (60, 200, 340)
        for index, row in enumerate(table):
            y = top + index * height
            for column, cell in enumerate(row):
                page.insert_text((columns[column] + 6, y + 16), cell, fontsize=10)
            page.draw_line((columns[0], y), (columns[-1] + 100, y))
        for x in (*columns, columns[-1] + 100):
            page.draw_line((x, top), (x, top + len(table) * height))
        page.draw_line(
            (columns[0], top + len(table) * height),
            (columns[-1] + 100, top + len(table) * height),
        )
    if len(lines) > 1:
        document.new_page()  # a scanned page: no extractable text
    document.save(path)
    document.close()


class StemmedLexicalMatchTests(unittest.TestCase):
    def test_affix_forms_share_index_terms(self):
        question = encode_sparse("penetapan pendanaan")
        passage = encode_sparse("ditetapkan dan mendanai")
        # Every term the question asks for is a term the passage carries;
        # function words are left in for Qdrant's IDF to discount.
        self.assertTrue(set(question.indices) <= set(passage.indices))

    def test_acronyms_and_numbers_are_left_alone(self):
        self.assertEqual(stem("2026"), "2026")
        self.assertEqual(stem("ITS"), "ITS")
        self.assertEqual(stem("P3"), "P3")

    def test_unrelated_words_stay_apart(self):
        self.assertFalse(
            set(encode_sparse("anggaran").indices)
            & set(encode_sparse("kurikulum").indices)
        )


class BoilerplateTests(unittest.TestCase):
    def setUp(self):
        self.pages = [
            f"RENSTRA ITS 2026-2030\nIsi halaman {index} tentang pendanaan.\n{index + 10}"
            for index in range(1, 5)
        ]

    def test_running_headers_and_page_numbers_leave_the_index(self):
        cleaned = strip_boilerplate(self.pages)
        self.assertEqual(cleaned[0], "Isi halaman 1 tentang pendanaan.")
        self.assertTrue(all("RENSTRA ITS" not in page for page in cleaned))

    def test_a_document_too_short_to_show_a_pattern_is_untouched(self):
        self.assertEqual(strip_boilerplate(self.pages[:2]), self.pages[:2])

    def test_body_text_that_merely_repeats_is_kept(self):
        pages = [
            f"Judul {index}\nKetentuan ini berlaku bagi seluruh unit kerja.\nPenutup {index}"
            for index in range(1, 5)
        ]
        self.assertTrue(
            all("berlaku bagi seluruh unit kerja" in page for page in strip_boilerplate(pages))
        )


class StructureTests(unittest.TestCase):
    def test_a_clause_is_not_split_across_headings(self):
        blocks = split_structure("BAB I Umum\nIsi bab.\n" + PASAL)
        self.assertEqual([heading for heading, _ in blocks], ["BAB I Umum", "Pasal 12"])
        self.assertIn("rektor", blocks[1][1])

    def test_a_numbered_sentence_is_not_a_heading(self):
        blocks = split_structure("1. Rektor menetapkan pagu penelitian setiap tahun.")
        self.assertEqual([heading for heading, _ in blocks], [""])

    def test_unstructured_text_stays_one_block(self):
        self.assertEqual(split_structure("Paragraf biasa."), [("", "Paragraf biasa.")])


class ChunkContentTests(unittest.TestCase):
    def setUp(self):
        self.chunks = DocumentChunker(chunk_size=200, chunk_overlap=0).chunk_sections(
            [Section(4, "", "BAB II Arah Kebijakan\nPembukaan bab.\n" + PASAL, "iv")]
        )

    def test_the_file_name_and_page_are_not_indexed_with_the_text(self):
        # They repeat in every chunk of a file, so they match the whole document
        # at once instead of the passage that answers the question.
        for chunk in self.chunks:
            self.assertNotIn("halaman", chunk["text"])
            self.assertNotIn("iv", chunk["text"].split("\n")[0].lower())

    def test_the_heading_is_indexed_and_recorded_as_the_section(self):
        clause = next(chunk for chunk in self.chunks if "rektor" in chunk["text"])
        self.assertEqual(clause["section"], "Pasal 12")
        self.assertIn("Pasal 12", clause["text"])

    def test_a_heading_alone_is_not_indexed(self):
        self.assertFalse([chunk for chunk in self.chunks if chunk["quote"] == "Pasal 12"])

    def test_quotes_stay_verbatim_slices_of_the_page(self):
        for chunk in self.chunks:
            self.assertIn(chunk["quote"][:60], chunk["page_text"])

    def test_markdown_headings_and_clause_headings_combine(self):
        chunks = DocumentChunker().chunk_sections([Section(None, "Bab I", PASAL)])
        self.assertEqual(chunks[0]["section"], "Bab I / Pasal 12")


class PdfExtractionTests(unittest.TestCase):
    def test_table_rows_survive_extraction(self):
        with tempfile.TemporaryDirectory() as directory:
            path = str(Path(directory) / "table.pdf")
            write_pdf(
                ["Tabel 3.1 Pagu per fakultas"],
                path,
                table=[("Fakultas", "2026"), ("Teknik", "12")],
            )
            text = read_sections(path, "application/pdf")[0].text
        # Read line by line, a table becomes a column of stray numbers.
        self.assertRegex(text, r"Teknik\s*\|\s*12")

    def test_pages_without_text_are_reported_not_silently_dropped(self):
        with tempfile.TemporaryDirectory() as directory:
            path = str(Path(directory) / "scan.pdf")
            write_pdf(["Halaman pertama.", "Baris kedua."], path)
            sections = read_sections(path, "application/pdf")
            total = document_pages(path, "application/pdf")
        self.assertEqual([section.page for section in sections], [1])
        self.assertEqual(total, 2)

    def test_a_pdf_without_any_text_fails_loudly(self):
        with tempfile.TemporaryDirectory() as directory:
            path = str(Path(directory) / "empty.pdf")
            write_pdf([], path)
            with self.assertRaises(ValueError):
                read_sections(path, "application/pdf")


class QueryAugmentationTests(unittest.TestCase):
    def test_only_labelled_rewrites_become_searches(self):
        queries = clean_queries(
            "Apa saja mata kuliah pilihan?",
            "<think>menerjemahkan</think>\n"
            "Berikut adalah daftar mata kuliah pilihan:\n"
            "1. Sistem Informasi\n"
            "EN: What are the elective courses?\n"
            "ID: mata kuliah pilihan\n"
            "KEY: elective courses\n"
            "KEY: elective courses",
        )
        # The answer the model made up is not a search; keyword lines are,
        # although they are not questions.
        self.assertEqual(
            queries,
            [
                "Apa saja mata kuliah pilihan?",
                "What are the elective courses?",
                "mata kuliah pilihan",
                "elective courses",
            ],
        )

    def test_a_rewrite_equal_to_the_question_is_not_searched_twice(self):
        self.assertEqual(clean_queries("tujuan ITS", "ID: Tujuan ITS\nEN: x"), ["tujuan ITS"])

    def test_the_search_budget_is_capped(self):
        generated = "\n".join(f"KEY: kata kunci nomor {index}" for index in range(9))
        self.assertEqual(len(clean_queries("Asli?", generated)), 4)

    def test_a_failed_generator_leaves_the_original_question_searchable(self):
        augmenter = object.__new__(AugmentQueryGenerated)
        augmenter.openai = Mock()
        augmenter.openai.client.chat.completions.create.side_effect = RuntimeError("down")
        self.assertEqual(augmenter.augment("Berapa anggaran?"), ["Berapa anggaran?"])


class MultiQueryRerankTests(unittest.TestCase):
    def reranker(self):
        from rag.llm.re_rank import ReRanking

        reranker = object.__new__(ReRanking)
        reranker.model = Mock()
        # Scores an English passage well only against the English rewrite.
        reranker.model.predict.side_effect = lambda batch: [
            0.9 if query.startswith("What") and "elective" in text else 0.1
            for query, text in batch
        ]
        return reranker

    def test_a_passage_keeps_its_best_score_across_rewrites(self):
        pairs = [["Apa mata kuliah pilihan?", "LIST OF ELECTIVE COURSES elective", {}]]
        ranked = self.reranker().rank(
            pairs=pairs,
            top_results=1,
            queries=["Apa mata kuliah pilihan?", "What are the elective courses?"],
        )
        self.assertEqual(ranked[0][2]["rerank_score"], 0.9)

    def test_the_original_question_alone_is_scored_as_before(self):
        pairs = [["Apa mata kuliah pilihan?", "LIST OF ELECTIVE COURSES elective", {}]]
        ranked = self.reranker().rank(pairs=pairs, top_results=1)
        self.assertEqual(ranked[0][2]["rerank_score"], 0.1)


class AugmentationDefaultTests(unittest.TestCase):
    def service(self):
        from app.services.retrieval_service import RetrievalService

        collections = Mock()
        augmenter = Mock()
        augmenter.augment.return_value = ["q"]
        qdrant = Mock()
        qdrant.search.return_value = []
        embedding = Mock()
        embedding.encode.return_value = [0.1]
        return RetrievalService(collections, qdrant, augmenter, None, embedding), augmenter

    def payload(self):
        return Mock(collection_id=uuid4(), question_text="q")

    def test_an_unset_request_follows_the_setting(self):
        from app.core.config import settings

        service, augmenter = self.service()
        with unittest.mock.patch.object(settings, "QUERY_AUGMENTATION", True):
            service.retrieve(self.payload(), using_augment_query=None)
        augmenter.augment.assert_called_once()
        service, augmenter = self.service()
        with unittest.mock.patch.object(settings, "QUERY_AUGMENTATION", False):
            service.retrieve(self.payload(), using_augment_query=None)
        augmenter.augment.assert_not_called()

    def test_an_explicit_request_overrides_the_setting(self):
        from app.core.config import settings

        service, augmenter = self.service()
        with unittest.mock.patch.object(settings, "QUERY_AUGMENTATION", True):
            service.retrieve(self.payload(), using_augment_query=False)
        augmenter.augment.assert_not_called()


class IngestionCoverageTests(unittest.TestCase):
    def test_indexed_page_count_is_recorded_against_the_document(self):
        from app.pipeline.pipeline_service import PipelineService

        with tempfile.TemporaryDirectory() as directory:
            path = str(Path(directory) / "scan.pdf")
            write_pdf(["Halaman pertama.", "Baris kedua."], path)
            files = Mock()
            files.get_collection_name.return_value = "Pilot"
            files.get_vectordb_collection_name.return_value = "pilot"
            source = Mock(
                id=uuid4(),
                collection_id=uuid4(),
                file_path=path,
                file_type="application/pdf",
                file_name="scan.pdf",
            )
            embedding = Mock()
            embedding.encode.return_value = [[0.1]]
            PipelineService(files, Mock(), None, embedding).run_pipeline(source)

        completed = files.update_fields.call_args.args[1]
        self.assertEqual(completed["status"], "completed")
        self.assertEqual(completed["metadatas"]["pages_total"], 2)
        self.assertEqual(completed["metadatas"]["pages_indexed"], 1)


class ReindexTests(unittest.TestCase):
    """Indexing changes only reach a document that is indexed again."""

    def service(self, status):
        from app.services.files_service import FilesService

        files = Mock()
        files.read_by_id.return_value = Mock(
            id=uuid4(), status=status, collection_id=uuid4()
        )
        collections = Mock()
        vectors = Mock()
        return FilesService(files, collections, vectors), files, vectors

    def test_a_finished_document_can_be_reindexed(self):
        service, files, vectors = self.service("completed")
        service.retry(files.read_by_id.return_value.id)
        vectors.delete_points_by_file_id.assert_called_once()
        self.assertEqual(files.update_fields.call_args.args[1]["status"], "pending")

    def test_a_document_still_being_processed_is_not_touched(self):
        from app.core.exceptions import ConflictError

        service, files, _ = self.service("processing")
        with self.assertRaises(ConflictError):
            service.retry(files.read_by_id.return_value.id)


if __name__ == "__main__":
    unittest.main()
