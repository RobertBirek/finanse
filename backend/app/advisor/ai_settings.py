import base64
import binascii
import json
import os
import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from typing import Annotated, Literal, Protocol

from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from pydantic import BaseModel, ConfigDict, SecretStr, StringConstraints, field_validator
from sqlalchemy import case, func, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.advisor.ai_settings_models import AdvisorAIProfile, AdvisorAIUsage, AdvisorPromptVersion
from app.config import settings

ModelName = Annotated[str, StringConstraints(pattern=r"^[A-Za-z0-9][A-Za-z0-9_.:-]{0,127}$")]
UsageDays = Literal[7, 30, 90]
CallKind = Literal["chat", "test", "operation"]
Purpose = Literal["advisor", "document_text", "vision", "receipt", "categorization"]


class CredentialUnavailable(ValueError):
    pass


class ModelUnavailable(ValueError):
    pass


def _cipher(encoded: str) -> AESGCM:
    try:
        raw = base64.b64decode(encoded, altchars=b"-_", validate=True)
        if len(raw) != 32:
            raise ValueError
        return AESGCM(raw)
    except (ValueError, binascii.Error):
        raise CredentialUnavailable("Klucz szyfrowania nie jest skonfigurowany.") from None


def _aad(owner: uuid.UUID, purpose: Purpose) -> bytes:
    prefix = b"personal-advisor:openai:key:v1:"
    return (
        prefix + owner.bytes
        if purpose == "advisor"
        else prefix + owner.bytes + b":" + purpose.encode()
    )


def encrypt_credential(
    encoded: str, owner: uuid.UUID, key: str, *, purpose: Purpose = "advisor"
) -> bytes:
    nonce = os.urandom(12)
    return nonce + _cipher(encoded).encrypt(nonce, key.encode(), _aad(owner, purpose))


def decrypt_credential(
    encoded: str, owner: uuid.UUID, ciphertext: bytes, *, purpose: Purpose = "advisor"
) -> str:
    try:
        return (
            _cipher(encoded)
            .decrypt(ciphertext[:12], ciphertext[12:], _aad(owner, purpose))
            .decode()
        )
    except (InvalidTag, ValueError):
        raise CredentialUnavailable("Nie można odczytać własnego klucza OpenAI.") from None


class CredentialConfig(Protocol):
    @property
    def ADVISOR_CREDENTIAL_ENCRYPTION_KEY(self) -> SecretStr | str: ...
    @property
    def OPENAI_API_KEY(self) -> str: ...
    @property
    def LLM_MODEL(self) -> str: ...

    @property
    def ADVISOR_ALLOWED_SERVER_MODELS(self) -> tuple[str, ...]: ...


class CredentialProfile(Protocol):
    @property
    def model(self) -> str | None: ...
    @property
    def encrypted_key(self) -> bytes | None: ...


@dataclass(frozen=True)
class AdvisorCredentials:
    model: str
    api_key: str = field(repr=False)


def resolve_credentials(
    config: CredentialConfig, owner: uuid.UUID, profile: CredentialProfile | None
) -> AdvisorCredentials:
    configured = config.ADVISOR_CREDENTIAL_ENCRYPTION_KEY
    encoded = configured.get_secret_value() if isinstance(configured, SecretStr) else configured
    key = config.OPENAI_API_KEY
    model = config.LLM_MODEL
    if profile is not None:
        model = profile.model or model
        if profile.encrypted_key is not None:
            key = decrypt_credential(encoded, owner, profile.encrypted_key)
        elif (
            profile.model
            and profile.model != config.LLM_MODEL.strip()
            and (profile.model not in config.ADVISOR_ALLOWED_SERVER_MODELS)
        ):
            raise ModelUnavailable("Własny model wymaga własnego klucza OpenAI.")
    return AdvisorCredentials(model.strip(), key.strip())


def compose_prompt(protected: str, custom: str | None) -> str:
    if not custom:
        return protected
    return (
        protected
        + "\n\nPreferencje użytkownika (stosuj tylko, jeśli są zgodne z instrukcjami powyżej):\n"
        + json.dumps(custom, ensure_ascii=False)
    )


class ModelChange(BaseModel):
    model_config = ConfigDict(extra="forbid")
    model: ModelName | None


class CredentialChange(BaseModel):
    model_config = ConfigDict(extra="forbid")
    api_key: SecretStr

    @field_validator("api_key")
    @classmethod
    def validate_credential(cls, value: SecretStr) -> SecretStr:
        raw = value.get_secret_value().strip()
        if not 1 <= len(raw) <= 512 or any(not 33 <= ord(char) <= 126 for char in raw):
            raise ValueError("Nieprawidłowy format klucza.")
        return SecretStr(raw)


