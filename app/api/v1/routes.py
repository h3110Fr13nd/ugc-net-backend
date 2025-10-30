from fastapi import APIRouter

router = APIRouter()

from .auth import router as auth_router
from .questions import router as questions_router
from .media import router as media_router


@router.get("/health")
async def health_check():
    return {"status": "ok", "version": "v1"}


# Include auth related endpoints under /auth
router.include_router(auth_router, prefix="/auth", tags=["auth"])

# Include questions CRUD endpoints
router.include_router(questions_router)

# Include media upload/management endpoints
router.include_router(media_router)
