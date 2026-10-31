import pytest

from app.config import settings
from app.documents.router import upload_capabilities


@pytest.mark.asyncio
async def test_upload_capabilities_expose_configured_limit_not_a_client_constant() -> None:
    class DB:
        async def get(self, *_args):
            return None

    capabilities = await upload_capabilities(None, DB())  # type: ignore[arg-type]

    assert capabilities.max_file_bytes == settings.DOCUMENT_MAX_FILE_BYTES
    assert {"application/pdf", "image/jpeg", "image/png", "image/heic", "image/heif"} <= set(
        capabilities.accepted_mime_types
    )