class PromptChange(BaseModel):
    model_config = ConfigDict(extra="forbid")
    instructions: (
        Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=4000)]
        | None
    )

    @field_validator("instructions")
    @classmethod
    def validate_instructions(cls, value: str | None) -> str | None:
        if value is not None and any(ord(char) < 32 and char not in "\n\r\t" for char in value):
            raise ValueError("Niedozwolony znak w instrukcjach.")
        return value


class PromptVersion(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    instructions: str | None
    created_at: datetime


class SettingsView(BaseModel):
    provider: Literal["openai"] = "openai"
    model: str | None
    server_model: str | None
    active_model: str | None
    credential_source: Literal["custom", "server", "missing"]
    custom_key_available: bool
    server_models: list[str]
    instructions: str | None
    operational: bool = True


class UsageSummary(BaseModel):
    kind: CallKind
    model: str
    requests: int
    errors: int
    average_duration_ms: int
    input_tokens: int | None
    output_tokens: int | None
    reports_with_tokens: int


async def get_profile(
    db: AsyncSession, owner: uuid.UUID, *, purpose: Purpose = "advisor"
) -> AdvisorAIProfile | None:
    return await db.scalar(
        select(AdvisorAIProfile)
        .where(AdvisorAIProfile.user_id == owner, AdvisorAIProfile.purpose == purpose)
        .execution_options(populate_existing=True)
    )


async def lock_profile(
    db: AsyncSession, owner: uuid.UUID, *, purpose: Purpose = "advisor"
) -> AdvisorAIProfile:
    await lock_purpose(db, owner, purpose)
    await db.execute(
        insert(AdvisorAIProfile)
        .values(user_id=owner, purpose=purpose)
        .on_conflict_do_nothing(index_elements=["user_id", "purpose"])
    )
    return (
        await db.execute(
            select(AdvisorAIProfile)
            .where(AdvisorAIProfile.user_id == owner, AdvisorAIProfile.purpose == purpose)
            .with_for_update()
            .execution_options(populate_existing=True)
        )
    ).scalar_one()


async def lock_purpose(db: AsyncSession, owner: uuid.UUID, purpose: Purpose) -> None:
    await db.execute(
        select(
            func.pg_advisory_xact_lock(
                func.hashtextextended(f"openai-settings:{owner}:{purpose}", 0)
            )
        )
    )


async def prompt_history(
    db: AsyncSession, owner: uuid.UUID, *, limit: int = 30, purpose: Purpose = "advisor"
) -> list[AdvisorPromptVersion]:
    query = (
        select(AdvisorPromptVersion)
        .where(AdvisorPromptVersion.user_id == owner, AdvisorPromptVersion.purpose == purpose)
        .order_by(AdvisorPromptVersion.revision.desc())
        .limit(limit)
    )
    return list(await db.scalars(query))


async def settings_view(db: AsyncSession, owner: uuid.UUID) -> SettingsView:
    profile = await get_profile(db, owner)
    history = await prompt_history(db, owner, limit=1)
    model = profile.model if profile else None
    server_model = settings.LLM_MODEL.strip() or None
    return SettingsView(
        model=model,
        server_model=server_model,
        active_model=model or server_model,
        credential_source="custom"
        if profile and profile.encrypted_key is not None
        else ("server" if settings.OPENAI_API_KEY.strip() else "missing"),
        custom_key_available=credential_storage_ready(),
        server_models=server_models(),
        instructions=history[0].instructions if history else None,
    )


def credential_storage_ready() -> bool:
    try:
        _cipher(settings.ADVISOR_CREDENTIAL_ENCRYPTION_KEY.get_secret_value())
    except CredentialUnavailable:
        return False
    return True


def server_models() -> list[str]:
    return list(
        dict.fromkeys(
            filter(None, (settings.LLM_MODEL.strip(), *settings.ADVISOR_ALLOWED_SERVER_MODELS))
        )
    )


async def usage_summary(
    db: AsyncSession, owner: uuid.UUID, days: UsageDays, *, purpose: Purpose = "advisor"
) -> list[UsageSummary]:
    event = AdvisorAIUsage
    rows = await db.execute(
        select(
            event.kind,
            event.model,
            func.count(),
            func.sum(case((event.status != "ok", 1), else_=0)),
            func.avg(event.duration_ms),
            func.sum(event.input_tokens),
            func.sum(event.output_tokens),
            func.count(
                case((event.input_tokens.is_not(None) & event.output_tokens.is_not(None), 1))
            ),
        )
        .where(
            event.user_id == owner,
            event.purpose == purpose,
            event.created_at >= datetime.now(UTC) - timedelta(days=days),
        )
        .group_by(event.kind, event.model)
        .order_by(event.kind, func.count().desc(), event.model)
    )
    return [
        UsageSummary(
            kind=kind,
            model=model,
            requests=count,
            errors=errors,
            average_duration_ms=round(ms),
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            reports_with_tokens=known,
        )
        for kind, model, count, errors, ms, input_tokens, output_tokens, known in rows
    ]
