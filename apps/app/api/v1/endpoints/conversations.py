from uuid import UUID

from dependency_injector.wiring import Provide, inject
from fastapi import APIRouter, Depends, Query

from app.core.container import Container
from app.core.dependencies import get_current_user
from app.models.users import Users
from app.schema.base_schema import BaseResponse
from app.schema.conversation_schema import (
    CreateConversation,
    ConversationDetail,
    ConversationList,
)
from app.services.conversation_service import ConversationService

router = APIRouter(prefix="/conversations", tags=["conversations"])


@router.get("", response_model=ConversationList)
@inject
def list_conversations(
    offset: int = Query(default=0, ge=0),
    limit: int = Query(default=50, ge=1, le=100),
    user: Users = Depends(get_current_user),
    service: ConversationService = Depends(Provide[Container.conversation_service]),
):
    return service.list(user.id, offset, limit)


@router.post("", response_model=BaseResponse[ConversationDetail], status_code=201)
@inject
def create_conversation(
    payload: CreateConversation,
    user: Users = Depends(get_current_user),
    service: ConversationService = Depends(Provide[Container.conversation_service]),
):
    return BaseResponse(data=service.create(user.id, payload.collection_id))


@router.get("/{conversation_id}", response_model=BaseResponse[ConversationDetail])
@inject
def get_conversation(
    conversation_id: UUID,
    user: Users = Depends(get_current_user),
    service: ConversationService = Depends(Provide[Container.conversation_service]),
):
    return BaseResponse(data=service.get(conversation_id, user.id))


@router.delete("/{conversation_id}", response_model=BaseResponse[None])
@inject
def delete_conversation(
    conversation_id: UUID,
    user: Users = Depends(get_current_user),
    service: ConversationService = Depends(Provide[Container.conversation_service]),
):
    service.delete(conversation_id, user.id)
    return BaseResponse(data=None, message="Conversation deleted")
