from app.config import settings
from app.documents.router import upload_capabilities


async def test_capabilities_require_effective_flag_and_never_expose_secrets(monkeypatch):
    monkeypatch.setattr(settings, "DOCUMENT_VISION_ENABLED", True)
    monkeypatch.setattr(settings, "DOCUMENT_VISION_PROVIDER", "safe-label")
    monkeypatch.setattr(settings, "DOCUMENT_VISION_API_KEY", "private-key")

    class DB:
        async def get(self, *_args):
            return None

    capabilities = await upload_capabilities(None, DB())  # type: ignore[arg-type]
    payload = capabilities.model_dump()
    assert payload["automatic_image_vision"] is False
    assert payload["vision_provider_label"] is None
    assert "private-key" not in str(payload)
