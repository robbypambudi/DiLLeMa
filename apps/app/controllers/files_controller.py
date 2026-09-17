import logging
import os
from typing import List, Dict, Any

from fastapi import File, Form, UploadFile
from fastapi.responses import JSONResponse

from src.lib.response_handler import ResponseHandler
from src.services.chroma.chroma_service import ChromaService
from src.services.embedding.embedding_service import EmbeddingService
from src.services.rag.memorystore_service import MemorystoreService
from src.services.storage.files_storage_service import FileStorageService
from src.types.files_request_type import DeleteFileRequestType

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class FilesController(ResponseHandler):
    # Class constants
    DOCUMENTS_DIR = "documents"

    def __init__(
            self,
            file_storage_service: FileStorageService,
            embedding_service: EmbeddingService,
            memorystore_service: MemorystoreService,
            chroma_service: ChromaService
    ):
        self.file_storage_service = file_storage_service
        self.embedding_service = embedding_service
        self.memorystore_service = memorystore_service
        self.chroma_service = chroma_service

    def get_files(self) -> JSONResponse:
        """
        Get all files
        """
        files = self.file_storage_service.get_all_files()

        if not files:
            return self.success(data=[], message="No files found", status_code=200)

        return self.success(data=files, message="Files retrieved successfully", status_code=200)

    def upload_file(self,
                    description: str = Form(...),
                    collection_name: str = Form(...),
                    file: UploadFile = File(...)) -> JSONResponse:
        """Upload and process a file, creating embeddings and storing in a collection."""
        try:
            file_info = self._process_file(file, description, collection_name)
            return self._create_success_response(file_info)
        except ValueError as e:
            return self.error(message=str(e), status_code=400)
        except Exception as e:
            logger.error(f"Error uploading file: {e}")
            return self.error(message="Failed to save file", status_code=500)

    def _process_file(self, file: UploadFile, description: str, collection_name: str) -> Dict[str, Any]:
        """Process the uploaded file and return file information."""
        filename = file.filename
        dir_path = self._get_directory_path(filename)

        # Save and process file
        file_path = self.file_storage_service.save_file_to_local(file, dir_path, filename)
        token_chunks = self._process_document(file_path)

        # Create embeddings for the document chunks
        print("token_chunks: ", token_chunks)

        # Store in a collection
        collection = self.chroma_service.get_collection(collection_name=collection_name)
        embeddings = self._create_embeddings(token_chunks)
        self._store_document_chunks(filename, file_path, description, token_chunks, embeddings, collection)

        # Save file metadata
        self.file_storage_service.save_file(
            name=filename,
            path=dir_path,
            description=description,
            metadatas={"source": file_path}
        )

        return {
            "file_path": file_path,
            "info": {
                "name": filename,
                "description": description,
                "metadatas": {"source": file_path},
                "chunks": len(token_chunks),
            }
        }

    def _get_directory_path(self, filename: str) -> str:
        """Generate directory path for the file."""
        return os.path.join(self.DOCUMENTS_DIR, filename.split(".")[0])

    def _process_document(self, file_path: str) -> List[Any]:
        """Load and split document into chunks."""
        document_chunks = self.embedding_service.load_and_split_document(file_path)
        token_chunks = self.embedding_service
        if not document_chunks:
            raise ValueError("No documents found in the file")
        return document_chunks

    def _create_embeddings(self, document_chunks: List[Any]) -> List[List[float]]:
        """Create embeddings from document chunks."""
        embeddings = self.embedding_service.embed_documents(document_chunks)
        if not embeddings:
            raise ValueError("Failed to embed documents")
        return embeddings

    def _store_document_chunks(self,
                               filename: str,
                               file_path: str,
                               description: str,
                               chunks: List[Any],
                               embeddings: List[List[float]],
                               collection: Any) -> None:
        """Store document chunks with their embeddings in the collection."""
        for i, (chunk, embedding) in enumerate(zip(chunks, embeddings)):
            # Fix: Check chunk object, not chunks (the list)
            document_text = chunk.page_content if hasattr(chunk, 'page_content') else str(chunk)

            self.chroma_service.add_document(
                doc_id=f"{filename}_chunk_{i}",
                embedding=embedding,
                document=document_text,
                metadata={
                    "source": file_path,
                    "filename": filename,
                    "description": description,
                },
                collection=collection
            )

    def _create_success_response(self, file_info: Dict[str, Any]) -> JSONResponse:
        """Create success response with file information."""
        return self.success(
            data=file_info,
            message="File uploaded successfully",
            status_code=200
        )

    async def delete_file_with_knowledge(self, payload: DeleteFileRequestType) -> JSONResponse:
        """
        Delete a file by its ID and name
        """

        try:
            file = self.file_storage_service.verify_file_by_id_name(payload.file_id, payload.file_name)

            if not file:
                return self.error(message="File not found", status_code=404)
            # Delete the file from chunks
            chunks: List[str] = self.vectorstore_service.get_chunks_by_filename(file.name)

            if not chunks:
                return self.error(message="No chunks found for the file", status_code=404)

            self.file_storage_service.delete_file(file)
            # TODO: Need to integrate using chroma service
            # self.vectorstore_service.delete_document_by_chunks(chunks)
            self.memorystore_service.clear_memory()

            return self.success(data={
                "id": file.id,
                "file": file.name,
                "chunks": chunks
            }, message="File deleted successfully", status_code=200)

        except ValueError as e:
            logger.error(f"Error deleting file: {e}")
            return self.error(message="File not found", status_code=404)
        except FileNotFoundError as e:
            logger.error(f"Error deleting file: {e}")
            return self.error(message="File not found", status_code=404)
        except Exception as e:
            logger.error(f"Error deleting file: {e}")
            return self.error(message="Failed to delete file", status_code=500)

    async def get_file_by_file_name(self, file_name: str) -> JSONResponse:
        """
        Get a file by its name
        """
        try:
            file = self.file_storage_service.get_file_by_file_name(file_name)
            if not file:
                return self.error(message="File not found", status_code=404)

            chunks = self.chroma_service.ge
            if not chunks:
                return self.error(message="No chunks found for the file", status_code=404)

            return self.success(data={
                "id": file.id,
                "file": file.name,
                "chunks": chunks
            }, message="File retrieved successfully", status_code=200)

        except ValueError as e:
            logger.error(f"Error retrieving file: {e}")
            return self.error(message="File not found", status_code=404)

        except Exception as e:
            logger.error(f"Error retrieving file: {e}")
            return self.error(message="Failed to retrieve file", status_code=500)
