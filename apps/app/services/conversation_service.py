from uuid import UUID

from app.repositories.conversations_repository import ConversationsRepository


class ConversationService:
    def __init__(self, repository: ConversationsRepository):
        self.repository = repository

    def create(self, user_id: UUID, collection_id: UUID):
        return self.repository.create(user_id, collection_id)

    def list(self, user_id: UUID, offset: int, limit: int):
        return self.repository.list(user_id, offset, limit)

    def get(self, conversation_id: UUID, user_id: UUID):
        return self.repository.get(conversation_id, user_id)

    def delete(self, conversation_id: UUID, user_id: UUID):
        self.repository.delete(conversation_id, user_id)
