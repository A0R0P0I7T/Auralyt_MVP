from fastapi import APIRouter
from app.api.v1.endpoints import brands

api_router = APIRouter(prefix="/api")
api_router.include_router(brands.router)
