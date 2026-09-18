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




class WeakEvidenceTests(unittest.TestCase):
    def test_evidence_far_below_the_best_match_is_dropped(self):
        from app.services.retrieval_service import drop_weak_evidence

        pairs = [
            ["q", "kode EF234202", {"page": 29, "rerank_score": 0.99}],
            ["q", "halaman lanjutan", {"page": 30, "rerank_score": 0.68}],
            ["q", "mata kuliah lain", {"page": 95, "rerank_score": 0.28}],
        ]
        kept = drop_weak_evidence(pairs, 0.5)
        self.assertEqual([pair[2]["page"] for pair in kept], [29, 30])

    def test_unscored_evidence_and_a_zero_ratio_keep_everything(self):
        from app.services.retrieval_service import drop_weak_evidence

        pairs = [["q", "a", {"page": 1}], ["q", "b", {"page": 2}]]
        self.assertEqual(drop_weak_evidence(pairs, 0.5), pairs)
        scored = [["q", "a", {"rerank_score": 0.9}], ["q", "b", {"rerank_score": 0.1}]]
        self.assertEqual(drop_weak_evidence(scored, 0.0), scored)

if __name__ == "__main__":
    unittest.main()
