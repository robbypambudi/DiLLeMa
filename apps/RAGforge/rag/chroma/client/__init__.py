# chromadb_client.py

import chromadb
from loguru import logger


class ChromaDBHttpClient:
    def __init__(self, host: str = "localhost", port: int = 9000):
        """
        Initialize ChromaDB HTTP client.
        """
        logger.info(f"Initializing ChromaDB client with host: {host}, port: {port}")
        self.host = host
        self.port = port
        self.client = chromadb.HttpClient(host=self.host, port=self.port)

    def create_collection(self, collection_name: str, embedding_function=None, metadata=None):
        return self.client.create_collection(name=collection_name, embedding_function=embedding_function,
                                             metadata=metadata)

    def add_documents(self, collection_name: str, ids: list, documents: list, metadatas: list = None,
                      embedding_function=None):
        """
        Add documents to a collection in ChromaDB.
        """
        collection = self.client.get_collection(collection_name)
        if not collection:
            logger.error(f"Collection '{collection_name}' does not exist.")
            return
        collection.add(
            ids=ids,
            documents=documents,
            metadatas=metadatas,
            embeddings=embedding_function(documents) if embedding_function else None
        )
        print(f"Added {len(documents)} documents to '{collection_name}'.")

    def query(self, collection_name: str, query_texts: list, n_results: int = 3, include: list = None):
        collection = self.client.get_collection(collection_name)
        return collection.query(query_texts=query_texts, n_results=n_results, include=include)

    def delete_collection(self, collection_name: str):
        collection = self.client.get_collection(collection_name)
        if collection:
            self.client.delete_collection(collection_name)
            print(f"Deleted collection '{collection_name}'.")
        else:
            print(f"Collection '{collection_name}' does not exist.")

    def get_documents(self, collection_name: str):
        collection = self.client.get_collection(collection_name)

        return collection.get()

    def heartbeat(self):
        """
        Check if the ChromaDB server is running.
        """
        try:
            self.client.heartbeat()
            return True
        except Exception as e:
            print(f"ChromaDB heartbeat failed: {e}")
            return False
