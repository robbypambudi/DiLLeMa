from qdrant_client import QdrantClient
from qdrant_client.models import (
    Distance,
    FieldCondition,
    Filter,
    Fusion,
    FusionQuery,
    MatchValue,
    Modifier,
    PayloadSchemaType,
    PointStruct,
    Prefetch,
    SparseVectorParams,
    VectorParams,
)
from loguru import logger
from uuid import NAMESPACE_URL, uuid5

from rag.embedding.sparse_bm25 import encode_sparse

DENSE_NAME = "dense"
SPARSE_NAME = "bm25"


class QdrantHttpClient:
    def __init__(self, host: str = "localhost", port: int = 6333):
        logger.info(f"Initializing Qdrant client with host: {host}, port: {port}")
        self.host = host
        self.port = port
        self.client = QdrantClient(host=self.host, port=self.port)

    def _layout(self, collection_name: str) -> str:
        info = self.client.get_collection(collection_name)
        vectors = info.config.params.vectors
        sparse = info.config.params.sparse_vectors or {}
        named_dense = isinstance(vectors, dict) and DENSE_NAME in vectors
        if named_dense and SPARSE_NAME in sparse:
            return "hybrid"
        if named_dense:
            return "named-dense"
        return "unnamed"

    def create_collection(
        self,
        collection_name: str,
        embedding_function=None,
        metadata=None,
        vector_size: int | None = None,
    ):
        try:
            collections = self.client.get_collections()
            existing_names = [col.name for col in collections.collections]
            size = vector_size or 768
            if collection_name in existing_names:
                logger.info("Collection '{}' already exists ({})", collection_name, self._layout(collection_name))
                return collection_name

            self.client.create_collection(
                collection_name=collection_name,
                vectors_config={
                    DENSE_NAME: VectorParams(size=size, distance=Distance.COSINE),
                },
                sparse_vectors_config={
                    SPARSE_NAME: SparseVectorParams(modifier=Modifier.IDF),
                },
            )
            try:
                self.client.create_payload_index(
                    collection_name=collection_name,
                    field_name="file_id",
                    field_schema=PayloadSchemaType.KEYWORD,
                )
            except Exception as index_error:
                logger.warning(
                    "Could not create file_id payload index on '{}': {}",
                    collection_name,
                    index_error,
                )
            logger.info("Created hybrid collection '{}'", collection_name)
            return collection_name
        except Exception as e:
            logger.error("Error creating collection '{}': {}", collection_name, e)
            raise

    def add_documents(
        self,
        collection_name: str,
        ids: list,
        documents: list,
        metadatas: list = None,
        embedding_function=None,
    ):
        if not embedding_function:
            logger.error("Embedding function is required for Qdrant")
            raise ValueError("Embedding function is required for Qdrant")

        try:
            embeddings = embedding_function(documents)
            layout = self._layout(collection_name)
            points = []
            for i, (doc_id, doc, embedding) in enumerate(zip(ids, documents, embeddings)):
                payload = {"document": doc}
                if metadatas and i < len(metadatas):
                    payload.update(metadatas[i])
                numeric_id = str(uuid5(NAMESPACE_URL, f"{collection_name}:{doc_id}"))
                dense = embedding.tolist() if hasattr(embedding, "tolist") else embedding
                if layout == "hybrid":
                    vector = {DENSE_NAME: dense, SPARSE_NAME: encode_sparse(doc)}
                elif layout == "named-dense":
                    vector = {DENSE_NAME: dense}
                else:
                    vector = dense
                points.append(PointStruct(id=numeric_id, vector=vector, payload=payload))

            self.client.upsert(collection_name=collection_name, points=points)
            logger.info("Added {} documents to '{}' ({})", len(documents), collection_name, layout)
        except Exception as e:
            logger.error("Error adding documents to Qdrant: {}", e)
            raise

    def search(
        self,
        collection_name: str,
        query_vector,
        limit: int = 20,
        query_text: str | None = None,
    ):
        """Dense search, or dense+BM25 RRF when the collection is hybrid."""
        try:
            layout = self._layout(collection_name)
        except Exception:
            layout = "unnamed"
        dense = query_vector.tolist() if hasattr(query_vector, "tolist") else query_vector
        try:
            if layout == "hybrid" and query_text:
                result = self.client.query_points(
                    collection_name=collection_name,
                    prefetch=[
                        Prefetch(query=dense, using=DENSE_NAME, limit=limit),
                        Prefetch(
                            query=encode_sparse(query_text),
                            using=SPARSE_NAME,
                            limit=limit,
                        ),
                    ],
                    query=FusionQuery(fusion=Fusion.RRF),
                    limit=limit,
                )
                return list(result.points)
            kwargs = {
                "collection_name": collection_name,
                "query": dense,
                "limit": limit,
            }
            if layout in {"hybrid", "named-dense"}:
                kwargs["using"] = DENSE_NAME
            return list(self.client.query_points(**kwargs).points)
        except Exception as exc:
            logger.warning("query_points failed ({}); falling back to search", type(exc).__name__)
            if layout in {"hybrid", "named-dense"}:
                return self.client.search(
                    collection_name=collection_name,
                    query_vector=dense,
                    using=DENSE_NAME,
                    limit=limit,
                )
            return self.client.search(
                collection_name=collection_name,
                query_vector=dense,
                limit=limit,
            )

    def query(self, collection_name: str, query_texts: list, n_results: int = 3, include: list = None):
        results = {"documents": [], "metadatas": [], "distances": []}
        for query_text in query_texts:
            search_result = self.client.search(
                collection_name=collection_name,
                query_vector=None,
                limit=n_results,
            )
            docs = [hit.payload.get("document", "") for hit in search_result]
            metas = [{k: v for k, v in hit.payload.items() if k != "document"} for hit in search_result]
            distances = [hit.score for hit in search_result]
            results["documents"].append(docs)
            results["metadatas"].append(metas)
            results["distances"].append(distances)
        return results

    def delete_collection(self, collection_name: str):
        try:
            self.client.delete_collection(collection_name)
            logger.info(f"Deleted collection '{collection_name}'.")
        except Exception as e:
            message = str(e).lower()
            if "not found" in message or "doesn't exist" in message or "does not exist" in message:
                logger.warning(f"Qdrant collection '{collection_name}' already absent: {e}")
                return
            logger.error(f"Failed to delete collection '{collection_name}': {e}")
            raise

    def delete_points_by_file_id(self, collection_name: str, file_id: str):
        try:
            self.client.delete(
                collection_name=collection_name,
                points_selector=Filter(
                    must=[FieldCondition(key="file_id", match=MatchValue(value=str(file_id)))]
                ),
            )
            logger.info(f"Deleted points for file {file_id} from '{collection_name}'.")
        except Exception as e:
            message = str(e).lower()
            if "not found" in message or "doesn't exist" in message or "does not exist" in message:
                logger.warning(f"Qdrant points for file {file_id} already absent: {e}")
                return
            logger.warning(f"Could not delete Qdrant points for file {file_id}: {e}")
            raise

    def get_documents(self, collection_name: str):
        try:
            result = self.client.scroll(collection_name=collection_name, limit=10000)
            points = result[0]
            return {
                "ids": [str(point.id) for point in points],
                "documents": [point.payload.get("document", "") for point in points],
                "metadatas": [
                    {k: v for k, v in point.payload.items() if k != "document"}
                    for point in points
                ],
            }
        except Exception as e:
            logger.error(f"Error getting documents from Qdrant: {e}")
            return {"ids": [], "documents": [], "metadatas": []}

    def heartbeat(self):
        try:
            self.client.get_collections()
            return True
        except Exception as e:
            logger.error(f"Qdrant heartbeat failed: {e}")
            return False
