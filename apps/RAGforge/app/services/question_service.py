from sentence_transformers import SentenceTransformer
from loguru import logger

from agents.augment_query_generated import AugmentQueryGenerated
from app.core.config import settings
from app.models.questions import Questions
from app.repositories import CollectionsRepository
from app.repositories.questions_repository import QuestionsRepository
from app.schema.question_schema import CreateQuestion
from app.services.base_service import BaseService
from rag.qdrant.client import QdrantHttpClient
from rag.llm.chat_model import OpenAIChat
from rag.llm.re_rank import ReRanking


class QuestionsService(BaseService):
    """
    Question service class for handling question-related operations.
    """
    re_ranking = ReRanking()
    openai_chat = OpenAIChat(key=str('any'), model_name=str('qwen-14b'))
    embedding_model = SentenceTransformer("sentence-transformers/all-mpnet-base-v2")

    def __init__(self, questions_repository: QuestionsRepository, collections_repository: CollectionsRepository,
                 qdrant_client: QdrantHttpClient, augment_query_generator: AugmentQueryGenerated) -> None:
        self.question_repository = questions_repository
        self.collections_repository = collections_repository
        self.qdrant_client = qdrant_client
        self.augment_query_generator = augment_query_generator
        super().__init__(questions_repository)

    def _before_question(self, payload: CreateQuestion, using_augment_query=False):
        """
        Create a new question and answer pair.
        """
        # Get Collection Name
        collection = self.collections_repository.read_by_id(payload.collection_id)
        if not collection:
            raise ValueError(f"Collection with ID {payload.collection_id} not found.")

        if using_augment_query:
            quries = self.augment_query_generator.augment(payload.question_text)
        else:
            quries = [payload.question_text]

        # Generate embeddings for queries
        query_embeddings = [self.embedding_model.encode(query) for query in quries]
        
        # Search in Qdrant
        all_results = []
        for query_embedding in query_embeddings:
            search_result = self.qdrant_client.client.search(
                collection_name=collection.vectordb_collection_name,
                query_vector=query_embedding,
                limit=10
            )
            docs = [hit.payload.get("document", "") for hit in search_result]
            all_results.append(docs)
        
        results = {"documents": all_results}
        retrieved_documents = results["documents"]

        # Check is retrieved_documents is empty
        # Example : "retrieved_documents": [[], [], []]
        if not any(retrieved_documents):
            logger.debug("Empty retrieved documents")
            return [[payload.question_text, "Tidak ada jawaban yang ditemukan."]]

        unique_documents = set()
        for documents in retrieved_documents:
            for doc in documents:
                unique_documents.add(doc)

        pairs = []
        for doc in unique_documents:
            pairs.append([payload.question_text, doc])

        # Re-rank the answers
        if using_augment_query:
            re_ranked_pairs = self.re_ranking.rank(pairs=pairs)
        else:
            re_ranked_pairs = pairs

        return re_ranked_pairs

    def question_no_stream(self, payload: CreateQuestion):
        re_ranked_pairs = self._before_question(payload, using_augment_query=payload.using_augment_query)

        response = self.openai_chat.chat(
            question=payload.question_text,
            context_pairs=re_ranked_pairs,
        )
        question = self.question_repository.create(
            Questions(
                question_id=payload.question_id,
                question_text=payload.question_text,
                answer=response,
                collection_id=payload.collection_id,
            )
        )
        return question

    async def question_stream(self, payload: CreateQuestion):
        """
        Stream the question and answer pairs.
        """
        try:
            re_ranked_pairs = self._before_question(payload, using_augment_query=payload.using_augment_query)

            async for chunk in self.openai_chat.chat_with_stream(
                    question=payload.question_text,
                    context_pairs=re_ranked_pairs
            ):
                if chunk:
                    yield {"data": chunk}

            # Create the question record after completion
            accumulated_answer = ""  # You might want to accumulate the complete answer
            self.question_repository.create(
                Questions(
                    question_id=payload.question_id,
                    question_text=payload.question_text,
                    answer=accumulated_answer,
                    collection_id=payload.collection_id,
                )
            )
        except Exception as e:
            logger.error(f"Error in question_stream: {str(e)}")
            yield {"error": str(e)}

    def clear_all(self):
        """
        Clear all questions from the database.
        """
        self.question_repository.clear_all()
