import asyncio
import logging
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .config import settings
from .api.routes import router
from .session.session_manager import session_manager

# Configure structured logging with PII safety
logging.basicConfig(
    level=getattr(logging, settings.LOG_LEVEL.upper(), logging.INFO),
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s"
)
logger = logging.getLogger("backend_main")

@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info(f"Starting {settings.COMPANY_NAME} Support Voice Backend on port {settings.BACKEND_PORT}")
    # Start session manager background cleanup task
    cleanup_task = asyncio.create_task(session_manager.cleanup_loop())
    yield
    # Graceful shutdown: cancel background tasks
    logger.info("Shutting down backend services...")
    cleanup_task.cancel()

app = FastAPI(
    title=f"{settings.COMPANY_NAME} Voice Customer Support API",
    version="1.0.0",
    lifespan=lifespan
)

# CORS configuration
origins = [
    settings.FRONTEND_URL,
    "http://localhost:3000",
    "http://127.0.0.1:3000",
    "*"
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(router)

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("backend.main:app", host="0.0.0.0", port=settings.BACKEND_PORT, reload=True)

