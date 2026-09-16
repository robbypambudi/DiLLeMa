import uuid

from pydantic import BaseModel

from app.utils.schema import as_form


class BaseQuestion(BaseModel):
    question_id: str
    question_text: str


@as_form
class CreateQuestion(BaseQuestion):
    collection_id: uuid.UUID
    using_augment_query: bool = False


class QuestionResponse(BaseModel):
    question_id: str
    question_text: str
    answer: str
