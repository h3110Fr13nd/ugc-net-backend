"""Media upload and management endpoints."""
from fastapi import APIRouter, UploadFile, File, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from typing import List
import hashlib
import uuid
from pathlib import Path
import aiofiles
import os
import mimetypes

from ...db.base import get_session
from ...db.models import Media
from .schemas import MediaResponse

router = APIRouter(prefix="/media", tags=["media"])

# Configure upload directory
UPLOAD_DIR = Path(os.getenv("UPLOAD_DIR", "./uploads"))
UPLOAD_DIR.mkdir(parents=True, exist_ok=True)

# Configure max file size (10MB default)
MAX_FILE_SIZE = int(os.getenv("MAX_FILE_SIZE", 10 * 1024 * 1024))

# Allowed file types
ALLOWED_IMAGE_TYPES = {"image/jpeg", "image/png", "image/gif", "image/webp", "image/svg+xml"}
ALLOWED_VIDEO_TYPES = {"video/mp4", "video/webm", "video/ogg"}
ALLOWED_AUDIO_TYPES = {"audio/mpeg", "audio/wav", "audio/ogg", "audio/webm"}
ALLOWED_DOCUMENT_TYPES = {"application/pdf"}

# File extensions to MIME types mapping
EXTENSION_TO_MIME = {
    '.jpg': 'image/jpeg',
    '.jpeg': 'image/jpeg',
    '.png': 'image/png',
    '.gif': 'image/gif',
    '.webp': 'image/webp',
    '.svg': 'image/svg+xml',
    '.mp4': 'video/mp4',
    '.webm': 'video/webm',
    '.ogg': 'video/ogg',
    '.mp3': 'audio/mpeg',
    '.wav': 'audio/wav',
    '.pdf': 'application/pdf',
}


async def calculate_checksum(file_path: Path) -> str:
    """Calculate SHA256 checksum of a file."""
    sha256_hash = hashlib.sha256()
    async with aiofiles.open(file_path, "rb") as f:
        while chunk := await f.read(8192):
            sha256_hash.update(chunk)
    return sha256_hash.hexdigest()


def get_file_extension(filename: str) -> str:
    """Get file extension from filename."""
    return Path(filename).suffix.lower()


def detect_mime_type(filename: str, content_type: str) -> str:
    """
    Detect MIME type from filename extension if content_type is generic.
    Falls back to mimetypes library if needed.
    """
    # If we got a generic content type, try to detect from filename
    if content_type in ('application/octet-stream', None, ''):
        file_ext = get_file_extension(filename)
        
        # Try our mapping first
        if file_ext in EXTENSION_TO_MIME:
            return EXTENSION_TO_MIME[file_ext]
        
        # Fall back to mimetypes library
        guessed_type, _ = mimetypes.guess_type(filename)
        if guessed_type:
            return guessed_type
    
    return content_type


def validate_file_type(content_type: str, allowed_types: set) -> bool:
    """Check if content type is allowed."""
    return content_type in allowed_types


@router.post("/upload", response_model=MediaResponse, status_code=201)
async def upload_media(
    file: UploadFile = File(...),
    db: AsyncSession = Depends(get_session),
):
    """
    Upload a media file (image, video, audio, or document).
    
    Returns the media metadata including URL and storage key.
    """
    # Validate file size
    content = await file.read()
    if len(content) > MAX_FILE_SIZE:
        raise HTTPException(
            status_code=413,
            detail=f"File too large. Maximum size is {MAX_FILE_SIZE / 1024 / 1024}MB"
        )
    
    # Detect actual MIME type from filename if needed
    mime_type = detect_mime_type(file.filename, file.content_type)
    
    # Validate content type
    all_allowed_types = (
        ALLOWED_IMAGE_TYPES | 
        ALLOWED_VIDEO_TYPES | 
        ALLOWED_AUDIO_TYPES | 
        ALLOWED_DOCUMENT_TYPES
    )
    if not validate_file_type(mime_type, all_allowed_types):
        raise HTTPException(
            status_code=400,
            detail=f"File type {mime_type} not allowed. Allowed types: images, videos, audio, PDF"
        )
    
    # Generate unique storage key
    file_ext = get_file_extension(file.filename)
    storage_key = f"{uuid.uuid4()}{file_ext}"
    file_path = UPLOAD_DIR / storage_key
    
    # Save file
    async with aiofiles.open(file_path, "wb") as f:
        await f.write(content)
    
    # Calculate checksum
    checksum = await calculate_checksum(file_path)
    
    # Get file size
    size_bytes = len(content)
    
    # Create media record
    media = Media(
        url=f"/media/files/{storage_key}",  # Will be served by static files
        storage_key=storage_key,
        mime_type=mime_type,
        size_bytes=size_bytes,
        checksum=checksum,
        meta_data={
            "original_filename": file.filename,
            "original_content_type": file.content_type,
        }
    )
    
    db.add(media)
    await db.commit()
    await db.refresh(media)
    
    return media


@router.post("/upload-image", response_model=MediaResponse, status_code=201)
async def upload_image(
    file: UploadFile = File(...),
    db: AsyncSession = Depends(get_session),
):
    """Upload an image file specifically."""
    # Detect MIME type from filename
    mime_type = detect_mime_type(file.filename, file.content_type)
    
    if not validate_file_type(mime_type, ALLOWED_IMAGE_TYPES):
        raise HTTPException(
            status_code=400,
            detail=f"Only image files allowed. Detected type: {mime_type}"
        )
    
    return await upload_media(file, db)


@router.get("/{media_id}", response_model=MediaResponse)
async def get_media(
    media_id: uuid.UUID,
    db: AsyncSession = Depends(get_session),
):
    """Get media metadata by ID."""
    result = await db.execute(select(Media).where(Media.id == media_id))
    media = result.scalar_one_or_none()
    
    if not media:
        raise HTTPException(status_code=404, detail="Media not found")
    
    return media


@router.delete("/{media_id}", status_code=204)
async def delete_media(
    media_id: uuid.UUID,
    db: AsyncSession = Depends(get_session),
):
    """Delete a media file and its record."""
    result = await db.execute(select(Media).where(Media.id == media_id))
    media = result.scalar_one_or_none()
    
    if not media:
        raise HTTPException(status_code=404, detail="Media not found")
    
    # Delete file from storage
    file_path = UPLOAD_DIR / media.storage_key
    if file_path.exists():
        file_path.unlink()
    
    # Delete database record
    await db.delete(media)
    await db.commit()
    
    return None


@router.get("/", response_model=List[MediaResponse])
async def list_media(
    skip: int = 0,
    limit: int = 50,
    db: AsyncSession = Depends(get_session),
):
    """List all media files."""
    result = await db.execute(
        select(Media)
        .offset(skip)
        .limit(limit)
        .order_by(Media.created_at.desc())
    )
    return result.scalars().all()
