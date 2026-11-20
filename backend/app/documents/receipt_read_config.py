"""Separate export destination and captured bounds; never inherits header consent."""

import hashlib
import json
import uuid
from dataclasses import asdict, dataclass, field, replace

from sqlalchemy.ext.asyncio import AsyncSession

from app.advisor.ai_purpose import PurposeBaseline, read_purpose
from app.advisor.ai_settings import AdvisorCredentials, CredentialUnavailable, ModelUnavailable
from app.config import Settings
from app.openai_client import _is_openai_base_url

NORMALIZER_VERSION = "receipt-image-v1"
CONSENT_VERSION = "receipt-items-consent-v1"


@dataclass(frozen=True)
class ReceiptReadConfig:
    provider: str
    base_url: str
    model: str
    api_key: str = field(repr=False)
    prompt_version: str
    schema_version: str
    normalizer_version: str
    consent_version: str
    max_edge: int
    max_bytes: int
    max_pixels: int
    max_output_tokens: int
    max_response_bytes: int
    reasoning_effort: str
    timeout_seconds: float
    max_lines: int
    max_discounts: int
    max_discount_shares: int
    item_name_max_chars: int
    policy_fingerprint: str | None = None
    personal_fingerprint: str | None = None
    custom_instructions: str | None = field(default=None, repr=False)
    personal_unavailable: bool = False

    @property
    def configuration_fingerprint(self) -> str:
        if self.personal_fingerprint is not None:
            return self.personal_fingerprint
        values = asdict(self)
        for key in (
            "api_key",
            "policy_fingerprint",
            "personal_fingerprint",
            "custom_instructions",
            "personal_unavailable",
        ):
            values.pop(key)
        return hashlib.sha256(
            json.dumps(values, sort_keys=True, separators=(",", ":")).encode()
        ).hexdigest()


async def owner_receipt_config(
    db: AsyncSession, owner: uuid.UUID, config: ReceiptReadConfig, *, linearize: bool = False
) -> ReceiptReadConfig:
    baseline = config.configuration_fingerprint
    try:
        runtime = await read_purpose(
            db,
            owner,
            "receipt",
            linearize=linearize,
            baseline=PurposeBaseline(AdvisorCredentials(config.model, config.api_key), True),
        )
    except (CredentialUnavailable, ModelUnavailable):
        return replace(config, policy_fingerprint=baseline, personal_unavailable=True)
    return replace(
        config,
        model=runtime.credentials.model,
        api_key=runtime.credentials.api_key,
        policy_fingerprint=baseline,
        personal_fingerprint=runtime.fingerprint(baseline),
        custom_instructions=runtime.instructions,
    )


def get_receipt_read_config(settings: Settings) -> ReceiptReadConfig | None:
    provider = settings.DOCUMENT_RECEIPT_ITEMS_PROVIDER.strip().lower()
    url = settings.DOCUMENT_RECEIPT_ITEMS_BASE_URL.strip().rstrip("/")
    model = settings.DOCUMENT_RECEIPT_ITEMS_MODEL.strip()
    prompt = settings.DOCUMENT_RECEIPT_ITEMS_PROMPT_VERSION.strip()
    schema = settings.DOCUMENT_RECEIPT_ITEMS_SCHEMA_VERSION.strip()
    key = settings.DOCUMENT_RECEIPT_ITEMS_API_KEY.strip()
    if (
        provider != "openai"
        or not _is_openai_base_url(url)
        or not all((model, prompt, schema, key))
    ):
        return None
    return ReceiptReadConfig(
        provider=provider,
        base_url=url,
        model=model,
        api_key=key,
        prompt_version=prompt,
        schema_version=schema,
        normalizer_version=NORMALIZER_VERSION,
        consent_version=CONSENT_VERSION,
        max_edge=settings.DOCUMENT_RECEIPT_ITEMS_MAX_EDGE,
        max_bytes=settings.DOCUMENT_RECEIPT_ITEMS_MAX_BYTES,
        max_pixels=settings.DOCUMENT_RECEIPT_ITEMS_MAX_PIXELS,
        max_output_tokens=settings.DOCUMENT_RECEIPT_ITEMS_MAX_OUTPUT_TOKENS,
        max_response_bytes=settings.DOCUMENT_RECEIPT_ITEMS_MAX_RESPONSE_BYTES,
        reasoning_effort=settings.DOCUMENT_RECEIPT_ITEMS_REASONING_EFFORT,
        timeout_seconds=settings.DOCUMENT_RECEIPT_ITEMS_TIMEOUT_SECONDS,
        max_lines=settings.FINANCE_RECEIPT_MAX_LINES,
        max_discounts=settings.FINANCE_RECEIPT_MAX_DISCOUNTS,
        max_discount_shares=settings.FINANCE_RECEIPT_MAX_DISCOUNT_SHARES,
        item_name_max_chars=settings.FINANCE_RECEIPT_ITEM_NAME_MAX_CHARS,
    )
