import asyncio
import json
import time
from dataclasses import dataclass
from typing import Literal, cast
from uuid import UUID

from openai import OpenAIError
from openai.types.responses.response_create_params import ResponseCreateParamsNonStreaming
from pydantic import BaseModel, ConfigDict

from app.advisor.ai_provider import (
    OPENAI_ENDPOINT,
    ProviderStatus,
    elapsed_ms,
    provider_error,
    record_usage,
)
from app.advisor.ai_settings import AdvisorCredentials, ModelName, PromptChange, compose_prompt
from app.config import settings
from app.openai_client import create_openai_client, response_text

SUITE_VERSION = "advisor-v1"


@dataclass(frozen=True)
class _Case:
    id: str
    question: str
    expected: str


_CASES = (
    _Case("classify_task", "Etykiety: task, payment, note. Sklasyfikuj: Oddzwoń jutro.", "task"),
    _Case(
        "missing_facts",
        "W danych brak salda i zobowiązań. Czy można obliczyć saldo po wydatku? "
        "Odpowiedz jednym kodem: sufficient_data lub insufficient_data.",
        "insufficient_data",
    ),
    _Case(
        "source_reference",
        "Referencje: A1 — zadanie. A2 — płatność po terminie. A3 — notatka. "
        "Podaj identyfikator płatności po terminie.",
        "A2",
    ),
)


class BenchmarkVariant(PromptChange):
    model: ModelName


class BenchmarkInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    variants: tuple[BenchmarkVariant, BenchmarkVariant]


class BenchmarkCaseResult(BaseModel):
    case_id: str
    status: ProviderStatus
    matches_expected: bool | None = None
    duration_ms: int
    input_tokens: int | None = None
    output_tokens: int | None = None


class BenchmarkVariantResult(BaseModel):
    model: str
    status: Literal["ok", "partial", "failed"]
    cases: list[BenchmarkCaseResult]


class BenchmarkResult(BaseModel):
    suite_version: str = SUITE_VERSION
    variants: list[BenchmarkVariantResult]


async def _run_case(
    owner: UUID, credentials: AdvisorCredentials, instructions: str, case: _Case
) -> BenchmarkCaseResult:
    if not credentials.model or not credentials.api_key:
        return BenchmarkCaseResult(case_id=case.id, status="not_configured", duration_ms=0)
    request = cast(
        ResponseCreateParamsNonStreaming,
        {
            "model": credentials.model,
            "instructions": instructions,
            "input": case.question,
            "store": False,
            "max_output_tokens": settings.ADVISOR_PROBE_MAX_OUTPUT_TOKENS,
            "text": {
                "format": {
                    "type": "json_schema",
                    "name": "benchmark_answer",
                    "strict": True,
                    "schema": {
                        "type": "object",
                        "properties": {"answer": {"type": "string"}},
                        "required": ["answer"],
                        "additionalProperties": False,
                    },
                }
            },
        },
    )
    start = time.monotonic()
    status: ProviderStatus = "unusable_response"
    matches = None
    response = None
    timeout = settings.ADVISOR_PROBE_TIMEOUT_SECONDS
    try:
        async with (
            asyncio.timeout(timeout),
            create_openai_client(
                api_key=credentials.api_key,
                base_url=OPENAI_ENDPOINT,
                timeout=timeout,
            ) as client,
        ):
            response = await client.responses.create(**request)
            answer = json.loads(response_text(response, allow_reasoning=True))
            if (
                isinstance(answer, dict)
                and set(answer) == {"answer"}
                and isinstance(answer["answer"], str)
            ):
                status = "ok"
                matches = answer["answer"] == case.expected
    except TimeoutError:
        status = "timeout"
    except OpenAIError as error:
        status = provider_error(error)
    except (ValueError, RuntimeError):
        pass
    duration = elapsed_ms(start)
    usage = response.usage if response else None
    await record_usage(owner, credentials.model, "test", status, duration, response)
    return BenchmarkCaseResult(
        case_id=case.id,
        status=status,
        matches_expected=matches,
        duration_ms=duration,
        input_tokens=usage.input_tokens if usage else None,
        output_tokens=usage.output_tokens if usage else None,
    )


async def compare_configs(
    owner_id: UUID,
    variants: tuple[BenchmarkVariant, BenchmarkVariant],
    *,
    credentials: tuple[AdvisorCredentials, AdvisorCredentials],
) -> BenchmarkResult:
    results = []
    for variant, credential in zip(variants, credentials, strict=True):
        instructions = compose_prompt(
            "To test syntetyczny. Odpowiedz jednym kodem zgodnie z danymi zadania.",
            variant.instructions,
        )
        cases = await asyncio.gather(
            *(_run_case(owner_id, credential, instructions, case) for case in _CASES)
        )
        successes = sum(case.status == "ok" for case in cases)
        results.append(
            BenchmarkVariantResult(
                model=credential.model,
                status="ok" if successes == len(cases) else "partial" if successes else "failed",
                cases=cases,
            )
        )
    return BenchmarkResult(variants=results)
