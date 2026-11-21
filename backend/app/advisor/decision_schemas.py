from datetime import date
from typing import Literal

from pydantic import BaseModel


class AttentionItem(BaseModel):
    kind: Literal["payment", "document", "task"]
    source_id: str
    title: str
    reason: str
    due_date: date | None = None
    href: str


class AttentionResult(BaseModel):
    as_of: date
    items: list[AttentionItem]


class DecisionExplanation(BaseModel):
    status: Literal["ok", "unavailable", "no_facts"]
    text: str | None = None
