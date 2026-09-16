from sentence_transformers import CrossEncoder


class ReRanking:
    """
    Re-ranks the results of a search query based on the relevance of the documents to the query.
    """

    def __init__(self, model_name: str = "cross-encoder/ms-marco-MiniLM-L-6-v2"):
        """
        Initializes the ReRanking class with a specified model name.

        Args:
            model_name (str): The name of the pre-trained model to use for re-ranking.
        """
        self.model = CrossEncoder(model_name)

    def rank(self, top_results: int = 3, pairs: list = None) -> list:
        """
        Ranks the given pairs of questions and answers based on their relevance.

        Args:
            top_results (int): The number of top results to return.
            pairs (list): A list of dictionaries containing question-answer pairs.

        Returns:
            list: A list of ranked question-answer pairs.
        """
        if not pairs:
            raise ValueError("Pairs cannot be None or empty.")

        scores = self.model.predict(pairs)
        sorted_pairs = sorted(zip(scores, pairs), key=lambda x: x[0], reverse=True)

        return [pair for _, pair in sorted_pairs[:top_results]]
