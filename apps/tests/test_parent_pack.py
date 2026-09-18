import unittest

from app.services.retrieval_service import format_graph_evidence, pack_parent_pages


class ParentPackTests(unittest.TestCase):
    def test_same_page_leaves_collapse_to_one_parent(self):
        page = "Visi ITS 2026–2030. Pendanaan prudent."
        packed = pack_parent_pages(
            [
                ["q", "leaf a", {"file_id": "1", "file_name": "r.pdf", "page": 2, "page_text": page, "quote": "leaf a"}],
                ["q", "leaf b", {"file_id": "1", "file_name": "r.pdf", "page": 2, "page_text": page, "quote": "leaf b"}],
                ["q", "other", {"file_id": "1", "file_name": "r.pdf", "page": 5, "page_text": "Halaman lima.", "quote": "other"}],
            ]
        )
        self.assertEqual(len(packed), 2)
        self.assertIn(page, packed[0][1])
        self.assertEqual(packed[0][2]["page"], 2)
        self.assertEqual(packed[1][2]["page"], 5)

    def test_graph_claims_stay_separate_from_vector_pages(self):
        packed = pack_parent_pages(
            [
                ["q", "leaf", {"file_id": "1", "file_name": "r.pdf", "page": 2, "page_text": "Halaman."}],
                ["q", "klaim", {"file_id": "1", "file_name": "r.pdf", "page": 2, "claim_id": "abc", "quote": "q"}],
            ]
        )
        self.assertEqual(len(packed), 2)

    def test_graph_evidence_keeps_qualifiers(self):
        text = format_graph_evidence(
            {"statement": "A rule", "qualifiers": {"negated": True}, "quote": "quote"}
        )
        self.assertIn("Klaim: A rule", text)
        self.assertIn('"negated": true', text)


if __name__ == "__main__":
    unittest.main()
