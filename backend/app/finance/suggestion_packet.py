"""Pure bounded data packet; key-to-UUID authority never leaves the backend."""

import json
import uuid
from dataclasses import dataclass
from typing import Any

from app.finance.categorization_context import CategorizationError, LedgerContext, columns, digest
from app.finance.models import Category
from app.finance.suggestion_config import PROMPT_TEXT, SuggestionConfig
from app.finance.suggestion_schemas import SuggestionPayload


@dataclass(frozen=True)
class SuggestionPacket:
    public_request: dict[str, Any]
    private_key_map: dict[str, uuid.UUID]
    source_sha256: str
    taxonomy_sha256: str
    request_sha256: str


def suggestion_taxonomy(
    categories: dict[uuid.UUID, Category], owner: uuid.UUID, marker_id: uuid.UUID
) -> tuple[list[dict[str, str]], dict[str, uuid.UUID], str]:
    targets = sorted(
        (
            c
            for c in categories.values()
            if c.id != marker_id and c.is_active and c.type == "expense"
        ),
        key=lambda c: str(c.id),
    )
    paths, mapping, evidence = [], {}, {}
    for i, target in enumerate(targets, 1):
        names, seen = [], set()
        cat: Category | None = target
        while cat is not None:
            if cat.id in seen or cat.user_id != owner or not cat.is_active or cat.type != "expense":
                raise CategorizationError(
                    "invalid_taxonomy", "Katalog kategorii wymaga ręcznego sprawdzenia."
                )
            seen.add(cat.id)
            names.append(cat.name)
            evidence[str(cat.id)] = columns(cat)
            if cat.parent_id and cat.parent_id not in categories:
                raise CategorizationError("invalid_taxonomy", "Brakuje rodzica kategorii.")
            cat = categories.get(cat.parent_id) if cat.parent_id else None
        key = f"c{i:02d}"
        paths.append({"key": key, "path": " / ".join(reversed(names))})
        mapping[key] = target.id
    if not paths:
        raise CategorizationError(
            "empty_taxonomy", "Brak kategorii docelowych. Wybierz kategorię ręcznie."
        )
    return paths, mapping, digest({"marker_id": marker_id, "categories": evidence, "paths": paths})


def build_suggestion_packet(
    ctx: LedgerContext, config: SuggestionConfig, *, marker_id: uuid.UUID
) -> SuggestionPacket:
    description = ctx.txn.description
    if not description.strip() or len(description) > config.max_description_chars:
        raise CategorizationError(
            "description_limit", "Opis przekracza limit AI; wybierz kategorię ręcznie."
        )
    paths, mapping, taxonomy = suggestion_taxonomy(ctx.categories, ctx.txn.user_id, marker_id)
    if len(paths) > config.max_categories:
        raise CategorizationError(
            "taxonomy_limit", "Katalog przekracza limit AI; wybierz kategorię ręcznie."
        )
    schema = SuggestionPayload.model_json_schema()
    keys = list(mapping)
    schema["properties"]["category_key"]["anyOf"][0]["enum"] = keys
    schema["$defs"]["SuggestedNewCategory"]["properties"]["parent_key"]["anyOf"][0]["enum"] = keys
    schema["properties"]["explanation"]["maxLength"] = config.max_explanation_chars
    schema["$defs"]["SuggestedNewCategory"]["properties"]["name"]["maxLength"] = (
        config.max_new_category_chars
    )
    schema["$defs"]["SuggestedNewCategory"]["properties"]["explanation"]["maxLength"] = (
        config.max_explanation_chars
    )
    request = {
        "model": config.model,
        "instructions": PROMPT_TEXT,
        "input": [
            {
                "role": "user",
                "content": json.dumps(
                    {"description": description, "categories": paths}, ensure_ascii=False
                ),
            }
        ],
        "store": False,
        "max_output_tokens": config.max_output_tokens,
        "text": {
            "format": {
                "type": "json_schema",
                "name": "category_suggestion",
                "strict": True,
                "schema": schema,
            }
        },
    }
    if len(json.dumps(request, ensure_ascii=False).encode()) > config.max_request_bytes:
        raise CategorizationError(
            "request_limit", "Pakiet przekracza limit AI; wybierz kategorię ręcznie."
        )
    return SuggestionPacket(request, mapping, ctx.snapshot(), taxonomy, digest(request))
