from fastapi import APIRouter

router = APIRouter()

from .auth import router as auth_router
from .questions import router as questions_router
from .media import router as media_router
from .taxonomy import router as taxonomy_router
from .quizzes import router as quizzes_router
from .attempts import router as attempts_router
from .stats import router as stats_router
from .ws_attempts import router as ws_attempts_router
from .history import router as history_router
from app.core.logging import get_logger

logger = get_logger()


@router.get("/health")
async def health_check():
    logger.info("Health check endpoint called")
    return {"status": "ok", "version": "v1"}


# Include auth related endpoints under /auth
router.include_router(auth_router, prefix="/auth", tags=["auth"])

# Include questions CRUD endpoints
router.include_router(questions_router)

# Include media upload/management endpoints
router.include_router(media_router)

# Include taxonomy endpoints
router.include_router(taxonomy_router)

# Include quizzes endpoints
router.include_router(quizzes_router)

# Include attempts endpoints
router.include_router(attempts_router)

# Include stats endpoints
router.include_router(stats_router)

# Include WebSocket attempts endpoints
router.include_router(ws_attempts_router)

# Include history endpoints
router.include_router(history_router)
