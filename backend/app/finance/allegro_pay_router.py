"""Owner-scoped Allegro Pay commands."""

import uuid
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.finance import allegro_pay
from app.finance.allegro_pay_models import AllegroPayProfile
from app.finance.allegro_pay_schemas import PaymentInput, ProfileInput, PurchaseInput
from app.identity.models import User
from app.identity.router import get_current_user

router = APIRouter(prefix="/allegro-pay")
Owner = Annotated[User, Depends(get_current_user)]
Database = Annotated[AsyncSession, Depends(get_db)]


@router.get("")
async def list_profiles(user: Owner, db: Database) -> list[dict[str, Any]]:
    ids = (
        await db.scalars(select(AllegroPayProfile.id).where(AllegroPayProfile.user_id == user.id))
    ).all()
    return [await allegro_pay.overview(db, user.id, profile_id) for profile_id in ids]


@router.put("")
async def put_profile(data: ProfileInput, user: Owner, db: Database) -> dict[str, Any]:
    try:
        profile = await allegro_pay.save_profile(db, user.id, data)
        return await allegro_pay.overview(db, user.id, profile.id)
    except (ValueError, LookupError) as error:
        raise HTTPException(404 if isinstance(error, LookupError) else 422, str(error)) from error


@router.post("/{profile_id}/purchases")
async def purchase(
    profile_id: uuid.UUID, data: PurchaseInput, user: Owner, db: Database
) -> dict[str, Any]:
    try:
        result = await allegro_pay.add_purchase(db, user.id, profile_id, data)
        return {"id": result.id}
    except (ValueError, LookupError) as error:
        raise HTTPException(404 if isinstance(error, LookupError) else 422, str(error)) from error


@router.post("/{profile_id}/payments")
async def payment(
    profile_id: uuid.UUID, data: PaymentInput, user: Owner, db: Database
) -> dict[str, bool]:
    try:
        await allegro_pay.allocate_payment(db, user.id, profile_id, data)
        return {"ok": True}
    except (ValueError, LookupError) as error:
        raise HTTPException(404 if isinstance(error, LookupError) else 422, str(error)) from error


@router.delete("/{profile_id}/payments/{transaction_id}")
async def unlink_payment(
    profile_id: uuid.UUID, transaction_id: uuid.UUID, user: Owner, db: Database
) -> dict[str, bool]:
    try:
        await allegro_pay.unlink_payment(db, user.id, profile_id, transaction_id)
        return {"ok": True}
    except (ValueError, LookupError) as error:
        raise HTTPException(404 if isinstance(error, LookupError) else 422, str(error)) from error
