"""One no-retry, no-tools Structured Outputs call. Usage survives invalid text."""

import asyncio
import hashlib
from dataclasses import dataclass

from openai import APIError
from pydantic import ValidationError

from app.finance.suggestion_config import SuggestionConfig
from app.finance.suggestion_packet import SuggestionPacket
from app.finance.suggestion_schemas import SuggestionPayload
from app.openai_client import ResponseOutputError, create_openai_client, response_text


@dataclass(frozen=True)
class ProviderUsage:
    input_tokens: int | None = None
    output_tokens: int | None = None
    response_id_hash: str | None = None


@dataclass(frozen=True)
class ProviderOutcome:
    payload: SuggestionPayload | None
    usage: ProviderUsage
    error_code: str | None = None
    uncertain: bool = False


async def call_suggestion_provider(
    packet: SuggestionPacket, config: SuggestionConfig
) -> ProviderOutcome:
    usage = ProviderUsage()
    try:
        async with asyncio.timeout(config.timeout_seconds):
            async with create_openai_client(
                api_key=config.api_key, base_url=config.base_url, timeout=config.timeout_seconds
            ) as client:
                response = await client.responses.create(**packet.public_request)
        raw = response.usage
        usage = ProviderUsage(
            raw.input_tokens if raw else None,
            raw.output_tokens if raw else None,
            hashlib.sha256(response.id.encode()).hexdigest(),
        )
        payload = SuggestionPayload.model_validate_json(response_text(response))
        if payload.category_key is not None and payload.category_key not in packet.private_key_map:
            raise ValueError("Unknown category key")
        if (
            not payload.explanation.strip()
            or len(payload.explanation) > config.max_explanation_chars
        ):
            raise ValueError("Explanation limit")
        if payload.new_category:
            n = payload.new_category
            if (
                (n.parent_key is not None and n.parent_key not in packet.private_key_map)
                or not n.name.strip()
                or len(n.name) > config.max_new_category_chars
                or not n.explanation.strip()
                or len(n.explanation) > config.max_explanation_chars
            ):
                raise ValueError("Invalid new category text")
        return ProviderOutcome(payload, usage)
    except (ResponseOutputError, ValidationError, ValueError):
        return ProviderOutcome(None, usage, "invalid_output")
    except (APIError, TimeoutError, OSError):
        return ProviderOutcome(None, usage, "provider_uncertain", uncertain=True)
