class Query:
    """
    A class to represent a query for a document retrieval system.
    """

    def __init__(self, text: str):
        """
        Initialize the Query object with the given text.

        Args:
            text (str): The text of the query.
        """
        self.text = text
