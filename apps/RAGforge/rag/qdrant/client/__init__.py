from qdrant_client import QdrantClient
from qdrant_client.models import Distance, FieldCondition, Filter, MatchValue, PayloadSchemaType, PointStruct, VectorParams
from loguru import logger
from uuid import NAMESPACE_URL, uuid5


class QdrantHttpClient:
    def __init__(self, host: str = "localhost", port: int = 6333):
        logger.info(f"Initializing Qdrant client with host: {host}, port: {port}")
        self.host = host
        self.port = port
        self.client = QdrantClient(host=self.host, port=self.port)

    def create_collection(self, collection_name: str, embedding_function=None, metadata=None):
        try:
            # Check if collection already exists
            collections = self.client.get_collections()
            existing_names = [col.name for col in collections.collections]
            
            if collection_name in existing_names:
                logger.info(f"Collection '{collection_name}' already exists")
                return collection_name
            
            vector_size = 768  # Default for sentence-transformers/all-mpnet-base-v2
            self.client.create_collection(
                collection_name=collection_name,
                vectors_config=VectorParams(size=vector_size, distance=Distance.COSINE),
            )
            try:
                self.client.create_payload_index(
                    collection_name=collection_name,
                    field_name="file_id",
                    field_schema=PayloadSchemaType.KEYWORD,
                )
            except Exception as index_error:
                logger.warning(f"Could not create file_id payload index on '{collection_name}': {index_error}")
            logger.info(f"Created collection '{collection_name}'")
            return collection_name
        except Exception as e:
            logger.error(f"Error creating collection '{collection_name}': {e}")
            raise

    def add_documents(self, collection_name: str, ids: list, documents: list, metadatas: list = None,
                      embedding_function=None):
        if not embedding_function:
            logger.error("Embedding function is required for Qdrant")
            raise ValueError("Embedding function is required for Qdrant")
        
        try:
            embeddings = embedding_function(documents)
            points = []
            
            for i, (doc_id, doc, embedding) in enumerate(zip(ids, documents, embeddings)):
                payload = {"document": doc}
                if metadatas and i < len(metadatas):
                    payload.update(metadatas[i])
                
                # Stable across interpreter restarts and retries.
                numeric_id = str(uuid5(NAMESPACE_URL, f"{collection_name}:{doc_id}"))
                
                points.append(PointStruct(
                    id=numeric_id,
                    vector=embedding.tolist() if hasattr(embedding, 'tolist') else embedding,
                    payload=payload
                ))
            
            self.client.upsert(collection_name=collection_name, points=points)
            logger.info(f"Added {len(documents)} documents to '{collection_name}'.")
        except Exception as e:
            logger.error(f"Error adding documents to Qdrant: {e}")
            raise

    def query(self, collection_name: str, query_texts: list, n_results: int = 3, include: list = None):
        # For Qdrant, we need embeddings for the query
        # This assumes embedding function is available in the calling context
        results = {"documents": [], "metadatas": [], "distances": []}
        
        for query_text in query_texts:
            search_result = self.client.search(
                collection_name=collection_name,
                query_vector=None,  # Will be set by caller with embeddings
                limit=n_results
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
                "metadatas": [{k: v for k, v in point.payload.items() if k != "document"} for point in points]
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
