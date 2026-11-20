import hashlib
import uuid
from dataclasses import dataclass

from sqlalchemy.ext.asyncio import AsyncSession

from app.advisor.ai_settings import (
    AdvisorCredentials,
    ModelUnavailable,
    Purpose,
    SettingsView,
    credential_storage_ready,
    decrypt_credential,
    get_profile,
    lock_purpose,
    prompt_history,
)
from app.config import settings
from app.openai_client import _is_openai_base_url


@dataclass(frozen=True)
class PurposeBaseline:
    credentials: AdvisorCredentials
    operational: bool


@dataclass(frozen=True)
class PurposeRuntime:
    credentials: AdvisorCredentials
    instructions: str | None
    version: uuid.UUID | None

    def fingerprint(self, baseline: str) -> str:
        if self.version is None:
            return baseline
        return hashlib.sha256(f"personal-openai-v1:{baseline}:{self.version}".encode()).hexdigest()


def purpose_baseline(purpose: Purpose) -> PurposeBaseline:
    if purpose == "advisor":
        return PurposeBaseline(
            AdvisorCredentials(settings.LLM_MODEL.strip(), settings.OPENAI_API_KEY.strip()), True
        )
    if purpose == "document_text":
        return PurposeBaseline(
            AdvisorCredentials(
                settings.DOCUMENT_TEXT_MODEL.strip(), settings.OPENAI_API_KEY.strip()
            ),
            _is_openai_base_url(settings.LLM_BASE_URL),
        )
    if purpose == "vision":
        from app.documents.vision_config import get_vision_config

        vision = get_vision_config(settings)
        if (
            vision
            and settings.DOCUMENT_VISION_ENABLED
            and vision.is_activation_ready
            and vision.provider.strip().lower() == "openai"
            and _is_openai_base_url(vision.base_url)
        ):
            return PurposeBaseline(AdvisorCredentials(vision.model, vision.api_key), True)
    if purpose == "receipt":
        from app.documents.receipt_read_config import get_receipt_read_config

        receipt = get_receipt_read_config(settings)
        if receipt and settings.DOCUMENT_RECEIPT_ITEMS_ENABLED:
            return PurposeBaseline(AdvisorCredentials(receipt.model, receipt.api_key), True)
    if purpose == "categorization":
        from app.finance.suggestion_config import get_suggestion_config

        suggestion = get_suggestion_config(settings)
        if suggestion:
            return PurposeBaseline(AdvisorCredentials(suggestion.model, suggestion.api_key), True)
    return PurposeBaseline(AdvisorCredentials("", ""), False)


def resolve_purpose(
    purpose: Purpose,
    owner: uuid.UUID,
    baseline: PurposeBaseline,
    *,
    model: str | None,
    encrypted_key: bytes | None,
    instructions: str | None,
    version: uuid.UUID | None,
) -> PurposeRuntime:
    if not baseline.operational:
        raise ModelUnavailable("Ta funkcja AI nie jest skonfigurowana na serwerze.")
    defaults = baseline.credentials
    if encrypted_key is not None:
        key = decrypt_credential(
            settings.ADVISOR_CREDENTIAL_ENCRYPTION_KEY.get_secret_value(),
            owner,
            encrypted_key,
            purpose=purpose,
        )
    else:
        if model and model != defaults.model.strip():
            raise ModelUnavailable("Własny model wymaga własnego klucza OpenAI.")
        key = defaults.api_key
    return PurposeRuntime(
        AdvisorCredentials((model or defaults.model).strip(), key.strip()), instructions, version
    )


async def read_purpose(
    db: AsyncSession,
    owner: uuid.UUID,
    purpose: Purpose,
    *,
    baseline: PurposeBaseline | None = None,
    linearize: bool = False,
) -> PurposeRuntime:
    defaults = baseline if baseline is not None else purpose_baseline(purpose)
    if linearize:
        await lock_purpose(db, owner, purpose)
    # Observe one committed version. A concurrent edit between statements must not pair
    # a previous credential with a new prompt. uuid4 is never reused on a settings write.
    for _ in range(2):
        profile = await get_profile(db, owner, purpose=purpose)
        if profile is None:
            return resolve_purpose(
                purpose,
                owner,
                defaults,
                model=None,
                encrypted_key=None,
                instructions=None,
                version=None,
            )
        version, model, key = profile.configuration_id, profile.model, profile.encrypted_key
        history = await prompt_history(db, owner, limit=1, purpose=purpose)
        current = await get_profile(db, owner, purpose=purpose)
        if current is not None and current.configuration_id == version:
            return resolve_purpose(
                purpose,
                owner,
                defaults,
                model=model,
                encrypted_key=key,
                instructions=history[0].instructions if history else None,
                version=version,
            )
    raise ModelUnavailable("Konfiguracja zmieniła się; spróbuj ponownie.")


async def purpose_view(db: AsyncSession, owner: uuid.UUID, purpose: Purpose) -> SettingsView:
    baseline = purpose_baseline(purpose)
    profile = await get_profile(db, owner, purpose=purpose)
    versions = await prompt_history(db, owner, limit=1, purpose=purpose)
    server_model = baseline.credentials.model or None
    model = profile.model if profile else None
    return SettingsView(
        model=model,
        server_model=server_model,
        active_model=model or server_model,
        credential_source="custom"
        if profile and profile.encrypted_key is not None
        else ("server" if baseline.credentials.api_key else "missing"),
        custom_key_available=credential_storage_ready(),
        server_models=[server_model] if server_model else [],
        instructions=versions[0].instructions if versions else None,
        operational=baseline.operational,
    )
