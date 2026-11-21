import asyncio
import json
import time
from typing import cast
from uuid import UUID

from openai import OpenAIError
from openai.types.responses.response_create_params import ResponseCreateParamsNonStreaming
from sqlalchemy.ext.asyncio import AsyncSession

from app.advisor.ai_provider import (
    OPENAI_ENDPOINT,
    ProviderStatus,
    elapsed_ms,
    provider_error,
    record_usage,
)
from app.advisor.ai_settings import (
    CredentialUnavailable,
    ModelUnavailable,
    compose_prompt,
    get_profile,
    prompt_history,
    resolve_credentials,
)
from app.advisor.decision_schemas import DecisionExplanation
from app.config import settings
from app.openai_client import create_openai_client, response_text


async def explain_facts(
    db: AsyncSession, user_id: UUID, facts: dict[str, object]
) -> DecisionExplanation:
    try:
        credentials = resolve_credentials(settings, user_id, await get_profile(db, user_id))
    except (CredentialUnavailable, ModelUnavailable):
        return DecisionExplanation(status="unavailable")
    if not credentials.model or not credentials.api_key:
        return DecisionExplanation(status="unavailable")
    versions = await prompt_history(db, user_id, limit=1)
    instructions = compose_prompt(
        "Krótko objaśnij przekazane fakty po polsku. Nie zmieniaj ich, "
        "nie wymyślaj kwot, dat, linków ani innych pozycji. Nie wydawaj "
        "poleceń wykonania operacji i nie gwarantuj płynności.",
        versions[0].instructions if versions else None,
    )
    request = cast(
        ResponseCreateParamsNonStreaming,
        {
            "model": credentials.model,
            "input": [
                {
                    "role": "developer",
                    "content": instructions,
                },
                {"role": "user", "content": json.dumps(facts, ensure_ascii=False)},
            ],
            "text": {
                "format": {
                    "type": "json_schema",
                    "name": "decision_explanation",
                    "strict": True,
                    "schema": {
                        "type": "object",
                        "properties": {"text": {"type": "string"}},
                        "required": ["text"],
                        "additionalProperties": False,
                    },
                }
            },
            "store": False,
            "max_output_tokens": settings.ADVISOR_PROBE_MAX_OUTPUT_TOKENS,
        },
    )
    started = time.monotonic()
    response = None
    status: ProviderStatus = "unusable_response"
    explanation = DecisionExplanation(status="unavailable")
    try:
        async with (
            asyncio.timeout(settings.ADVISOR_PROBE_TIMEOUT_SECONDS),
            create_openai_client(
                api_key=credentials.api_key,
                base_url=OPENAI_ENDPOINT,
                timeout=settings.ADVISOR_PROBE_TIMEOUT_SECONDS,
            ) as client,
        ):
            response = await client.responses.create(**request)
            content = json.loads(response_text(response, allow_reasoning=True))
            if isinstance(content, dict) and isinstance(content.get("text"), str):
                text = content["text"].strip()
                if 0 < len(text) <= 1200:
                    status = "ok"
                    explanation = DecisionExplanation(status="ok", text=text)
    except TimeoutError:
        status = "timeout"
    except OpenAIError as error:
        status = provider_error(error)
    except (ValueError, RuntimeError):
        pass
    await record_usage(
        user_id, credentials.model, "operation", status, elapsed_ms(started), response
    )
    return explanation
