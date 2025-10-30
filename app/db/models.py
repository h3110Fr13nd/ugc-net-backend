from sqlalchemy import (
    Boolean,
    Column,
    DateTime,
    ForeignKey,
    Integer,
    Numeric,
    String,
    Text,
)
from sqlalchemy.dialects.postgresql import ARRAY, JSONB, UUID
from sqlalchemy.orm import declarative_base, relationship
import sqlalchemy as sa
from datetime import datetime

Base = declarative_base()


def now():
    return datetime.utcnow()


class User(Base):
    __tablename__ = "users"
    id = Column(UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()"))
    email = Column(String, unique=True, nullable=False, index=True)
    email_verified = Column(Boolean, default=False)
    password_hash = Column(Text, nullable=True)
    password_algo = Column(String, nullable=True)
    preferred_username = Column(String, nullable=True)
    display_name = Column(String, nullable=True)
    locale = Column(String, nullable=True)
    meta_data = Column(JSONB, nullable=False, server_default=sa.text("'{}'::jsonb"))
    created_at = Column(DateTime(timezone=True), default=now)
    updated_at = Column(DateTime(timezone=True), default=now, onupdate=now)
    deleted_at = Column(DateTime(timezone=True), nullable=True)

    roles = relationship("UserRole", foreign_keys="UserRole.user_id", back_populates="user")


class Role(Base):
    __tablename__ = "roles"
    id = Column(UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()"))
    name = Column(String, unique=True, nullable=False)
    description = Column(Text, nullable=True)
    meta_data = Column(JSONB, nullable=False, server_default=sa.text("'{}'::jsonb"))


class Permission(Base):
    __tablename__ = "permissions"
    id = Column(UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()"))
    name = Column(String, unique=True, nullable=False)
    description = Column(Text, nullable=True)


class RolePermission(Base):
    __tablename__ = "role_permissions"
    role_id = Column(UUID(as_uuid=True), ForeignKey("roles.id"), primary_key=True)
    permission_id = Column(UUID(as_uuid=True), ForeignKey("permissions.id"), primary_key=True)


class UserRole(Base):
    __tablename__ = "user_roles"
    id = Column(UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()"))
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False, index=True)
    role_id = Column(UUID(as_uuid=True), ForeignKey("roles.id"), nullable=False, index=True)
    assigned_by = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=True)
    assigned_at = Column(DateTime(timezone=True), default=now)

    user = relationship("User", foreign_keys=[user_id], back_populates="roles")


class OAuthProvider(Base):
    __tablename__ = "oauth_providers"
    id = Column(UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()"))
    provider_name = Column(String, unique=True, nullable=False)
    meta_data = Column(JSONB, nullable=False, server_default=sa.text("'{}'::jsonb"))


class UserOAuthAccount(Base):
    __tablename__ = "user_oauth_accounts"
    id = Column(UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()"))
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False, index=True)
    provider_id = Column(UUID(as_uuid=True), ForeignKey("oauth_providers.id"), nullable=False)
    provider_account_id = Column(String, nullable=False)
    provider_account_email = Column(String, nullable=True)
    access_token_encrypted = Column(Text, nullable=True)
    refresh_token_encrypted = Column(Text, nullable=True)
    scope = Column(Text, nullable=True)
    raw_profile = Column(JSONB, nullable=True)
    created_at = Column(DateTime(timezone=True), default=now)
    updated_at = Column(DateTime(timezone=True), default=now, onupdate=now)


class JWTRevocation(Base):
    __tablename__ = "jwt_revocations"
    jti = Column(String, primary_key=True)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=True, index=True)
    expires_at = Column(DateTime(timezone=True), nullable=True)
    revoked_at = Column(DateTime(timezone=True), nullable=True)
    reason = Column(Text, nullable=True)
    meta_data = Column(JSONB, nullable=False, server_default=sa.text("'{}'::jsonb"))


class RefreshToken(Base):
    __tablename__ = "refresh_tokens"
    id = Column(UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()"))
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False, index=True)
    refresh_token_hash = Column(Text, nullable=False)
    device_info = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=True), default=now)
    last_used_at = Column(DateTime(timezone=True), nullable=True)
    revoked_at = Column(DateTime(timezone=True), nullable=True)
    expires_at = Column(DateTime(timezone=True), nullable=True)
    meta_data = Column(JSONB, nullable=False, server_default=sa.text("'{}'::jsonb"))
    rotate_on_use = Column(Boolean, default=True)


class Media(Base):
    __tablename__ = "media"
    id = Column(UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()"))
    url = Column(Text, nullable=False)
    storage_key = Column(Text, unique=True, nullable=False)
    mime_type = Column(String, nullable=True)
    width = Column(Integer, nullable=True)
    height = Column(Integer, nullable=True)
    size_bytes = Column(Integer, nullable=True)
    checksum = Column(String, nullable=True, index=True)
    uploaded_by = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=True)
    meta_data = Column(JSONB, nullable=False, server_default=sa.text("'{}'::jsonb"))
    created_at = Column(DateTime(timezone=True), default=now)
    updated_at = Column(DateTime(timezone=True), default=now, onupdate=now)


