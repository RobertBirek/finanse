from collections.abc import Callable, Coroutine
from typing import Annotated, Any, Literal
from uuid import UUID, uuid4

from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from fastapi.routing import APIRoute
from sqlalchemy.ext.asyncio import AsyncSession

from app.advisor.ai_provider import ProbeResult, probe
from app.advisor.ai_purpose import purpose_baseline, purpose_view, read_purpose
from app.advisor.ai_settings import (
    CredentialChange,
    CredentialUnavailable,
    ModelChange,
    ModelUnavailable,
    PromptChange,
    PromptVersion,
    Purpose,
    SettingsView,
    UsageSummary,
    encrypt_credential,
    get_profile,
    lock_profile,
    prompt_history,
    resolve_credentials,
    server_models,
    settings_view,
    usage_summary,
)
from app.advisor.ai_settings_models import AdvisorPromptVersion
from app.audit.service import log_event
from app.config import settings
from app.database import get_db
from app.identity.models import User
from app.identity.router import get_current_user
from app.security.rate_limit import limit_advisor


class PrivateInputRoute(APIRoute):
    def get_route_handler(self) -> Callable[[Request], Coroutine[Any, Any, Response]]:
        handler = super().get_route_handler()

        async def redact_validation(request: Request) -> Response:
            try:
                response = await handler(request)
            except RequestValidationError:
                response = JSONResponse({"detail": "Nieprawidłowe dane ustawień AI."}, 422)
            response.headers["Cache-Control"] = "no-store"
            return response

        return redact_validation


router = APIRouter(prefix="/settings", route_class=PrivateInputRoute)
Owner = Annotated[User, Depends(get_current_user)]
DB = Annotated[AsyncSession, Depends(get_db)]
ProbeRate = Annotated[None, Depends(limit_advisor(get_current_user))]


async def _view(user_id: UUID, db: AsyncSession, purpose: Purpose) -> SettingsView:
    if purpose == "advisor":
        return await settings_view(db, user_id)
    return await purpose_view(db, user_id, purpose)


def _server_models(purpose: Purpose) -> list[str]:
    if purpose == "advisor":
        return server_models()
    model = purpose_baseline(purpose).credentials.model
    return [model] if model else []


@router.get("")
async def view(user: Owner, db: DB, purpose: Purpose = "advisor") -> SettingsView:
    return await _view(user.id, db, purpose)


@router.put("/model")
async def update_model(
    body: ModelChange, user: Owner, db: DB, purpose: Purpose = "advisor"
) -> SettingsView:
    profile = await lock_profile(db, user.id, purpose=purpose)
    if (
        body.model is not None
        and profile.encrypted_key is None
        and body.model not in _server_models(purpose)
    ):
        raise HTTPException(422, "Wybierz model serwera lub dodaj własny klucz OpenAI.")
    if profile.model != body.model:
        profile.model, profile.configuration_id = body.model, uuid4()
        await log_event(db, user.id, "advisor_ai_settings", str(profile.id), "model_changed")
    return await _view(user.id, db, purpose)


@router.put("/credential")
async def replace_credential(
    body: CredentialChange, user: Owner, db: DB, purpose: Purpose = "advisor"
) -> SettingsView:
    try:
        encrypted = encrypt_credential(
            settings.ADVISOR_CREDENTIAL_ENCRYPTION_KEY.get_secret_value(),
            user.id,
            body.api_key.get_secret_value(),
            purpose=purpose,
        )
    except CredentialUnavailable:
        raise HTTPException(503, "Własny klucz nie jest dostępny w tej instalacji.") from None
    profile = await lock_profile(db, user.id, purpose=purpose)
    profile.encrypted_key, profile.configuration_id = encrypted, uuid4()
    await log_event(db, user.id, "advisor_ai_settings", str(profile.id), "credential_replaced")
    return await _view(user.id, db, purpose)


@router.delete("/credential")
async def remove_credential(user: Owner, db: DB, purpose: Purpose = "advisor") -> SettingsView:
    profile = await lock_profile(db, user.id, purpose=purpose)
    if profile.encrypted_key is not None:
        profile.encrypted_key, profile.configuration_id = None, uuid4()
        if profile.model is not None and profile.model not in _server_models(purpose):
            profile.model = None
        await log_event(db, user.id, "advisor_ai_settings", str(profile.id), "credential_removed")
    return await _view(user.id, db, purpose)


@router.get("/prompts")
async def versions(user: Owner, db: DB, purpose: Purpose = "advisor") -> list[PromptVersion]:
    return [
        PromptVersion.model_validate(row)
        for row in await prompt_history(db, user.id, purpose=purpose)
    ]


@router.post("/prompts", status_code=201)
async def save_prompt(
    body: PromptChange, user: Owner, db: DB, purpose: Purpose = "advisor"
) -> PromptVersion:
    profile = await lock_profile(db, user.id, purpose=purpose)
    profile.configuration_id = uuid4()
    row = AdvisorPromptVersion(user_id=user.id, instructions=body.instructions, purpose=purpose)
    db.add(row)
    await log_event(db, user.id, "advisor_ai_settings", str(profile.id), "prompt_changed")
    return PromptVersion.model_validate(row)


@router.post("/test")
async def test_connection(
    user: Owner, db: DB, _limit: ProbeRate, purpose: Purpose = "advisor"
) -> ProbeResult:
    try:
        if purpose == "advisor":
            profile = await get_profile(db, user.id)
            credentials = resolve_credentials(settings, user.id, profile)
        else:
            credentials = (await read_purpose(db, user.id, purpose)).credentials
    except CredentialUnavailable:
        raise HTTPException(503, "Nie można odczytać własnego klucza OpenAI.") from None
    except ModelUnavailable:
        raise HTTPException(422, "Wybierz model dostępny z kluczem serwera.") from None
    return await probe(user.id, credentials, purpose=purpose)


@router.get("/usage")
async def get_usage(
    user: Owner, db: DB, days: Annotated[int, Query()] = 30, purpose: Purpose = "advisor"
) -> list[UsageSummary]:
    window: Literal[7, 30, 90]
    if days == 7:
        window = 7
    elif days == 30:
        window = 30
    elif days == 90:
        window = 90
    else:
        raise HTTPException(422, "Wybierz okres 7, 30 lub 90 dni.")
    return await usage_summary(db, user.id, window, purpose=purpose)
