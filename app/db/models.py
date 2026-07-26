import uuid
from datetime import datetime, timezone

from sqlalchemy import (
    Column,
    DateTime,
    ForeignKey,
    Integer,
    String,
    Text,
    JSON,
)
from sqlalchemy.orm import relationship

from app.db.database import Base


def utcnow():
    return datetime.now(timezone.utc)


def make_uuid():
    return str(uuid.uuid4())


class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    email = Column(String(255), nullable=True, index=True)
    business_name = Column(String(255), nullable=True)
    created_at = Column(DateTime(timezone=True), default=utcnow)

    onboarding_sessions = relationship("OnboardingSession", back_populates="user")


class OnboardingSession(Base):
    __tablename__ = "onboarding_sessions"

    id = Column(String(64), primary_key=True, default=make_uuid)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=True)

    status = Column(String(50), default="mode_selection")
    # beginner / advanced / conversational
    mode = Column(String(50), nullable=True)

    current_step = Column(Integer, default=0)

    report_path = Column(Text, nullable=True)
    report_generated_at = Column(DateTime(timezone=True), nullable=True)

    created_at = Column(DateTime(timezone=True), default=utcnow)
    updated_at = Column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)

    user = relationship("User", back_populates="onboarding_sessions")
    answers = relationship("OnboardingAnswer", back_populates="session")
    icp_profile = relationship("ICPProfile", back_populates="session", uselist=False)
    conversation_turns = relationship("ConversationTurn", back_populates="session")
    token_usage_logs = relationship("TokenUsageLog", back_populates="session")
    generation_events = relationship("GenerationEvent", back_populates="session")


class OnboardingAnswer(Base):
    __tablename__ = "onboarding_answers"

    id = Column(Integer, primary_key=True, index=True)
    session_id = Column(String(64), ForeignKey("onboarding_sessions.id"), nullable=False)

    mode = Column(String(50), nullable=True)
    question_key = Column(String(100), nullable=False)
    question_text = Column(Text, nullable=False)
    answer_text = Column(Text, nullable=False)

    created_at = Column(DateTime(timezone=True), default=utcnow)

    session = relationship("OnboardingSession", back_populates="answers")


class ConversationTurn(Base):
    """
    Raw chat transcript for advanced/conversational modes.
    Persisted so the LLM gets full context on every turn.
    Beginner mode doesn't use this — its questions are a static list.
    """
    __tablename__ = "conversation_turns"

    id = Column(Integer, primary_key=True, index=True)
    session_id = Column(String(64), ForeignKey("onboarding_sessions.id"), nullable=False, index=True)
    role = Column(String(20), nullable=False)   # "user" or "assistant"
    content = Column(Text, nullable=False)
    created_at = Column(DateTime(timezone=True), default=utcnow)

    session = relationship("OnboardingSession", back_populates="conversation_turns")


class TokenUsageLog(Base):
    """
    One row per LLM call. Lets you track cost per session, per user, per day.

    call_type values:
      "chat"            — conversational / advanced mode turn
      "icp_generation"  — ICPBuilder.build_from_answers()

    Cost formula (verify current prices at openrouter.ai/models):
      cost_usd = (prompt_tokens / 1_000_000) * input_price
               + (completion_tokens / 1_000_000) * output_price
    """
    __tablename__ = "token_usage_logs"

    id = Column(Integer, primary_key=True, index=True)
    session_id = Column(String(64), ForeignKey("onboarding_sessions.id"), nullable=True, index=True)
    call_type = Column(String(50), nullable=False)
    model = Column(String(100), nullable=True)
    prompt_tokens = Column(Integer, default=0)
    completion_tokens = Column(Integer, default=0)
    total_tokens = Column(Integer, default=0)
    latency_ms = Column(Integer, nullable=True)
    created_at = Column(DateTime(timezone=True), default=utcnow)

    session = relationship("OnboardingSession", back_populates="token_usage_logs")


