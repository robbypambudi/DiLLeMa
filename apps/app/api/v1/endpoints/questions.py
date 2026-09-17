from dependency_injector.wiring import Provide
from fastapi import APIRouter, Depends
from sse_starlette import EventSourceResponse
from starlette.concurrency import run_in_threadpool

from app.core.container import Container
from app.core.dependencies import get_optional_user, require_admin
from app.core.middleware import inject
from app.models.users import Users
from app.schema.base_schema import BaseResponse
from app.schema.question_schema import QuestionResponse, CreateQuestion
from app.services.question_service import QuestionsService

router = APIRouter(prefix="/questions", tags=["questions"])


@router.post("", tags=["get"], response_model=BaseResponse[QuestionResponse])
@inject
def question(
    payload: CreateQuestion = Depends(),
    user: Users | None = Depends(get_optional_user),
    question_service: QuestionsService = Depends(Provide[Container.question_service]),
):
    turn_id = question_service.start_turn(payload, user)
    question = question_service.question_no_stream(payload, turn_id=turn_id)
    return BaseResponse(
        message="Questions retrieved successfully",
        data=QuestionResponse(
            question_id=question.question_id,
            question_text=question.question_text,
            answer=question.answer,
        ),
    )


@router.post("/stream", tags=["get"])
@inject
async def question_stream(
    payload: CreateQuestion = Depends(),
    user: Users | None = Depends(get_optional_user),
    question_service: QuestionsService = Depends(Provide[Container.question_service]),
):
    turn_id = await run_in_threadpool(question_service.start_turn, payload, user)
    return EventSourceResponse(
        question_service.question_stream(payload, turn_id=turn_id),
        media_type="text/event-stream",
        ping=15,
        headers={
            "Cache-Control": "no-cache, no-transform",
            "X-Accel-Buffering": "no",
            "Connection": "keep-alive",
        },
    )


@router.delete("/clear-all", tags=["delete-all"])
@inject
def clear_all(
    _admin: Users = Depends(require_admin),
    question_service: QuestionsService = Depends(Provide[Container.question_service]),
):
    question_service.clear_all()
    return BaseResponse(message="All questions cleared successfully", data=None)
