import uuid
from typing import Annotated

from pydantic import BaseModel, BeforeValidator

from app.utils.schema import as_form

# A form field left blank arrives as "", which is "not chosen", not a
# malformed boolean.
OptionalFlag = Annotated[
    bool | None, BeforeValidator(lambda value: None if value == "" else value)
]


class BaseQuestion(BaseModel):
    question_id: str
    question_text: str


@as_form
class CreateQuestion(BaseQuestion):
    collection_id: uuid.UUID
    # Unset follows the server's QUERY_AUGMENTATION setting.
    using_augment_query: OptionalFlag = None
    conversation_id: uuid.UUID | None = None


class QuestionResponse(BaseModel):
    question_id: str
    question_text: str
    answer: str
