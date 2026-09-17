from dependency_injector import containers, providers

from agents.augment_query_generated import AugmentQueryGenerated
from app.core.config import settings
from app.core.database import Database
from app.pipeline.pipeline_service import PipelineService
from app.repositories import CollectionsRepository
from app.repositories.files_repository import FilesRepository
from app.repositories.questions_repository import QuestionsRepository
from app.repositories.users_repository import UsersRepository
from app.services.auth_service import AuthService
from app.services.collection_service import CollectionsService
from app.services.files_service import FilesService
from app.services.knowledge_service import KnowledgeService
from app.services.question_service import QuestionsService
from app.services.retrieval_service import RetrievalService
from rag.qdrant.client import QdrantHttpClient
from rag.embedding.embedding_factory import EmbeddingFactory
from rag.embedding.device import embedding_device
from knowledge.repository import KnowledgeRepository
from rag.llm.chat_model import OpenAIChat
from rag.llm.re_rank import ReRanking
from rag.nlp.doc_chunking import DocumentChunker


class Container(containers.DeclarativeContainer):
    wiring_config = containers.WiringConfiguration(
        modules=[
            "app.api.v1.endpoints.auth",
            "app.api.v1.endpoints.questions",
            "app.api.v1.endpoints.collections",
            "app.api.v1.endpoints.files",
            "app.api.v1.endpoints.knowledge",
            "app.core.dependencies",
        ]
    )
    embedding_factory = providers.Singleton(
        EmbeddingFactory,
        device=providers.Callable(embedding_device),
    )
    embedding_model = providers.ThreadSafeSingleton(
        lambda factory: factory.get("Default"),
        embedding_factory,
    )
    qdrant_client = providers.Singleton(
        QdrantHttpClient, host=settings.QDRANT_HOST, port=settings.QDRANT_PORT
    )
    db = providers.Singleton(Database, db_url=str(settings.SQLALCHEMY_DATABASE_URI))
    knowledge_repository = providers.Factory(
        KnowledgeRepository, session_factory=db.provided.session
    )
    knowledge_service = providers.Factory(
        KnowledgeService, repository=knowledge_repository
    )
    re_ranking = providers.ThreadSafeSingleton(ReRanking)
    openai_chat = providers.Singleton(OpenAIChat, key="any")
    doc_chunker = providers.ThreadSafeSingleton(DocumentChunker)
    augment_query_generator = providers.Singleton(
        AugmentQueryGenerated, api_key=str(settings.OPENAI_API_KEY)
    )

    collections_repository = providers.Factory(
        CollectionsRepository, session_factory=db.provided.session
    )
    files_repository = providers.Factory(
        FilesRepository, session_factory=db.provided.session
    )
    questions_repository = providers.Factory(
        QuestionsRepository, session_factory=db.provided.session
    )
    users_repository = providers.Factory(
        UsersRepository, session_factory=db.provided.session
    )

    pipeline_service = providers.Factory(
        PipelineService,
        files_repository=files_repository,
        qdrant_client=qdrant_client,
        knowledge_repository=knowledge_repository,
        embedding_model=embedding_model,
        doc_chunker=doc_chunker,
    )
    collection_service = providers.Factory(
        CollectionsService,
        collections_repository=collections_repository,
        files_repository=files_repository,
        qdrant_client=qdrant_client,
        embedding_model=embedding_model,
    )
    files_service = providers.Factory(
        FilesService,
        files_repository=files_repository,
        collections_repository=collections_repository,
        qdrant_client=qdrant_client,
    )
    retrieval_service = providers.Factory(
        RetrievalService,
        collections_repository=collections_repository,
        qdrant_client=qdrant_client,
        augment_query_generator=augment_query_generator,
        knowledge_repository=knowledge_repository,
        embedding_model=embedding_model,
        re_ranking=re_ranking,
    )
    question_service = providers.Factory(
        QuestionsService,
        questions_repository=questions_repository,
        collections_repository=collections_repository,
        qdrant_client=qdrant_client,
        augment_query_generator=augment_query_generator,
        retrieval_service=retrieval_service,
        openai_chat=openai_chat,
    )
    auth_service = providers.Factory(AuthService, users_repository=users_repository)
