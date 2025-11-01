from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from pathlib import Path
import os
from app.api.v1.routes import router as v1_router
from app.core.logging import get_logger
from app.middleware.request_id import RequestIdMiddleware


# Initialize logging for the application early so other modules can use it
logger = get_logger(name="ugc-net-backend")
logger.info("Logger initialized for backend")


def create_app() -> FastAPI:
    app = FastAPI(title="UGC Net Backend")
    
    # Allow CORS for local development. Narrow this in production.
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    
    # Mount static files for media uploads
    upload_dir = Path(os.getenv("UPLOAD_DIR", "./uploads"))
    upload_dir.mkdir(parents=True, exist_ok=True)
    app.mount("/media/files", StaticFiles(directory=str(upload_dir)), name="media")
    
    # Request ID middleware (sets X-Request-ID and contextvar for logging)
    app.add_middleware(RequestIdMiddleware)
    
    # Include API routes
    app.include_router(v1_router, prefix="/api/v1")
    
    return app


app = create_app()

logger.info("Application startup complete.")
