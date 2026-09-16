from langchain_text_splitters import RecursiveCharacterTextSplitter
from langchain_text_splitters import SentenceTransformersTokenTextSplitter
from loguru import logger


class DocumentChunker:
    """
    This class is responsible for chunking documents into smaller pieces.
    """

    def __init__(self, chunk_size: int = 1000, chunk_overlap: int = 100):
        self.chunk_size = chunk_size
        self.chunk_overlap = chunk_overlap
        self.text_splitter = RecursiveCharacterTextSplitter(
            chunk_size=self.chunk_size,
            chunk_overlap=self.chunk_overlap,
            separators=["\n\n", "\n", ".", " "],
        )
        self.token_splitter = SentenceTransformersTokenTextSplitter(
            chunk_size=384,
            chunk_overlap=0,
        )
        logger.info(
            f"DocumentChunker initialized with chunk_size: {self.chunk_size}, chunk_overlap: {self.chunk_overlap}")

    def chunk_text(self, text: str) -> list:
        """
        Chunk the input text into smaller pieces.
        :param text: The input text to be chunked.
        :return: A list of chunked texts.
        """
        chunks = self.text_splitter.split_text(text)
        token_split_chunks = []
        for chunk in chunks:
            token_split_chunks.extend(self.token_splitter.split_text(chunk))
        return token_split_chunks
