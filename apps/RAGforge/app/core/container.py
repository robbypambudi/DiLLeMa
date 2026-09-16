from dependency_injector import containers, providers

from agents.augment_query_generated import AugmentQueryGenerated
from app.core.config import settings
from app.core.database import Database
from app.pipeline.pipeline_service import PipelineService
from app.repositories import CollectionsRepository
from app.repositories.files_repository import FilesRepository
from app.repositories.questions_repository import QuestionsRepository
from app.services.collection_service import CollectionsService
from app.services.files_service import FilesService
from app.services.question_service import QuestionsService
from rag.qdrant.client import QdrantHttpClient
from rag.embedding.embedding_factory import EmbeddingFactory


class Container(containers.DeclarativeContainer):
    wiring_config = containers.WiringConfiguration(
        modules=[
            "app.api.v1.endpoints.questions",
            "app.api.v1.endpoints.collections",
            "app.api.v1.endpoints.files",
            "app.core.dependencies",
        ]
    )
    embedding_factory = providers.Singleton(
        EmbeddingFactory,
    )
    embedding_model = providers.ThreadSafeSingleton(
        lambda factory: factory.get("Default"),
        embedding_factory,
    )
    qdrant_client = providers.Singleton(QdrantHttpClient, host=settings.QDRANT_HOST, port=settings.QDRANT_PORT)
    db = providers.Singleton(Database, db_url=str(settings.SQLALCHEMY_DATABASE_URI))
    augment_query_generator = providers.Singleton(AugmentQueryGenerated, api_key=str(settings.OPENAI_API_KEY))

    # Repository layer
    collections_repository = providers.Factory(CollectionsRepository, session_factory=db.provided.session)
    files_repository = providers.Factory(FilesRepository, session_factory=db.provided.session)
    questions_repository = providers.Factory(QuestionsRepository, session_factory=db.provided.session)

    # Service layer
    pipeline_service = providers.Factory(PipelineService, files_repository=files_repository,
                                         qdrant_client=qdrant_client)
    collection_service = providers.Factory(CollectionsService, collections_repository=collections_repository,
                                           qdrant_client=qdrant_client, embedding_model=embedding_model)
    files_service = providers.Factory(FilesService, files_repository=files_repository)
    question_service = providers.Factory(QuestionsService, questions_repository=questions_repository,
                                         collections_repository=collections_repository,
                                         qdrant_client=qdrant_client,
                                         augment_query_generator=augment_query_generator)
