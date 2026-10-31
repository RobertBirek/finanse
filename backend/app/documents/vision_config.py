import hashlib
import json
from dataclasses import dataclass, field
from urllib.parse import urlsplit

from app.config import Settings


@dataclass(frozen=True)
class VisionConfig:
    provider: str
    base_url: str
    model: str
    api_key: str = field(repr=False)
    prompt_version: str = ""
    schema_version: str = ""

    @property
    def configuration_fingerprint(self) -> str:
        parsed = urlsplit(self.base_url)
        endpoint = f"https://{parsed.hostname or ''}"
        if parsed.port is not None:
            endpoint = f"{endpoint}:{parsed.port}"
        endpoint = f"{endpoint}{parsed.path.rstrip('/') or '/'}"
        identity = {
            "endpoint": endpoint,
            "model": self.model.strip(),
            "prompt_version": self.prompt_version.strip(),
            "provider": self.provider.strip().lower(),
            "schema_version": self.schema_version.strip(),
        }
        return hashlib.sha256(
            json.dumps(identity, sort_keys=True, separators=(",", ":")).encode()
        ).hexdigest()

    @property
    def is_activation_ready(self) -> bool:
        return bool(self.prompt_version.strip() and self.schema_version.strip())


def get_vision_config(settings: Settings) -> VisionConfig | None:
    values = (
        settings.DOCUMENT_VISION_PROVIDER,
        settings.DOCUMENT_VISION_BASE_URL,
        settings.DOCUMENT_VISION_MODEL,
        settings.DOCUMENT_VISION_API_KEY,
    )
    if not all(values):
        return None
    return VisionConfig(
        provider=settings.DOCUMENT_VISION_PROVIDER,
        base_url=settings.DOCUMENT_VISION_BASE_URL,
        model=settings.DOCUMENT_VISION_MODEL,
        api_key=settings.DOCUMENT_VISION_API_KEY,
        prompt_version=settings.DOCUMENT_VISION_PROMPT_VERSION,
        schema_version=settings.DOCUMENT_VISION_SCHEMA_VERSION,
    )
