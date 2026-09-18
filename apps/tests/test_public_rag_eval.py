"""Metric checks: no models, downloads or live services."""

import unittest

from evaluation.public_rag_eval import evidence_metrics, score_answer


class PublicRagMetricTests(unittest.TestCase):
    def setUp(self):
        self.row = {"source_id": "gold", "answers": {"text": ["12 November 2027"]}}

    def test_answer_string_in_wrong_source_is_not_a_retrieval_hit(self):
        result = evidence_metrics(
            self.row, [["q", "12 November 2027", {"source_id": "wrong"}]]
        )
        self.assertFalse(result["answer_hit"])
        self.assertEqual(result["rr"], 0)

    def test_source_without_answer_does_not_count_as_answer_hit(self):
        result = evidence_metrics(
            self.row, [["q", "Biaya pendaftaran", {"source_id": "gold"}]]
        )
        self.assertTrue(result["source_hit"])
        self.assertFalse(result["answer_hit"])

    def test_rank_and_empty_evidence(self):
        result = evidence_metrics(
            self.row,
            [
                ["q", "Tanggal lain", {"source_id": "wrong"}],
                ["q", "Tanggalnya 12 November 2027.", {"source_id": "gold"}],
            ],
        )
        self.assertTrue(result["answer_hit"])
        self.assertEqual(result["rr"], 0.5)
        self.assertEqual(result["source_precision"], 0.5)
        self.assertFalse(evidence_metrics(self.row, [])["answer_hit"])

    def test_generation_scoring_uses_best_alias_and_counts_extra_words(self):
        self.assertEqual(
            score_answer("12 November 2027.", ["November", "12 November 2027"])[
                "exact_match"
            ],
            1,
        )
        score = score_answer("Tanggal 12 November 2027", ["12 November 2027"])
        self.assertEqual(score["exact_match"], 0)
        self.assertAlmostEqual(score["token_f1"], 6 / 7)
        self.assertEqual(score_answer("", ["12 November 2027"])["token_f1"], 0)


if __name__ == "__main__":
    unittest.main()
