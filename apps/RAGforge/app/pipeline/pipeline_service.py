from datetime import datetime

from sentence_transformers import SentenceTransformer
from loguru import logger
from pypdf import PdfReader
import pypandoc

# Ensure pandoc is available
try:
    pypandoc.get_pandoc_version()
except OSError:
    logger.warning("Pandoc not found. Downloading pandoc...")
    pypandoc.download_pandoc()
    logger.info("Pandoc downloaded successfully")

from app.core.config import settings
from app.models.files import Files
from app.repositories.files_repository import FilesRepository
from rag.qdrant.client import QdrantHttpClient
from rag.nlp.doc_chunking import DocumentChunker
from rag.nlp.doc_cleaner import DocumentCleaner


def read_file(file_path: str, file_type: str):
    """
    Read a file and return its content based on file type.
    """
    try:
        if file_type == "application/pdf":
            reader = PdfReader(file_path)
            text = ""
            for page in reader.pages:
                text += page.extract_text()
            return text
        
        elif file_type == "application/vnd.openxmlformats-officedocument.wordprocessingml.document" or file_path.endswith(".docx"):
            return pypandoc.convert_file(file_path, 'md')
        
        elif file_type.startswith("text/"):
            with open(file_path, "r", encoding="utf-8") as f:
                return f.read()
        else:
            # Try to read as text for other file types
            with open(file_path, "r", encoding="utf-8") as f:
                return f.read()
    except Exception as e:
        logger.error("Error reading file {}: {}", file_path, e)
        raise


class PipelineService:
    doc_cleaner = DocumentCleaner()
    doc_chunker = DocumentChunker()
    embedding_model = SentenceTransformer("sentence-transformers/all-mpnet-base-v2")

    def __init__(self, files_repository: FilesRepository, qdrant_client: QdrantHttpClient):
        self.file_repository = files_repository
        self.qdrant_client = qdrant_client

    def run_pipeline(self, files: Files):
        """
        Run the pipeline with the given ID.
        """
        # Update the file status to processing
        logger.info("Starting pipeline for file: {}", files.id)
        try:
            self.file_repository.update(
                id=files.id,
                schema=Files(
                    status="processing",
                    processing_started_at=datetime.now()
                )
            )
            logger.info("Updated file status to processing for file: {}", files.id)

            # Read file content based on file type
            clean_text = read_file(files.file_path, files.file_type)
            logger.info("Cleaned text for file: {}", files.id)
            chunks = self.doc_chunker.chunk_text(clean_text)
            logger.info("Chunked text for file: {}", files.id)

            # Query the collection name from the database
            collection_name = self.file_repository.get_collection_name(files.collection_id)
            vectordb_collection_name = self.file_repository.get_vectordb_collection_name(files.collection_id)

            logger.info("Collection name for file {}: {}", files.id, collection_name)
            if not collection_name:
                raise ValueError(f"Collection with ID {files.collection_id} not found.")
            # Add chunks to ChromaDB
            ids = [str(files.id) + "_" + str(i) for i in range(len(chunks))]
            metadata = [
                {
                    "text": text,
                    "file_name": files.file_name,
                } for text in chunks
            ]
            logger.info("Preparing to add chunks to Qdrant for file: {}", files.id)
            self.qdrant_client.add_documents(
                ids=ids,
                documents=chunks,
                metadatas=metadata,
                collection_name=vectordb_collection_name,
                embedding_function=self.embedding_model.encode
            )
            logger.info("Added chunks to Qdrant for file: {}", files.id)
            # Update the file status to completed
            self.file_repository.update(
                id=files.id,
                schema=Files(
                    status="completed",
                    metadatas={
                        "collection_name": collection_name,
                        "chunk_count": len(chunks),
                        "chunk_size": self.doc_chunker.chunk_size,
                        "chunk_overlap": self.doc_chunker.chunk_overlap,
                    },
                    processing_ended_at=datetime.now()
                )
            )

        except Exception as e:
            logger.error("Error processing file {}: {}", files.id, str(e))
            logger.exception("Full traceback:")
            # Update the file status to error
            self.file_repository.update(
                id=files.id,
                schema=Files(
                    status="failed",
                    processing_ended_at=datetime.now()
                )
            )
