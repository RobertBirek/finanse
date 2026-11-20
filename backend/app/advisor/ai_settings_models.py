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
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class AdvisorAIProfile(Base):
    __tablename__ = "advisor_ai_profiles"
    __table_args__ = (UniqueConstraint("user_id", "purpose", name="uq_advisor_ai_profile_purpose"),)

    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    purpose: Mapped[str] = mapped_column(String(20), server_default="advisor")
    configuration_id: Mapped[uuid.UUID | None]
    model: Mapped[str | None] = mapped_column(String(128))
    encrypted_key: Mapped[bytes | None] = mapped_column(LargeBinary)


class AdvisorPromptVersion(Base):
    __tablename__ = "advisor_prompt_versions"
    __table_args__ = (Index("ix_advisor_prompt_versions_owner", "user_id", "purpose", "revision"),)

    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    purpose: Mapped[str] = mapped_column(String(20), server_default="advisor")
    revision: Mapped[int] = mapped_column(BigInteger, Identity(), unique=True)
    instructions: Mapped[str | None] = mapped_column(Text)


class AdvisorAIUsage(Base):
    __tablename__ = "advisor_ai_usage"
    __table_args__ = (
        Index("ix_advisor_ai_usage_owner", "user_id", "purpose", "created_at"),
        CheckConstraint("kind IN ('chat', 'test', 'operation')", name="ck_advisor_ai_usage_kind"),
        CheckConstraint("duration_ms >= 0", name="ck_advisor_ai_usage_duration"),
        CheckConstraint("input_tokens >= 0", name="ck_advisor_ai_usage_input"),
        CheckConstraint("output_tokens >= 0", name="ck_advisor_ai_usage_output"),
    )

    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    purpose: Mapped[str] = mapped_column(String(20), server_default="advisor")
    model: Mapped[str] = mapped_column(String(128))
    kind: Mapped[str] = mapped_column(String(9))
    status: Mapped[str] = mapped_column(String(32))
    duration_ms: Mapped[int]
    input_tokens: Mapped[int | None] = mapped_column(BigInteger)
    output_tokens: Mapped[int | None] = mapped_column(BigInteger)
