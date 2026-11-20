from collections.abc import Callable, Coroutine
from typing import Annotated, Any, Literal

from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from fastapi.routing import APIRoute
from sqlalchemy.ext.asyncio import AsyncSession

from app.advisor.ai_provider import ProbeResult, probe
from app.advisor.ai_settings import (
    CredentialChange,
    CredentialUnavailable,
    ModelChange,
    ModelUnavailable,
    PromptChange,
    PromptVersion,
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


@router.get("")
async def view(user: Owner, db: DB) -> SettingsView:
    return await settings_view(db, user.id)


@router.put("/model")
async def update_model(body: ModelChange, user: Owner, db: DB) -> SettingsView:
    profile = await lock_profile(db, user.id)
    if (
        body.model is not None
        and profile.encrypted_key is None
        and body.model not in server_models()
    ):
        raise HTTPException(422, "Wybierz model serwera lub dodaj własny klucz OpenAI.")
    profile.model = body.model
    await log_event(db, user.id, "advisor_ai_settings", str(user.id), "model_changed")
    return await settings_view(db, user.id)


@router.put("/credential")
async def replace_credential(body: CredentialChange, user: Owner, db: DB) -> SettingsView:
    try:
        encrypted = encrypt_credential(
            settings.ADVISOR_CREDENTIAL_ENCRYPTION_KEY.get_secret_value(),
            user.id,
            body.api_key.get_secret_value(),
        )
    except CredentialUnavailable:
        raise HTTPException(503, "Własny klucz nie jest dostępny w tej instalacji.") from None
    profile = await lock_profile(db, user.id)
    profile.encrypted_key = encrypted
    await log_event(db, user.id, "advisor_ai_settings", str(user.id), "credential_replaced")
    return await settings_view(db, user.id)


@router.delete("/credential")
async def remove_credential(user: Owner, db: DB) -> SettingsView:
    profile = await lock_profile(db, user.id)
    profile.encrypted_key = None
    if profile.model is not None and profile.model not in server_models():
        profile.model = None
    await log_event(db, user.id, "advisor_ai_settings", str(user.id), "credential_removed")
    return await settings_view(db, user.id)


@router.get("/prompts")
async def versions(user: Owner, db: DB) -> list[PromptVersion]:
    return [PromptVersion.model_validate(row) for row in await prompt_history(db, user.id)]


@router.post("/prompts", status_code=201)
async def save_prompt(body: PromptChange, user: Owner, db: DB) -> PromptVersion:
    await lock_profile(db, user.id)
    row = AdvisorPromptVersion(user_id=user.id, instructions=body.instructions)
    db.add(row)
    await log_event(db, user.id, "advisor_ai_settings", str(user.id), "prompt_changed")
    return PromptVersion.model_validate(row)


@router.post("/test")
async def test_connection(user: Owner, db: DB, _limit: ProbeRate) -> ProbeResult:
    profile = await get_profile(db, user.id)
    try:
        credentials = resolve_credentials(settings, user.id, profile)
    except CredentialUnavailable:
        raise HTTPException(503, "Nie można odczytać własnego klucza OpenAI.") from None
    except ModelUnavailable:
        raise HTTPException(422, "Wybierz model dostępny z kluczem serwera.") from None
    return await probe(user.id, credentials)


@router.get("/usage")
async def get_usage(user: Owner, db: DB, days: Annotated[int, Query()] = 30) -> list[UsageSummary]:
    window: Literal[7, 30, 90]
    if days == 7:
        window = 7
    elif days == 30:
        window = 30
    elif days == 90:
        window = 90
    else:
        raise HTTPException(422, "Wybierz okres 7, 30 lub 90 dni.")
    return await usage_summary(db, user.id, window)