class Quiz(Base):
    __tablename__ = "quizzes"
    id = Column(UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()"))
    title = Column(String, nullable=False)
    description = Column(Text, nullable=True)
    meta_data = Column(JSONB, nullable=False, server_default=sa.text("'{}'::jsonb"))
    created_by = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=True)
    created_at = Column(DateTime(timezone=True), default=now)
    updated_at = Column(DateTime(timezone=True), default=now, onupdate=now)
    published_at = Column(DateTime(timezone=True), nullable=True)
    status = Column(String, nullable=False, default="draft")


class QuizVersion(Base):
    __tablename__ = "quiz_versions"
    id = Column(UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()"))
    quiz_id = Column(UUID(as_uuid=True), ForeignKey("quizzes.id"), nullable=False)
    version_number = Column(Integer, nullable=False)
    snapshot = Column(JSONB, nullable=False)
    created_at = Column(DateTime(timezone=True), default=now)
    created_by = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=True)


class Question(Base):
    __tablename__ = "questions"
    id = Column(UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()"))
    canonical_id = Column(UUID(as_uuid=True), nullable=True, index=True)
    title = Column(String, nullable=True)
    description = Column(Text, nullable=True)
    answer_type = Column(String, nullable=False, default="options")
    scoring = Column(JSONB, nullable=False, server_default=sa.text("'{}'::jsonb"))
    difficulty = Column(Integer, nullable=True)
    estimated_time_seconds = Column(Integer, nullable=True)
    meta_data = Column(JSONB, nullable=False, server_default=sa.text("'{}'::jsonb"))
    created_by = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=True)
    created_at = Column(DateTime(timezone=True), default=now)
    updated_at = Column(DateTime(timezone=True), default=now, onupdate=now)
    
    parts = relationship("QuestionPart", back_populates="question", order_by="QuestionPart.index", cascade="all, delete-orphan")
    options = relationship("Option", back_populates="question", order_by="Option.index", cascade="all, delete-orphan")


class QuestionVersion(Base):
    __tablename__ = "question_versions"
    id = Column(UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()"))
    question_id = Column(UUID(as_uuid=True), ForeignKey("questions.id"), nullable=False)
    version_number = Column(Integer, nullable=False)
    snapshot = Column(JSONB, nullable=False)
    created_at = Column(DateTime(timezone=True), default=now)
    created_by = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=True)


