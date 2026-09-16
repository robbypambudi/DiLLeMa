import inspect
from typing import Annotated
from typing import Optional, get_type_hints

from fastapi import Form
from pydantic._internal._model_construction import ModelMetaclass


class AllOptional(ModelMetaclass):

    def __new__(cls, name, bases, namespace):
        annotations = namespace.get('__annotations__', {})
        for base in bases:
            annotations.update(get_type_hints(base))
        new_annotations = {k: Optional[v] for k, v in annotations.items()}
        namespace['__annotations__'] = new_annotations
        return super().__new__(cls, name, bases, namespace)


def as_form(cls):
    new_params = [
        inspect.Parameter(
            field_name,
            inspect.Parameter.POSITIONAL_ONLY,
            default=model_field.default,
            annotation=Annotated[
                model_field.annotation, model_field.metadata[:], Form()
            ],
        )
        for field_name, model_field in cls.model_fields.items()
    ]

    cls.__signature__ = cls.__signature__.replace(parameters=new_params)

    return cls
