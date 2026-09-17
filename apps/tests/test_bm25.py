import unittest

from rag.embedding.sparse_bm25 import encode_sparse, tokenize


class SparseBm25Tests(unittest.TestCase):
    def test_indices_are_sorted_and_unique(self):
        vector = encode_sparse("RENSTRA ITS 2026 2026 pendanaan prudent")
        self.assertEqual(vector.indices, sorted(vector.indices))
        self.assertEqual(len(vector.indices), len(set(vector.indices)))
        self.assertEqual(len(vector.indices), len(vector.values))
        self.assertGreater(len(vector.indices), 3)

    def test_repeated_terms_raise_frequency(self):
        once = encode_sparse("visi visi")
        self.assertEqual(tokenize("visi visi"), ["visi", "visi"])
        self.assertEqual(len(once.indices), 1)
        self.assertEqual(once.values[0], 2.0)

    def test_empty_text_is_empty_sparse_vector(self):
        vector = encode_sparse("  ")
        self.assertEqual(vector.indices, [])
        self.assertEqual(vector.values, [])


if __name__ == "__main__":
    unittest.main()
