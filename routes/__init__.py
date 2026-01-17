"""
API routes package.
"""
from fastapi import APIRouter
from routes.sync import router as sync_router
from routes.async_ import router as async_router
from routes.requests import router as requests_router

# Aggregate all routers
api_router = APIRouter()
api_router.include_router(sync_router, tags=["sync"])
api_router.include_router(async_router, tags=["async"])
api_router.include_router(requests_router, tags=["requests"])
