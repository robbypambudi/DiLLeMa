from fastapi import APIRouter

from app.api.v1.endpoints.collections import router as collections

api_router = APIRouter()
api_router.include_router(collections)


# Test
@api_router.get("/", tags=["test"])
def test():
    return {"message": "Hello World"}
