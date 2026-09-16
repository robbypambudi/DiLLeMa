import threading

from loguru import logger

from rag.embedding import BaseEmbeddingModel
from rag.embedding.default_embedding import DefaultEmbedding
from rag.embedding.linqai_embedding import LinqAIEmbedding


class EmbeddingFactory:
    def __init__(self, device: str = 'cpu'):
        logger.info('Initializing embedding factory')
        self.device = device
        self._instances = {}  # Cache model instances
        self._lock = threading.Lock()  # Protects cache for thread safety

    def get(self, model_name: str) -> BaseEmbeddingModel:
        # Return cached model if available
        with self._lock:
            if model_name in self._instances:
                return self._instances[model_name]
            # Otherwise create a new embedding instance
            if model_name == "LinqAI":
                model = LinqAIEmbedding(device=self.device)
            elif model_name == "Default":
                model = DefaultEmbedding(device=self.device)
            else:
                raise ValueError(f"Model {model_name} is not supported.")
            # Cache and return
            self._instances[model_name] = model
            return model
