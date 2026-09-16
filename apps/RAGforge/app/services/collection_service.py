from sentence_transformers import SentenceTransformer
from asyncpg import NotNullViolationError

from app.core.config import settings
from app.core.exceptions import ValidationError
from app.repositories import CollectionsRepository
from app.schema.collection_schema import CreateCollectionRequest
from app.services.base_service import BaseService
from rag.qdrant.client import QdrantHttpClient


class CollectionsService(BaseService):
    """
    Collection service class for handling collection-related operations.
    """
    embedding_model = SentenceTransformer("sentence-transformers/all-mpnet-base-v2")

    def __init__(self, collections_repository: CollectionsRepository, qdrant_client: QdrantHttpClient,
                 embedding_model) -> None:
        self.collections_repository = collections_repository
        self.embedding_model = embedding_model
        self.qdrant_client = qdrant_client
        super().__init__(collections_repository)

    def create(self, payload: CreateCollectionRequest) -> CreateCollectionRequest:
        """
        Create a new collection with the given name. Creates ChromaDB collection and saves to repository.
        If ChromaDB creation fails, repository record is deleted.
        """

        collection = self.collections_repository.create(payload)
        try:
            self.qdrant_client.create_collection(
                collection_name=collection.vectordb_collection_name
            )
            return collection
        except Exception as e:
            self.collections_repository.delete_by_id(collection.id)
            raise ValidationError(detail=f"Collection creation failed: {str(e)}")

    def get_documents(self, collection_name: str) -> list:
        """
        Get documents from a collection in ChromaDB.
        """
        try:
            collection = self.collections_repository.get_by_name(collection_name)
            documents = self.qdrant_client.get_documents(
                collection_name=collection.vectordb_collection_name,
            )
            return documents
        except Exception as e:
            raise e

    def delete_collection(self, collection_name: str) -> None:
        """
        Delete a collection from ChromaDB and the repository.
        """
        try:
            collection = self.collections_repository.get_by_name(collection_name)
            self.collections_repository.delete_by_id(collection.id)
            self.qdrant_client.delete_collection(collection_name=collection.vectordb_collection_name)
        except NotNullViolationError as e:
            raise ValidationError(detail=f"Collection name '{collection_name}' is invalid. {str(e)}")
        except Exception as e:
            raise e