class QuestionPart(Base):
    __tablename__ = "question_parts"
    id = Column(UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()"))
    question_id = Column(UUID(as_uuid=True), ForeignKey("questions.id"), nullable=False, index=True)
    index = Column(Integer, nullable=False)
    part_type = Column(String, nullable=False)
    content = Column(Text, nullable=True)
    content_json = Column(JSONB, nullable=True)
    media_id = Column(UUID(as_uuid=True), ForeignKey("media.id"), nullable=True)
    meta_data = Column(JSONB, nullable=False, server_default=sa.text("'{}'::jsonb"))
    
    question = relationship("Question", back_populates="parts")
    media = relationship("Media")


class Option(Base):
    __tablename__ = "options"
    id = Column(UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()"))
    question_id = Column(UUID(as_uuid=True), ForeignKey("questions.id"), nullable=False, index=True)
    label = Column(String, nullable=True)
    index = Column(Integer, nullable=True)
    is_correct = Column(Boolean, default=False)
    weight = Column(Numeric, default=1)
    meta_data = Column(JSONB, nullable=False, server_default=sa.text("'{}'::jsonb"))
    created_at = Column(DateTime(timezone=True), default=now)
    updated_at = Column(DateTime(timezone=True), default=now, onupdate=now)
    
    question = relationship("Question", back_populates="options")
    parts = relationship("OptionPart", back_populates="option", order_by="OptionPart.index", cascade="all, delete-orphan")


class OptionPart(Base):
    __tablename__ = "option_parts"
    id = Column(UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()"))
    option_id = Column(UUID(as_uuid=True), ForeignKey("options.id"), nullable=False, index=True)
    index = Column(Integer, nullable=False)
    part_type = Column(String, nullable=False)
    content = Column(Text, nullable=True)
    media_id = Column(UUID(as_uuid=True), ForeignKey("media.id"), nullable=True)
    
    option = relationship("Option", back_populates="parts")
    media = relationship("Media")


class QuizAttempt(Base):
    __tablename__ = "quiz_attempts"
    id = Column(UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()"))
    quiz_id = Column(UUID(as_uuid=True), ForeignKey("quizzes.id"), nullable=False)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=True, index=True)
    started_at = Column(DateTime(timezone=True), default=now)
    submitted_at = Column(DateTime(timezone=True), nullable=True)
    duration_seconds = Column(Integer, nullable=True)
    score = Column(Numeric, nullable=True)
    max_score = Column(Numeric, nullable=True)
    status = Column(String, nullable=False, default="in_progress")
    meta_data = Column(JSONB, nullable=False, server_default=sa.text("'{}'::jsonb"))


class QuestionAttempt(Base):
    __tablename__ = "question_attempts"
    id = Column(UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()"))
    quiz_attempt_id = Column(UUID(as_uuid=True), ForeignKey("quiz_attempts.id"), nullable=True, index=True)
    question_id = Column(UUID(as_uuid=True), ForeignKey("questions.id"), nullable=False, index=True)
    attempt_index = Column(Integer, nullable=True)
    started_at = Column(DateTime(timezone=True), default=now)
    submitted_at = Column(DateTime(timezone=True), nullable=True)
    scored_at = Column(DateTime(timezone=True), nullable=True)
    score = Column(Numeric, nullable=True)
    grading = Column(JSONB, nullable=True)
    meta_data = Column(JSONB, nullable=False, server_default=sa.text("'{}'::jsonb"))


class QuestionAttemptPart(Base):
    __tablename__ = "question_attempt_parts"
    id = Column(UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()"))
    question_attempt_id = Column(UUID(as_uuid=True), ForeignKey("question_attempts.id"), nullable=False, index=True)
    question_part_id = Column(UUID(as_uuid=True), ForeignKey("question_parts.id"), nullable=True)
    selected_option_ids = Column(ARRAY(UUID(as_uuid=True)), nullable=True)
    text_response = Column(Text, nullable=True)
    numeric_response = Column(Numeric, nullable=True)
    file_media_id = Column(UUID(as_uuid=True), ForeignKey("media.id"), nullable=True)
    raw_response = Column(JSONB, nullable=True)
    created_at = Column(DateTime(timezone=True), default=now)


class Subject(Base):
    __tablename__ = "subjects"
    id = Column(UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()"))
    name = Column(String, nullable=False)
    meta_data = Column(JSONB, nullable=False, server_default=sa.text("'{}'::jsonb"))


class Chapter(Base):
    __tablename__ = "chapters"
    id = Column(UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()"))
    subject_id = Column(UUID(as_uuid=True), ForeignKey("subjects.id"), nullable=True, index=True)
    name = Column(String, nullable=False)
    meta_data = Column(JSONB, nullable=False, server_default=sa.text("'{}'::jsonb"))


class Topic(Base):
    __tablename__ = "topics"
    id = Column(UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()"))
    name = Column(String, nullable=False)
    parent_id = Column(UUID(as_uuid=True), ForeignKey("topics.id"), nullable=True)
    path = Column(String, nullable=True)  # recommend using ltree in DB
    meta_data = Column(JSONB, nullable=False, server_default=sa.text("'{}'::jsonb"))
    created_at = Column(DateTime(timezone=True), default=now)


class QuestionTopic(Base):
    __tablename__ = "question_topics"
    id = Column(UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()"))
    question_id = Column(UUID(as_uuid=True), ForeignKey("questions.id"), nullable=False, index=True)
    topic_id = Column(UUID(as_uuid=True), ForeignKey("topics.id"), nullable=False, index=True)
    relevance_score = Column(Numeric, nullable=True)


class QuestionChapter(Base):
    __tablename__ = "question_chapters"
    question_id = Column(UUID(as_uuid=True), ForeignKey("questions.id"), primary_key=True)
    chapter_id = Column(UUID(as_uuid=True), ForeignKey("chapters.id"), primary_key=True)


class TopicAssociation(Base):
    __tablename__ = "topic_associations"
    id = Column(UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()"))
    from_topic_id = Column(UUID(as_uuid=True), ForeignKey("topics.id"), nullable=False)
    to_topic_id = Column(UUID(as_uuid=True), ForeignKey("topics.id"), nullable=False)
    association_type = Column(String, nullable=False)
    meta_data = Column(JSONB, nullable=False, server_default=sa.text("'{}'::jsonb"))


class EntityRelationship(Base):
    __tablename__ = "entity_relationships"
    id = Column(UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()"))
    source_type = Column(String, nullable=False)
    source_id = Column(UUID(as_uuid=True), nullable=False)
    target_type = Column(String, nullable=False)
    target_id = Column(UUID(as_uuid=True), nullable=False)
    relation_type = Column(String, nullable=False)
    meta_data = Column(JSONB, nullable=False, server_default=sa.text("'{}'::jsonb"))
    created_by = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=True)
    created_at = Column(DateTime(timezone=True), default=now)

