"""Register consistent validation responses without logging request contents."""

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from pydantic import ValidationError
from starlette.responses import JSONResponse


def validation_response(errors: list[dict], *, skip_location: bool) -> JSONResponse:
    return JSONResponse(
        status_code=422,
        content={
            "errors": [
                {
                    "field": ".".join(
                        str(part) for part in error["loc"][int(skip_location) :]
                    ),
                    "message": error["msg"],
                }
                for error in errors
            ]
        },
    )


def register_exception_handlers(app: FastAPI) -> None:
    @app.exception_handler(RequestValidationError)
    async def request_validation_handler(
        _request: Request, exc: RequestValidationError
    ):
        return validation_response(exc.errors(), skip_location=True)

    @app.exception_handler(ValidationError)
    async def model_validation_handler(_request: Request, exc: ValidationError):
        return validation_response(exc.errors(), skip_location=False)
