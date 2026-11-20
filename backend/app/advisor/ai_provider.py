import logging
import time
import uuid
from typing import Literal, cast

from openai import APIStatusError, APITimeoutError, OpenAIError
from openai.types.responses import Response
from openai.types.responses.response_create_params import ResponseCreateParamsNonStreaming
from pydantic import BaseModel
from sqlalchemy.exc import SQLAlchemyError

from app import database
from app.advisor.ai_settings import AdvisorCredentials, CallKind
from app.advisor.ai_settings_models import AdvisorAIUsage
from app.config import settings
from app.openai_client import create_openai_client

logger = logging.getLogger(__name__)

ProviderStatus = Literal[
    "ok",
    "not_configured",
    "rejected_key",
    "model_unavailable",
    "rate_limited",
    "timeout",
    "unusable_response",
    "provider_error",
]
OPENAI_ENDPOINT = "https://api.openai.com/v1"


def provider_error(error: OpenAIError) -> ProviderStatus:
    if isinstance(error, APITimeoutError):
        return "timeout"
    if isinstance(error, APIStatusError):
        if error.status_code in (401, 403):
            return "rejected_key"
        if error.status_code in (400, 404, 422):
            return "model_unavailable"
        if error.status_code == 429:
            return "rate_limited"
    return "provider_error"


def elapsed_ms(start: float) -> int:
    return round((time.monotonic() - start) * 1000)


async def record_usage(
    owner: uuid.UUID,
    model: str,
    kind: CallKind,
    status: ProviderStatus,
    duration_ms: int,
    response: Response | None,
) -> None:
    usage = response.usage if response is not None else None
    try:
        async with database.async_session_factory() as db, db.begin():
            db.add(
                AdvisorAIUsage(
                    user_id=owner,
                    model=model[:128],
                    kind=kind,
                    status=status,
                    duration_ms=duration_ms,
                    input_tokens=usage.input_tokens if usage else None,
                    output_tokens=usage.output_tokens if usage else None,
                )
            )
    except SQLAlchemyError:
        logger.warning("Could not persist OpenAI usage metadata")


class ProbeResult(BaseModel):
    status: ProviderStatus
    model: str
    duration_ms: int


async def probe(owner: uuid.UUID, credentials: AdvisorCredentials) -> ProbeResult:
    if not credentials.model or not credentials.api_key:
        return ProbeResult(status="not_configured", model=credentials.model, duration_ms=0)
    request = cast(
        ResponseCreateParamsNonStreaming,
        {
            "model": credentials.model,
            "input": "Wywołaj funkcję connection_check. To syntetyczny test połączenia.",
            "tools": [
                {
                    "type": "function",
                    "name": "connection_check",
                    "parameters": {
                        "type": "object",
                        "properties": {},
                        "additionalProperties": False,
                    },
                    "strict": True,
                }
            ],
            "tool_choice": {"type": "function", "name": "connection_check"},
            "reasoning": {"effort": settings.LLM_REASONING_EFFORT},
            "include": ["reasoning.encrypted_content"],
            "store": False,
            "max_output_tokens": settings.ADVISOR_PROBE_MAX_OUTPUT_TOKENS,
        },
    )
    start = time.monotonic()
    response = None
    try:
        async with create_openai_client(
            api_key=credentials.api_key,
            base_url=OPENAI_ENDPOINT,
            timeout=settings.ADVISOR_PROBE_TIMEOUT_SECONDS,
        ) as client:
            response = await client.responses.create(**request)
            status: ProviderStatus = "unusable_response"
            if response.status == "completed" and any(
                item.type == "function_call"
                and item.name == "connection_check"
                and item.arguments.strip() == "{}"
                for item in response.output
            ):
                status = "ok"
    except OpenAIError as error:
        status = provider_error(error)
    except (ValueError, RuntimeError):
        status = "provider_error"
    duration = elapsed_ms(start)
    await record_usage(owner, credentials.model, "test", status, duration, response)
    return ProbeResult(status=status, model=credentials.model, duration_ms=duration)
