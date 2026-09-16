import logging

from sse_starlette.sse import EventSourceResponse

from src.lib.response_handler import ResponseHandler
from src.services.api.questions_service import QuestionsService
from src.services.chroma.chroma_service import ChromaService
from src.services.rag.chain_service import ChainService
from src.services.rag.memorystore_service import MemorystoreService
from src.types.question_request_type import PostQuestionStreamGeneratorType

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class QuestionsController(ResponseHandler):

    def __init__(self, chain_service: ChainService, chroma_service: ChromaService,
                 memorystore_service: MemorystoreService, questions_service: QuestionsService):
        self.chain_service = chain_service
        self.memorystore_service = memorystore_service
        self.questions_service = questions_service
        self.chroma_service = chroma_service

    @staticmethod
    async def _chain_stream(self, question: str, question_id: str, is_output_html: bool = True):
        """
        Initialize the chain service with the specified parameters.
        """
        memorystore = self.memorystore_service.get_memory(id)
        context = self.chain_service.get_context(question, memorystore)
        # Pretty print the context
        logger.info(f"Context: {context}")
        chain_gen = self.chain_service.get_chain(is_stream=True, is_output_html=is_output_html).astream(context)

        accumulated_answer = ""
        async for chunk in chain_gen:
            accumulated_answer += chunk
            yield chunk

        # After the streaming is done, save the answer to the memory store
        self.memorystore_service.add_ai_message(id, accumulated_answer)

    def ask_with_stream(self, payload: PostQuestionStreamGeneratorType):
        """
        Ask a question to the chain service and return the answer.
        """
        try:
            # Call the chain service with the question
            self.memorystore_service.add_user_message(payload.id, payload.question)

            # Call the chain service with the question
            return EventSourceResponse(
                self._chain_stream(
                    self,
                    question=payload.question,
                    question_id=payload.id
                ),
                media_type="text/event-stream",
            )
        except Exception as e:
            logger.error(f"Error in ask_with_stream: {e}")
            return self.error(message="An error occurred while processing your request.", status_code=500)

    def ask_without_stream(self, payload: PostQuestionStreamGeneratorType):
        """
        Ask a question to the chain service and return the answer.
        """
        try:
            # Tambahkan pesan pengguna ke memory store
            collection = self.chroma_service.get_collection(collection_name=payload.collection_name)
            self.memorystore_service.add_user_message(payload.id, payload.question)
            memorystore = self.memorystore_service.get_memory(payload.id)

            context = self.chain_service.get_context(payload.question, memorystore, collection)

            # Ambil chain dan dapatkan jawaban dari LL
            answer = self.chain_service.get_chain(is_stream=False, is_output_html=False).invoke(context)

            # Simpan jawaban AI ke dalam memory store
            self.memorystore_service.add_ai_message(payload.id, answer)

            return self.success(
                data={
                    "answer": answer,
                },
                status_code=200
            )
        # as Value Error
        except ValueError as e:
            logger.error(f"Error in ask_without_stream: {e}")
            return self.error(message=str(e), status_code=400)
        except Exception as e:
            logger.error(f"Error in ask_without_stream: {e}")
            return self.error(message="An error occurred while processing your request.", status_code=500)
