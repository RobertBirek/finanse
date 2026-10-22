import shutil
import uuid
from pathlib import Path

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from starlette.exceptions import HTTPException
from starlette.responses import JSONResponse
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from app.config import settings
from app.documents.models import Document


class StorageQuotaExceededError(ValueError):
    pass


class DocumentStorageFullError(OSError):
    pass


class DocumentUploadBodyLimitMiddleware:
    def __init__(self, app: ASGIApp, max_bytes: int | None = None) -> None:
        self.app = app
        self.max_bytes = max_bytes

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http" or scope.get("path", "").rstrip("/") != "/api/documents/upload":
            await self.app(scope, receive, send)
            return
        limit = self.max_bytes or settings.DOCUMENT_MAX_BODY_BYTES
        size = 0
        response = JSONResponse({"detail": "Upload request exceeds size limit"}, status_code=413)
        for name, value in scope.get("headers", []):
            if name.lower() == b"content-length":
                try:
                    if int(value) > limit:
                        await response(scope, receive, send)
                        return
                except ValueError:
                    await response(scope, receive, send)
                    return

        async def bounded_receive() -> Message:
            nonlocal size
            message = await receive()
            if message["type"] == "http.request":
                size += len(message.get("body", b""))
                if size > limit:
                    raise HTTPException(413, "Upload request exceeds size limit")
            return message

        try:
            await self.app(scope, bounded_receive, send)
        except HTTPException as error:
            if error.status_code != 413:
                raise
            await response(scope, receive, send)


async def enforce_storage_admission(
    db: AsyncSession, user_id: uuid.UUID, content_size: int, upload_dir: Path
) -> None:
    """Caller holds global admission advisory lock until transaction completion."""
    user_bytes = await db.scalar(
        select(func.coalesce(func.sum(Document.size_bytes), 0)).where(Document.user_id == user_id)
    )
    total_bytes = await db.scalar(select(func.coalesce(func.sum(Document.size_bytes), 0)))
    if (
        int(user_bytes or 0) + content_size > settings.DOCUMENT_USER_QUOTA_BYTES
        or int(total_bytes or 0) + content_size > settings.DOCUMENT_GLOBAL_QUOTA_BYTES
    ):
        raise StorageQuotaExceededError("Document storage quota exceeded")
    parent = upload_dir
    while not parent.exists() and parent != parent.parent:
        parent = parent.parent
    if shutil.disk_usage(parent).free - content_size < settings.DOCUMENT_MIN_FREE_BYTES:
        raise DocumentStorageFullError("Insufficient document storage space")
