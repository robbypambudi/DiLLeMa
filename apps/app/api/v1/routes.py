from fastapi import APIRouter

from app.api.v1.endpoints.auth import router as auth
from app.api.v1.endpoints.collections import router as collections
from app.api.v1.endpoints.files import router as files
from app.api.v1.endpoints.questions import router as questions
from app.api.v1.endpoints.knowledge import router as knowledge

routers = APIRouter(prefix='/v1', tags=["v1"])

routers.include_router(auth)
routers.include_router(collections)
routers.include_router(files)
routers.include_router(questions)
routers.include_router(knowledge)
