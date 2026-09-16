from abc import ABC, abstractmethod
from typing import List

import numpy as np


class BaseEmbeddingModel(ABC):
    @abstractmethod
    def encode(self, text: str) -> np.ndarray:
        """Encode a single text into a vector."""
        pass

    @abstractmethod
    def encode_queries(self, texts: List[str]) -> np.ndarray:
        """Encode a list of texts (queries) into a 2D array of vectors."""
        pass
