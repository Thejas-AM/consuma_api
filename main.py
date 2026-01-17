import logging
from contextlib import asynccontextmanager
from fastapi import FastAPI

from database import init_database
from routes import api_router

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan - initialize database on startup."""
    await init_database()
    logging.info("Database initialized")
    yield
    logging.info("Application shutting down")


app = FastAPI(
    title="Sync/Async Work Service",
    description="A service that exposes sync and async endpoints performing the same work",
    version="1.0.0",
    lifespan=lifespan
)

# Include all API routes
app.include_router(api_router)


@app.get("/healthz", tags=["health"])
async def healthz():
    """Health check endpoint."""
    return {"status": "healthy"}
