from datetime import datetime
from functools import cached_property

from loguru import logger

from app.core.config import settings
from app.models.files import Files
from app.repositories.files_repository import FilesRepository
from rag.nlp.doc_parse import document_pages, read_sections
from rag.qdrant.client import QdrantHttpClient


class PipelineService:
    def __init__(
        self,
        files_repository: FilesRepository,
        qdrant_client: QdrantHttpClient,
        knowledge_repository=None,
        embedding_model=None,
        doc_chunker=None,
    ):
        self.file_repository = files_repository
        self.qdrant_client = qdrant_client
        self.knowledge_repository = knowledge_repository
        if embedding_model is not None:
            self.embedding_model = embedding_model
        if doc_chunker is not None:
            self.doc_chunker = doc_chunker

    @cached_property
    def doc_chunker(self):
        from rag.nlp.doc_chunking import DocumentChunker

        return DocumentChunker()

    @cached_property
    def embedding_model(self):
        from rag.embedding.default_embedding import DefaultEmbedding
        from rag.embedding.device import embedding_device

        return DefaultEmbedding(device=embedding_device())

    def run_pipeline(self, files: Files):
        """
        Run the pipeline with the given ID.
        """
        # Update the file status to processing
        logger.info("Starting pipeline for file: {}", files.id)
        try:
            self.file_repository.update_fields(
                files.id,
                {"status": "processing", "processing_started_at": datetime.now()},
            )
            logger.info("Updated file status to processing for file: {}", files.id)

            sections = read_sections(files.file_path, files.file_type)
            chunks = self.doc_chunker.chunk_sections(sections, file_name=files.file_name)
            if not chunks:
                raise ValueError(f"No indexable text in file {files.id}")
            logger.info("Chunked {} sections into {} windows for {}", len(sections), len(chunks), files.id)
            pages_total = document_pages(files.file_path, files.file_type)
            pages_indexed = len({unit[0] for unit in sections if unit[0] is not None})

            # Query the collection name from the database
            collection_name = self.file_repository.get_collection_name(
                files.collection_id
            )
            vectordb_collection_name = (
                self.file_repository.get_vectordb_collection_name(files.collection_id)
            )

            logger.info("Collection name for file {}: {}", files.id, collection_name)
            if not collection_name:
                raise ValueError(f"Collection with ID {files.collection_id} not found.")
            # Add chunks to Qdrant.
            ids = [str(files.id) + "_" + str(i) for i in range(len(chunks))]
            documents = [item["text"] for item in chunks]
            metadata = [
                {
                    "file_name": files.file_name,
                    "file_id": str(files.id),
                    "page": item["page"],
                    "page_label": item.get("page_label"),
                    "section": item["section"],
                    "quote": item["quote"],
                    "page_text": item["page_text"],
                }
                for item in chunks
            ]
            logger.info("Preparing to add chunks to Qdrant for file: {}", files.id)
            self.qdrant_client.add_documents(
                ids=ids,
                documents=documents,
                metadatas=metadata,
                collection_name=vectordb_collection_name,
                embedding_function=self.embedding_model.encode,
            )
            logger.info("Added chunks to Qdrant for file: {}", files.id)
            # Update the file status to completed
            self.file_repository.update_fields(
                files.id,
                {
                    "status": "completed",
                    "metadatas": {
                        "collection_name": collection_name,
                        "chunk_count": len(chunks),
                        "chunk_size": self.doc_chunker.chunk_size,
                        "chunk_overlap": self.doc_chunker.chunk_overlap,
                        # Pages without extractable text are skipped, not
                        # fatal; the gap is recorded so it can be seen.
                        "pages_total": pages_total,
                        "pages_indexed": pages_indexed if pages_total else None,
                    },
                    "processing_ended_at": datetime.now(),
                },
            )
            if settings.KG_ENABLED and self.knowledge_repository:
                try:
                    if self.knowledge_repository.get_profile(
                        files.collection_id
                    ).enabled:
                        self.knowledge_repository.enqueue(files.collection_id, files.id)
                except Exception as exc:
                    logger.warning(
                        "File indexed, but knowledge enqueue failed for {} ({})",
                        files.id,
                        type(exc).__name__,
                    )

        except Exception as e:
            logger.error("Error processing file {}: {}", files.id, str(e))
            logger.exception("Full traceback:")
            try:
                self.file_repository.update_fields(
                    files.id,
                    {"status": "failed", "processing_ended_at": datetime.now()},
                )
            except Exception:
                logger.warning(
                    "Could not mark file {} as failed (row may have been deleted)",
                    files.id,
                )
