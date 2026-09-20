import unittest

from app.services.retrieval_service import format_graph_evidence, pack_parent_pages


class ParentPackTests(unittest.TestCase):
    def test_same_page_leaves_collapse_to_one_parent(self):
        page = "Visi ITS 2026–2030. Pendanaan prudent."
        packed = pack_parent_pages(
            [
                [
                    "q",
                    "leaf a",
                    {
                        "file_id": "1",
                        "file_name": "r.pdf",
                        "page": 2,
                        "page_text": page,
                        "quote": "leaf a",
                    },
                ],
                [
                    "q",
                    "leaf b",
                    {
                        "file_id": "1",
                        "file_name": "r.pdf",
                        "page": 2,
                        "page_text": page,
                        "quote": "leaf b",
                    },
                ],
                [
                    "q",
                    "other",
                    {
                        "file_id": "1",
                        "file_name": "r.pdf",
                        "page": 5,
                        "page_text": "Halaman lima.",
                        "quote": "other",
                    },
                ],
            ]
        )
        self.assertEqual(len(packed), 2)
        self.assertIn(page, packed[0][1])
        self.assertIn("leaf a", packed[0][1])
        self.assertIn("leaf b", packed[0][1])
        self.assertEqual(packed[0][2]["page"], 2)
        self.assertEqual(packed[1][2]["page"], 5)

    def test_graph_claims_stay_separate_from_vector_pages(self):
        packed = pack_parent_pages(
            [
                [
                    "q",
                    "leaf",
                    {
                        "file_id": "1",
                        "file_name": "r.pdf",
                        "page": 2,
                        "page_text": "Halaman.",
                    },
                ],
                [
                    "q",
                    "klaim",
                    {
                        "file_id": "1",
                        "file_name": "r.pdf",
                        "page": 2,
                        "claim_id": "abc",
                        "quote": "q",
                    },
                ],
            ]
        )
        self.assertEqual(len(packed), 2)

    def test_graph_evidence_keeps_qualifiers(self):
        text = format_graph_evidence(
            {"statement": "A rule", "qualifiers": {"negated": True}, "quote": "quote"}
        )
        self.assertIn("Klaim: A rule", text)
        self.assertIn('"negated": true', text)

    def test_legacy_unpaginated_sections_do_not_collapse(self):
        pairs = [
            [
                "q",
                "Biaya 100 rupiah.",
                {"file_id": "1", "section": "Biaya", "page": None},
            ],
            [
                "q",
                "Batas waktu 12 November.",
                {"file_id": "1", "section": "Tanggal", "page": None},
            ],
        ]
        self.assertEqual(len(pack_parent_pages(pairs)), 2)

    def test_parent_limit_does_not_skip_later_leaf_of_selected_parent(self):
        pairs = [
            ["q", "Aturan awal.", {"file_id": "1", "page": 1}],
            ["q", "Halaman lain.", {"file_id": "1", "page": 2}],
            [
                "q",
                "Pengecualian yang wajib dipertahankan.",
                {"file_id": "1", "page": 1},
            ],
        ]
        packed = pack_parent_pages(pairs, max_pages=1)
        self.assertEqual(len(packed), 1)
        self.assertIn("Pengecualian", packed[0][1])
        self.assertNotIn("Halaman lain", packed[0][1])

    def test_long_legacy_page_never_replaces_full_leaf_with_short_quote(self):
        leaf = "rincian " * 60 + "JAWABAN_DI_AKHIR"
        packed = pack_parent_pages(
            [
                [
                    "q",
                    leaf,
                    {
                        "file_id": "1",
                        "page": 1,
                        "page_text": "awal " * 1000,
                        "quote": leaf[:350],
                    },
                ]
            ]
        )
        self.assertIn(leaf, packed[0][1])
        self.assertLess(len(packed[0][1]), 5000)

    def test_versions_and_anonymous_sources_do_not_merge(self):
        pairs = [
            [
                "q",
                "Aturan lama.",
                {"file_id": "1", "page": 1, "document_version": "old"},
            ],
            [
                "q",
                "Aturan baru.",
                {"file_id": "1", "page": 1, "document_version": "new"},
            ],
            ["q", "Sumber tanpa nama pertama.", {}],
            ["q", "Sumber tanpa nama kedua.", {}],
        ]
        self.assertEqual(len(pack_parent_pages(pairs)), 4)
        self.assertEqual(pack_parent_pages(pairs, max_pages=0), [])


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
