from sqlalchemy import (
    Boolean,
    Column,
    DateTime,
    ForeignKey,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    Index,
)
from sqlalchemy.dialects.postgresql import ARRAY, JSONB, UUID
from sqlalchemy.orm import declarative_base, relationship, remote, foreign
import sqlalchemy as sa
from datetime import datetime, timezone

Base = declarative_base()


def now():
    return datetime.now(tz=timezone.utc)


class User(Base):
    __tablename__ = "users"
    id = Column(UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()"))
    email = Column(String, unique=True, nullable=False, index=True)
    email_verified = Column(Boolean, default=False)
    password_hash = Column(Text, nullable=True)
    password_algo = Column(String, nullable=True)
    preferred_username = Column(String, nullable=True)
    display_name = Column(String, nullable=True)
    # Optional OAuth provider id (e.g. Google 'sub')
    google_id = Column(String, nullable=True, unique=True, index=True)
    # URL to a profile picture returned by OAuth provider
    profile_picture_url = Column(Text, nullable=True)
    locale = Column(String, nullable=True)
    meta_data = Column(JSONB, nullable=False, server_default=sa.text("'{}'::jsonb"))
    created_at = Column(DateTime(timezone=True), default=now)
    updated_at = Column(DateTime(timezone=True), default=now, onupdate=now)
    deleted_at = Column(DateTime(timezone=True), nullable=True)

    roles = relationship("UserRole", foreign_keys="UserRole.user_id", back_populates="user")
    taxonomy_stats = relationship("UserTaxonomyStats", back_populates="user", cascade="all, delete-orphan")


class Role(Base):
    __tablename__ = "roles"
    id = Column(UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()"))
    name = Column(String, unique=True, nullable=False)
    description = Column(Text, nullable=True)
    meta_data = Column(JSONB, nullable=False, server_default=sa.text("'{}'::jsonb"))
    
    permissions = relationship("Permission", secondary="role_permissions", back_populates="roles")


class Permission(Base):
    __tablename__ = "permissions"
    id = Column(UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()"))
    name = Column(String, unique=True, nullable=False)
    description = Column(Text, nullable=True)

    roles = relationship("Role", secondary="role_permissions", back_populates="permissions")


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
    role = relationship("Role")
    assigner = relationship("User", foreign_keys=[assigned_by])


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

    user = relationship("User")
    provider = relationship("OAuthProvider")


class JWTRevocation(Base):
    __tablename__ = "jwt_revocations"
    jti = Column(String, primary_key=True)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=True, index=True)
    expires_at = Column(DateTime(timezone=True), nullable=True)
    revoked_at = Column(DateTime(timezone=True), nullable=True)
    reason = Column(Text, nullable=True)
    meta_data = Column(JSONB, nullable=False, server_default=sa.text("'{}'::jsonb"))

    user = relationship("User")


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

    user = relationship("User")


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
    
    uploader = relationship("User")

# --- NEW/MODIFIED TAXONOMY SECTION ---
# This single table replaces Subject, Chapter, and Topic.
class Taxonomy(Base):
    __tablename__ = "taxonomy"
    id = Column(UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()"))
    name = Column(String, nullable=False)
    description = Column(Text, nullable=True)
    # Type allows differentiation: 'subject', 'chapter', 'topic', 'subtopic', etc.
    node_type = Column(String, nullable=False, index=True) 
    parent_id = Column(UUID(as_uuid=True), ForeignKey("taxonomy.id"), nullable=True, index=True)
    # path is for materialized path (ltree in postgres), e.g. "subject_id.chapter_id.topic_id"
    path = Column(String, nullable=True, index=True) 
    meta_data = Column(JSONB, nullable=False, server_default=sa.text("'{}'::jsonb"))
    created_at = Column(DateTime(timezone=True), default=now)
    updated_at = Column(DateTime(timezone=True), default=now, onupdate=now)

    # Self-referencing relationship
    parent = relationship("Taxonomy", remote_side=[id], back_populates="children")
    children = relationship("Taxonomy", back_populates="parent", cascade="all, delete-orphan")
    
    question_links = relationship("QuestionTaxonomy", back_populates="taxonomy_node")
    user_stats = relationship("UserTaxonomyStats", back_populates="taxonomy_node")


# --- QUIZ & QUESTION SECTION ---

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
    status = Column(String, nullable=False, default="draft")  # e.g., 'draft', 'published', 'archived'

    creator = relationship("User")
    versions = relationship("QuizVersion", back_populates="quiz", order_by="QuizVersion.version_number.desc()", cascade="all, delete-orphan")
    attempts = relationship("QuizAttempt", back_populates="quiz")
    # Questions linked to this quiz via association table
    questions = relationship("Question", secondary="quiz_questions", back_populates="quizzes")


class QuizVersion(Base):
    __tablename__ = "quiz_versions"
    id = Column(UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()"))
    quiz_id = Column(UUID(as_uuid=True), ForeignKey("quizzes.id"), nullable=False, index=True)
    version_number = Column(Integer, nullable=False)
    # Snapshot contains the full quiz structure (questions, order, settings) at this version
    snapshot = Column(JSONB, nullable=False) 
    created_at = Column(DateTime(timezone=True), default=now)
    created_by = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=True)

    quiz = relationship("Quiz", back_populates="versions")
    creator = relationship("User")


class Question(Base):
    __tablename__ = "questions"
    id = Column(UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()"))
    # Use canonical_id to link different versions of the *same* conceptual question
    canonical_id = Column(UUID(as_uuid=True), nullable=True, index=True, server_default=sa.text("gen_random_uuid()"))
    title = Column(String, nullable=True) # Internal title
    description = Column(Text, nullable=True) # Internal description or notes
    answer_type = Column(String, nullable=False, default="options") # 'options', 'text', 'numeric', 'match'
    scoring = Column(JSONB, nullable=False, server_default=sa.text("'{}'::jsonb")) # e.g. {"points_per_part": 1}
    explanation = Column(JSONB, nullable=True) # Rich text explanation: [{"type": "text", "content": "..."}]
    difficulty = Column(Integer, nullable=True) # e.g., 1-5
    estimated_time_seconds = Column(Integer, nullable=True)
    meta_data = Column(JSONB, nullable=False, server_default=sa.text("'{}'::jsonb"))
    created_by = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=True)
    created_at = Column(DateTime(timezone=True), default=now)
    updated_at = Column(DateTime(timezone=True), default=now, onupdate=now)

    creator = relationship("User")
    parts = relationship("QuestionPart", back_populates="question", order_by="QuestionPart.index", cascade="all, delete-orphan")
    options = relationship("Option", back_populates="question", order_by="Option.index", cascade="all, delete-orphan")
    versions = relationship("QuestionVersion", back_populates="question", order_by="QuestionVersion.version_number.desc()", cascade="all, delete-orphan")
    taxonomy_links = relationship("QuestionTaxonomy", back_populates="question", cascade="all, delete-orphan")
    quizzes = relationship("Quiz", secondary="quiz_questions", back_populates="questions")


# This new table replaces QuestionTopic and QuestionChapter
class QuestionTaxonomy(Base):
    __tablename__ = "question_taxonomy"
    id = Column(UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()"))
    question_id = Column(UUID(as_uuid=True), ForeignKey("questions.id"), nullable=False, index=True)
    taxonomy_id = Column(UUID(as_uuid=True), ForeignKey("taxonomy.id"), nullable=False, index=True)
    relevance_score = Column(Numeric, nullable=True, default=1) # How relevant this topic is

    question = relationship("Question", back_populates="taxonomy_links")
    taxonomy_node = relationship("Taxonomy", back_populates="question_links")

    __table_args__ = (UniqueConstraint("question_id", "taxonomy_id", name="uq_question_taxonomy"),)


class QuestionVersion(Base):
    __tablename__ = "question_versions"
    id = Column(UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()"))
    question_id = Column(UUID(as_uuid=True), ForeignKey("questions.id"), nullable=False, index=True)
    version_number = Column(Integer, nullable=False)
    # Snapshot contains the full question (parts, options, correct answers) at this version
    snapshot = Column(JSONB, nullable=False)
    created_at = Column(DateTime(timezone=True), default=now)
    created_by = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=True)

    question = relationship("Question", back_populates="versions")
    creator = relationship("User")


class QuestionPart(Base):
    __tablename__ = "question_parts"
    id = Column(UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()"))
    question_id = Column(UUID(as_uuid=True), ForeignKey("questions.id"), nullable=False, index=True)
    index = Column(Integer, nullable=False) # Order of the part
    part_type = Column(String, nullable=False) # 'text', 'image', 'code_snippet', 'video'
    content = Column(Text, nullable=True) # For 'text' or 'code_snippet'
    content_json = Column(JSONB, nullable=True) # For rich text editor content
    media_id = Column(UUID(as_uuid=True), ForeignKey("media.id"), nullable=True)
    meta_data = Column(JSONB, nullable=False, server_default=sa.text("'{}'::jsonb"))

    question = relationship("Question", back_populates="parts")
    media = relationship("Media", lazy="joined") # lazy='joined' can be good if you always show media


class Option(Base):
    __tablename__ = "options"
    id = Column(UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()"))
    question_id = Column(UUID(as_uuid=True), ForeignKey("questions.id"), nullable=False, index=True)
    label = Column(String, nullable=True) # Internal label (e.g., 'A', 'B')
    index = Column(Integer, nullable=True) # Order of the option
    is_correct = Column(Boolean, default=False)
    weight = Column(Numeric, default=1) # For partial scoring
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
    part_type = Column(String, nullable=False) # 'text', 'image'
    content = Column(Text, nullable=True)
    media_id = Column(UUID(as_uuid=True), ForeignKey("media.id"), nullable=True)

    option = relationship("Option", back_populates="parts")
    media = relationship("Media", lazy="joined")


# --- ATTEMPT & STATISTICS SECTION ---

class QuizAttempt(Base):
    __tablename__ = "quiz_attempts"
    id = Column(UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()"))
    quiz_id = Column(UUID(as_uuid=True), ForeignKey("quizzes.id"), nullable=False, index=True)
    # Link the attempt to the QuizVersion that was used for this attempt (nullable for older attempts)
    quiz_version_id = Column(UUID(as_uuid=True), ForeignKey("quiz_versions.id"), nullable=True, index=True)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=True, index=True)
    # This could also link to a quiz_version_id
    # quiz_version_id = Column(UUID(as_uuid=True), ForeignKey("quiz_versions.id"), nullable=False)
    started_at = Column(DateTime(timezone=True), default=now)
    submitted_at = Column(DateTime(timezone=True), nullable=True)
    duration_seconds = Column(Integer, nullable=True)
    score = Column(Numeric, nullable=True)
    max_score = Column(Numeric, nullable=True)
    status = Column(String, nullable=False, default="in_progress") # 'in_progress', 'completed', 'aborted'
    meta_data = Column(JSONB, nullable=False, server_default=sa.text("'{}'::jsonb"))

    quiz = relationship("Quiz", back_populates="attempts")
    user = relationship("User")
    question_attempts = relationship("QuestionAttempt", back_populates="quiz_attempt", cascade="all, delete-orphan")


class QuestionAttempt(Base):
    __tablename__ = "question_attempts"
    id = Column(UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()"))
    quiz_attempt_id = Column(UUID(as_uuid=True), ForeignKey("quiz_attempts.id"), nullable=True, index=True)
    question_id = Column(UUID(as_uuid=True), ForeignKey("questions.id"), nullable=False, index=True)
    # This could also link to a question_version_id
    # question_version_id = Column(UUID(as_uuid=True), ForeignKey("question_versions.id"), nullable=False)
    attempt_index = Column(Integer, nullable=True) # e.g., 1st, 2nd try on this question
    started_at = Column(DateTime(timezone=True), default=now)
    submitted_at = Column(DateTime(timezone=True), nullable=True)
    scored_at = Column(DateTime(timezone=True), nullable=True)
    score = Column(Numeric, nullable=True)
    max_score = Column(Numeric, nullable=True)
    grading = Column(JSONB, nullable=True) # Store details of the grading (e.g., which parts were right/wrong)
    meta_data = Column(JSONB, nullable=False, server_default=sa.text("'{}'::jsonb"))

    quiz_attempt = relationship("QuizAttempt", back_populates="question_attempts")
    question = relationship("Question")
    parts = relationship("QuestionAttemptPart", back_populates="question_attempt", cascade="all, delete-orphan")


class QuestionAttemptPart(Base):
    __tablename__ = "question_attempt_parts"
    id = Column(UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()"))
    question_attempt_id = Column(UUID(as_uuid=True), ForeignKey("question_attempts.id"), nullable=False, index=True)
    question_part_id = Column(UUID(as_uuid=True), ForeignKey("question_parts.id"), nullable=True) # If question has multiple inputs
    selected_option_ids = Column(ARRAY(UUID(as_uuid=True)), nullable=True) # For multiple-choice
    text_response = Column(Text, nullable=True) # For free-text
    numeric_response = Column(Numeric, nullable=True) # For numeric
    file_media_id = Column(UUID(as_uuid=True), ForeignKey("media.id"), nullable=True) # For file upload
    raw_response = Column(JSONB, nullable=True) # For complex response types
    created_at = Column(DateTime(timezone=True), default=now)
    
    question_attempt = relationship("QuestionAttempt", back_populates="parts")
    file_media = relationship("Media")
    # You could add relationships to selected_option_ids but it's complex; 
    # The ARRAY is often sufficient for storing the answer.


# --- NEW STATISTICS TABLE ---
# This is the key to your stats requirement.
class UserTaxonomyStats(Base):
    __tablename__ = "user_taxonomy_stats"
    id = Column(UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()"))
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False, index=True)
    taxonomy_id = Column(UUID(as_uuid=True), ForeignKey("taxonomy.id"), nullable=False, index=True)
    
    questions_attempted = Column(Integer, nullable=False, default=0)
    questions_correct = Column(Integer, nullable=False, default=0)
    total_score = Column(Numeric, nullable=False, default=0)
    max_possible_score = Column(Numeric, nullable=False, default=0)
    # Store derived value for easy reads. Can be updated via trigger or application logic.
    average_score_percent = Column(Numeric, nullable=False, default=0) 
    
    first_attempt_at = Column(DateTime(timezone=True), default=now)
    last_attempt_at = Column(DateTime(timezone=True), default=now, onupdate=now)
    
    # Store things like 'proficiency_level': 'novice'/'advanced' or 'streak': 5
    meta_data = Column(JSONB, nullable=False, server_default=sa.text("'{}'::jsonb")) 

    user = relationship("User", back_populates="taxonomy_stats")
    taxonomy_node = relationship("Taxonomy", back_populates="user_stats")

    __table_args__ = (UniqueConstraint("user_id", "taxonomy_id", name="uq_user_taxonomy_stats"),)


# --- DYNAMIC RELATIONSHIP SECTION ---
# This table is for "interlink anything with anything"
class EntityRelationship(Base):
    __tablename__ = "entity_relationships"
    id = Column(UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()"))
    
    # Source Entity (e.g., 'taxonomy', 'question', 'quiz')
    source_type = Column(String, nullable=False, index=True)
    source_id = Column(UUID(as_uuid=True), nullable=False, index=True)
    
    # Target Entity (e.g., 'taxonomy', 'question', 'quiz')
    target_type = Column(String, nullable=False, index=True)
    target_id = Column(UUID(as_uuid=True), nullable=False, index=True)
    
    # Type of relationship (e.g., 'prerequisite_for', 'related_to', 'duplicates')
    relation_type = Column(String, nullable=False, index=True) 
    
    meta_data = Column(JSONB, nullable=False, server_default=sa.text("'{}'::jsonb"))
    created_by = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=True)
    created_at = Column(DateTime(timezone=True), default=now)

    creator = relationship("User")
    
    __table_args__ = (
        Index("idx_entity_relationship_source", "source_type", "source_id"),
        Index("idx_entity_relationship_target", "target_type", "target_id"),
    )


# Association table for quizzes -> questions
class QuizQuestion(Base):
    __tablename__ = "quiz_questions"
    id = Column(UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()"))
    quiz_id = Column(UUID(as_uuid=True), ForeignKey("quizzes.id"), nullable=False, index=True)
    question_id = Column(UUID(as_uuid=True), ForeignKey("questions.id"), nullable=False, index=True)
    index = Column(Integer, nullable=True)
    meta_data = Column(JSONB, nullable=False, server_default=sa.text("'{}'::jsonb"))

    __table_args__ = (UniqueConstraint("quiz_id", "question_id", name="uq_quiz_question"),)