class GenerationEvent(Base):
    """
    One row per ICP generation attempt — the observability backbone.

    Captures the categorical FACTS of each generation so rates, trends, and
    thresholds can be COMPUTED later. You cannot retroactively categorize an
    error you logged as a plain string, so the categorization is captured here
    at the moment of the event.

    Every dashboard metric (fallback rate, retry rate, per-model reliability,
    latency percentiles, score distribution) is derived from these columns.

    outcome values:
      "success"   — ICP generated normally by the LLM
      "fallback"  — LLM path failed, fallback_profile() used instead
      "error"     — generation failed entirely (rare; should be near-zero)

    fallback_reason values (null unless outcome == "fallback"):
      "insufficient_info"  — too few/low-weight answers (user domain, not a bug)
      "provider_error"     — LLM API call threw (dependency domain)
      "timeout"            — LLM call timed out specifically
      "rate_limit"         — provider returned 429 / quota (common on free tier)
      "schema_invalid"     — LLM responded but output failed Pydantic validation
      "both_models_down"   — primary AND backup both failed (highest severity)
      "unknown"            — uncategorized; investigate and add a category
    """
    __tablename__ = "generation_events"

    id = Column(Integer, primary_key=True, index=True)
    session_id = Column(String(64), ForeignKey("onboarding_sessions.id"), nullable=True, index=True)

    # Outcome — the field every rate is built on.
    outcome = Column(String(30), nullable=False, index=True)
    fallback_reason = Column(String(50), nullable=True, index=True)

    # Segmentation dimensions.
    mode = Column(String(50), nullable=True, index=True)       # beginner/advanced/conversational
    model_used = Column(String(100), nullable=True, index=True)
    used_backup = Column(String(10), default="false")          # "true"/"false" (string for sqlite simplicity)

    # Performance signals.
    latency_ms = Column(Integer, nullable=True)
    retry_count = Column(Integer, default=0)
    prompt_tokens = Column(Integer, default=0)
    completion_tokens = Column(Integer, default=0)
    total_tokens = Column(Integer, default=0)

    # Quality signals.
    quality_score = Column(Integer, nullable=True)
    answers_provided_count = Column(Integer, default=0)

    # Free-text detail for debugging the specific case (NOT for categorization —
    # categorization lives in the typed columns above so it stays queryable).
    error_detail = Column(Text, nullable=True)

    created_at = Column(DateTime(timezone=True), default=utcnow, index=True)

    session = relationship("OnboardingSession", back_populates="generation_events")


class ICPProfile(Base):
    __tablename__ = "icp_profiles"

    id = Column(Integer, primary_key=True, index=True)
    session_id = Column(String(64), ForeignKey("onboarding_sessions.id"), nullable=False, unique=True)

    mode = Column(String(50), nullable=False)
    icp_name = Column(String(255), nullable=True)
    icp_summary = Column(Text, nullable=True)
    icp_data = Column(JSON, nullable=True)
    search_recipe = Column(JSON, nullable=True)
    icp_quality = Column(JSON, nullable=True)
    generation_method = Column(String(100), nullable=True)
    needs_review = Column(String(20), default="false")
    created_at = Column(DateTime(timezone=True), default=utcnow)

    session = relationship("OnboardingSession", back_populates="icp_profile")


class PlanRecommendation(Base):
    __tablename__ = "plan_recommendations"

    id = Column(Integer, primary_key=True, index=True)
    session_id = Column(String(64), ForeignKey("onboarding_sessions.id"), nullable=True)
    recommended_plan = Column(String(50), nullable=False)
    confidence = Column(Integer, default=80)
    reasons = Column(JSON, nullable=True)
    next_steps = Column(JSON, nullable=True)
    created_at = Column(DateTime(timezone=True), default=utcnow)


class AIDatasetExample(Base):
    __tablename__ = "ai_dataset_examples"

    id = Column(Integer, primary_key=True, index=True)
    session_id = Column(String(64), ForeignKey("onboarding_sessions.id"), nullable=True)
    task_type = Column(String(100), nullable=False)
    input_json = Column(JSON, nullable=False)
    output_json = Column(JSON, nullable=False)
    tags = Column(JSON, nullable=True)
    feedback_label = Column(String(50), nullable=True)
    feedback_notes = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=True), default=utcnow)