from fastapi import APIRouter
from app.api.v1.endpoints import brands, prompts

api_router = APIRouter(prefix="/api")
api_router.include_router(brands.router)
api_router.include_router(prompts.router)
