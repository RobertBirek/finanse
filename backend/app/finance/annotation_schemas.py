"""Strict, dynamically bounded input for human-authored transaction labels."""

import unicodedata
import uuid

from pydantic import BaseModel, ConfigDict, Field, ValidationInfo, field_validator

from app.config import settings


def normalize_tag(value: str) -> tuple[str, str]:
    name = " ".join(unicodedata.normalize("NFC", value).split())
    return name, name.casefold()


class AnnotationLimits(BaseModel):
    display_description: int
    note: int
    tag_name: int
    tags: int


def annotation_limits() -> AnnotationLimits:
    return AnnotationLimits(
        display_description=settings.FINANCE_ANNOTATION_TITLE_MAX_CHARS,
        note=settings.FINANCE_ANNOTATION_NOTE_MAX_CHARS,
        tag_name=settings.FINANCE_TAG_NAME_MAX_CHARS,
        tags=settings.FINANCE_ANNOTATION_MAX_TAGS,
    )


class AnnotationTag(BaseModel):
    id: uuid.UUID
    name: str
    model_config = ConfigDict(from_attributes=True)


class AnnotationResponse(BaseModel):
    display_description: str | None
    original_description: str
    note: str | None
    tags: list[AnnotationTag]
    project_id: uuid.UUID | None
    project_name: str | None = None
    version: int
    context_snapshot: str
    limits: AnnotationLimits


class AnnotationUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    display_description: str | None
    note: str | None
    tags: list[str]
    project_id: uuid.UUID | None
    expected_version: int = Field(ge=0, strict=True)
    expected_context_snapshot: str = Field(pattern=r"^[a-f0-9]{64}$")

    @field_validator("display_description", "note")
    @classmethod
    def bounded_text(cls, value: str | None, info: ValidationInfo) -> str | None:
        if value is None:
            return None
        value = value.strip()
        if "\0" in value:
            raise ValueError("Tekst zawiera niedozwolony znak.")
        limit = (
            settings.FINANCE_ANNOTATION_TITLE_MAX_CHARS
            if info.field_name == "display_description"
            else settings.FINANCE_ANNOTATION_NOTE_MAX_CHARS
        )
        if len(value) > limit:
            raise ValueError("Przekroczono limit długości tekstu.")
        return value or None

    @field_validator("tags")
    @classmethod
    def bounded_tags(cls, values: list[str]) -> list[str]:
        if len(values) > settings.FINANCE_ANNOTATION_MAX_TAGS:
            raise ValueError("Zbyt wiele tagów.")
        result: dict[str, str] = {}
        for value in values:
            name, key = normalize_tag(value)
            if not name or "\0" in name or len(name) > settings.FINANCE_TAG_NAME_MAX_CHARS:
                raise ValueError("Tag jest pusty lub zbyt długi.")
            result.setdefault(key, name)
        return list(result.values())
