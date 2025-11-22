"""Pydantic schemas for API request/response models."""
from typing import Optional, List, Any
from pydantic import BaseModel, Field, ConfigDict
from uuid import UUID
from datetime import datetime
from decimal import Decimal


# Media schemas
class MediaBase(BaseModel):
    url: str
    storage_key: str
    mime_type: Optional[str] = None
    width: Optional[int] = None
    height: Optional[int] = None
    size_bytes: Optional[int] = None
    checksum: Optional[str] = None
    meta_data: dict = Field(default_factory=dict)


class MediaCreate(MediaBase):
    uploaded_by: Optional[UUID] = None


class MediaResponse(MediaBase):
    id: UUID
    uploaded_by: Optional[UUID] = None
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


# Question/Option Part schemas
class QuestionPartBase(BaseModel):
    index: int
    part_type: str  # 'text', 'image', 'diagram', 'latex', 'code', 'audio', 'video', 'table'
    content: Optional[str] = None
    content_json: Optional[dict] = None
    media_id: Optional[UUID] = None
    meta_data: dict = Field(default_factory=dict)


class QuestionPartCreate(QuestionPartBase):
    pass


class QuestionPartResponse(QuestionPartBase):
    id: UUID
    question_id: UUID
    media: Optional[MediaResponse] = None

    model_config = ConfigDict(from_attributes=True)


class OptionPartBase(BaseModel):
    index: int
    part_type: str
    content: Optional[str] = None
    media_id: Optional[UUID] = None


class OptionPartCreate(OptionPartBase):
    pass


class OptionPartResponse(OptionPartBase):
    id: UUID
    option_id: UUID
    media: Optional[MediaResponse] = None

    model_config = ConfigDict(from_attributes=True)


# Option schemas
class OptionBase(BaseModel):
    label: Optional[str] = None
    index: Optional[int] = None
    is_correct: bool = False
    weight: Decimal = Decimal("1.0")
    meta_data: dict = Field(default_factory=dict)


class OptionCreate(OptionBase):
    parts: List[OptionPartCreate] = Field(default_factory=list)


class OptionUpdate(BaseModel):
    label: Optional[str] = None
    index: Optional[int] = None
    is_correct: Optional[bool] = None
    weight: Optional[Decimal] = None
    meta_data: Optional[dict] = None
    parts: Optional[List[OptionPartCreate]] = None


class OptionResponse(OptionBase):
    id: UUID
    question_id: UUID
    parts: List[OptionPartResponse] = Field(default_factory=list)
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


# Question schemas
class QuestionBase(BaseModel):
    title: Optional[str] = None
    description: Optional[str] = None
    answer_type: str = "options"  # 'options', 'text', 'numeric', 'integer', 'regex', 'file', 'composite'
    scoring: dict = Field(default_factory=dict)
    difficulty: Optional[int] = None
    estimated_time_seconds: Optional[int] = None
    meta_data: dict = Field(default_factory=dict)


class QuestionCreate(QuestionBase):
    canonical_id: Optional[UUID] = None
    parts: List[QuestionPartCreate] = Field(default_factory=list)
    options: List[OptionCreate] = Field(default_factory=list)
    created_by: Optional[UUID] = None
    taxonomy_ids: Optional[List[UUID]] = None


class QuestionUpdate(BaseModel):
    title: Optional[str] = None
    description: Optional[str] = None
    answer_type: Optional[str] = None
    scoring: Optional[dict] = None
    difficulty: Optional[int] = None
    estimated_time_seconds: Optional[int] = None
    meta_data: Optional[dict] = None
    parts: Optional[List[QuestionPartCreate]] = None
    options: Optional[List[OptionCreate]] = None


class QuestionResponse(QuestionBase):
    id: UUID
    canonical_id: Optional[UUID] = None
    parts: List[QuestionPartResponse] = Field(default_factory=list)
    options: List[OptionResponse] = Field(default_factory=list)
    created_by: Optional[UUID] = None
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class QuestionListResponse(BaseModel):
    questions: List[QuestionResponse]
    total: int
    page: int
    page_size: int


# Quiz schemas
class QuizBase(BaseModel):
    title: str
    description: Optional[str] = None
    meta_data: dict = Field(default_factory=dict)
    status: str = "draft"  # 'draft', 'published', 'archived'


class QuizCreate(QuizBase):
    created_by: Optional[UUID] = None


class QuizUpdate(BaseModel):
    title: Optional[str] = None
    description: Optional[str] = None
    meta_data: Optional[dict] = None
    status: Optional[str] = None


class QuizResponse(QuizBase):
    id: UUID
    created_by: Optional[UUID] = None
    created_at: datetime
    updated_at: datetime
    published_at: Optional[datetime] = None

    model_config = ConfigDict(from_attributes=True)


# Attempt schemas
class QuestionAttemptPartCreate(BaseModel):
    question_part_id: Optional[UUID] = None
    selected_option_ids: Optional[List[UUID]] = None
    text_response: Optional[str] = None
    numeric_response: Optional[Decimal] = None
    file_media_id: Optional[UUID] = None
    raw_response: Optional[dict] = None


class QuestionAttemptCreate(BaseModel):
    question_id: UUID
    quiz_attempt_id: Optional[UUID] = None
    attempt_index: Optional[int] = None
    parts: List[QuestionAttemptPartCreate] = Field(default_factory=list)
    meta_data: dict = Field(default_factory=dict)


class QuestionAttemptResponse(BaseModel):
    id: UUID
    quiz_attempt_id: Optional[UUID] = None
    question_id: UUID
    attempt_index: Optional[int] = None
    started_at: datetime
    submitted_at: Optional[datetime] = None
    scored_at: Optional[datetime] = None
    score: Optional[Decimal] = None
    grading: Optional[dict] = None
    meta_data: dict

    model_config = ConfigDict(from_attributes=True)


class QuizAttemptCreate(BaseModel):
    quiz_id: UUID
    user_id: Optional[UUID] = None
    meta_data: dict = Field(default_factory=dict)


class QuizAttemptResponse(BaseModel):
    id: UUID
    quiz_id: UUID
    user_id: Optional[UUID] = None
    started_at: datetime
    submitted_at: Optional[datetime] = None
    duration_seconds: Optional[int] = None
    score: Optional[Decimal] = None
    max_score: Optional[Decimal] = None
    status: str
    meta_data: dict

    model_config = ConfigDict(from_attributes=True)


# Taxonomy schemas
class TaxonomyBase(BaseModel):
    name: str
    description: Optional[str] = None
    node_type: str = "topic"
    parent_id: Optional[UUID] = None
    meta_data: dict = Field(default_factory=dict)


class TaxonomyCreate(TaxonomyBase):
    pass


class TaxonomyResponse(TaxonomyBase):
    id: UUID
    path: Optional[str] = None
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class TaxonomyTreeResponse(TaxonomyResponse):
    children: List["TaxonomyTreeResponse"] = Field(default_factory=list)


# Forward ref resolution
TaxonomyTreeResponse.model_rebuild()
