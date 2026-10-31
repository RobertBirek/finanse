from dataclasses import dataclass, field

from app.config import Settings


@dataclass(frozen=True)
class VisionConfig:
    provider: str
    base_url: str
    model: str
    api_key: str = field(repr=False)


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
    )
