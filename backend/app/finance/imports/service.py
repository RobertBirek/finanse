"""Import orchestration inside finance; preparing a batch never creates a transaction."""

import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from app.finance.imports.contracts import ImportKind
from app.finance.imports.errors import ImportError
from app.finance.imports.models import ImportBatch
from app.finance.imports.queries import get_batch, list_rows  # noqa: F401
from app.finance.imports.schemas import BatchDTO


async def create_batch(db: AsyncSession, owner: uuid.UUID, kind: ImportKind) -> BatchDTO:
    if kind not in {"statement", "loan_schedule"}:
        raise ImportError("unsupported_import_kind", "Nieobsługiwany rodzaj importu.", 422)
    batch = ImportBatch(user_id=owner, kind=kind)
    db.add(batch)
    await db.flush([batch])
    result = await get_batch(db, owner, batch.id)
    if result is None:
        raise RuntimeError("New import batch is missing")
    return result
