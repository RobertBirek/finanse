import uuid

from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    ForeignKey,
    Identity,
    Index,
    LargeBinary,
    String,
    Text,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class AdvisorAIProfile(Base):
    __tablename__ = "advisor_ai_profiles"

    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), unique=True
    )
    model: Mapped[str | None] = mapped_column(String(128))
    encrypted_key: Mapped[bytes | None] = mapped_column(LargeBinary)


class AdvisorPromptVersion(Base):
    __tablename__ = "advisor_prompt_versions"
    __table_args__ = (Index("ix_advisor_prompt_versions_owner", "user_id", "revision"),)

    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    revision: Mapped[int] = mapped_column(BigInteger, Identity(), unique=True)
    instructions: Mapped[str | None] = mapped_column(Text)


class AdvisorAIUsage(Base):
    __tablename__ = "advisor_ai_usage"
    __table_args__ = (
        Index("ix_advisor_ai_usage_owner", "user_id", "created_at"),
        CheckConstraint("kind IN ('chat', 'test')", name="ck_advisor_ai_usage_kind"),
        CheckConstraint("duration_ms >= 0", name="ck_advisor_ai_usage_duration"),
        CheckConstraint("input_tokens >= 0", name="ck_advisor_ai_usage_input"),
        CheckConstraint("output_tokens >= 0", name="ck_advisor_ai_usage_output"),
    )

    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    model: Mapped[str] = mapped_column(String(128))
    kind: Mapped[str] = mapped_column(String(8))
    status: Mapped[str] = mapped_column(String(32))
    duration_ms: Mapped[int]
    input_tokens: Mapped[int | None] = mapped_column(BigInteger)
    output_tokens: Mapped[int | None] = mapped_column(BigInteger)
