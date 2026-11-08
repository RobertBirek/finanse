"""Public import representations contain source evidence, never client ledger postings."""

import datetime as dt
import uuid
from decimal import Decimal
from typing import Annotated, Literal, Self

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.finance.imports.contracts import (
    Bank,
    Check,
    ImportKind,
    ScheduleRow,
    SourcePosition,
    StatementRow,
)


class ImportDTO(BaseModel):
    model_config = ConfigDict(extra="forbid", from_attributes=True)


class SourceDTO(ImportDTO):
    id: uuid.UUID
    batch_id: uuid.UUID
    document_id: uuid.UUID
    sha256: str
    original_name: str
    bank: Bank | None = None
    layout: str | None = None
    parser_version: str | None = None
    processing_state: Literal["queued", "processing", "ready", "error", "unsupported"]
    validation_state: Literal["passed", "needs_review", "blocked"]
    current_revision_id: uuid.UUID | None = None
    checks: list[Check] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)


class BatchDTO(ImportDTO):
    id: uuid.UUID
    kind: ImportKind
    version: int
    archived_at: dt.datetime | None
    commit_state: Literal["not_committed", "partial", "committed"]
    sources: list[SourceDTO] = Field(default_factory=list)
    unresolved_count: int = 0


class RowDTO(ImportDTO):
    id: uuid.UUID
    source_id: uuid.UUID
    revision_id: uuid.UUID
    source_key: str
    position: SourcePosition
    kind: ImportKind
    bank_fields: StatementRow | None = None
    schedule_fields: ScheduleRow | None = None
    candidate_ids: list[uuid.UUID] = Field(default_factory=list)
    decision: dict[str, object] | None = None


class RowPage(ImportDTO):
    items: list[RowDTO]
    total: int
    offset: int
    limit: int


class SourceUploadResult(ImportDTO):
    source: SourceDTO
    is_duplicate: bool
    existing_batch_id: uuid.UUID | None = None


Version = Annotated[int, Field(strict=True, ge=1)]
ImportAction = Literal["create", "link", "defer"]
TransactionKind = Literal["expense", "income", "expense_refund", "transfer", "exchange"]


class ImportDecisionInput(ImportDTO):
    group_id: uuid.UUID
    row_ids: list[uuid.UUID] = Field(min_length=1)
    action: ImportAction
    kind: TransactionKind | None = None
    account_id: uuid.UUID | None = None
    other_account_id: uuid.UUID | None = None
    category_id: uuid.UUID | None = None
    existing_transaction_id: uuid.UUID | None = None
    fee_category_id: uuid.UUID | None = None
    manual_rate: Decimal | None = Field(default=None, gt=0, lt=1000000, decimal_places=6)
    acknowledgements: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_intent(self) -> Self:
        if len(set(self.row_ids)) != len(self.row_ids):
            raise ValueError("A row cannot occur twice in one group")
        if self.action == "defer":
            if self.existing_transaction_id is not None:
                raise ValueError("A deferred row cannot also claim an existing payment")
            return self
        if self.kind is None or self.account_id is None:
            raise ValueError("A financial decision requires its type and existing account")
        if self.action == "link":
            if self.existing_transaction_id is None:
                raise ValueError("A link requires the explicitly selected existing transaction")
        else:
            if self.existing_transaction_id is not None:
                raise ValueError("A new transaction cannot also be an existing transaction")
            if self.kind in {"expense", "income", "expense_refund"} and self.category_id is None:
                raise ValueError("A new external payment requires a category")
            if self.kind in {"transfer", "exchange"} and (
                self.other_account_id is None or self.other_account_id == self.account_id
            ):
                raise ValueError("A transfer requires two distinct existing accounts")
        return self


class DecisionUpdate(ImportDTO):
    expected_version: Version
    decisions: list[ImportDecisionInput] = Field(min_length=1)

    @model_validator(mode="after")
    def validate_unique_groups_and_rows(self) -> Self:
        if len({decision.group_id for decision in self.decisions}) != len(self.decisions):
            raise ValueError("Each group has exactly one decision per update")
        rows = [row for decision in self.decisions for row in decision.row_ids]
        if len(set(rows)) != len(rows):
            raise ValueError("The same source row cannot belong to two selected groups")
        return self


class PreviewRequest(ImportDTO):
    expected_version: Version
    group_ids: list[uuid.UUID] = Field(min_length=1)
    acknowledgements: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_distinct_groups(self) -> Self:
        if len(set(self.group_ids)) != len(self.group_ids):
            raise ValueError("Preview requires distinct complete groups")
        return self


class CommitRequest(ImportDTO):
    preview_id: uuid.UUID
    request_hash: str = Field(pattern=r"^[0-9a-f]{64}$")


class CommitResult(ImportDTO):
    receipt_id: uuid.UUID
    batch_id: uuid.UUID
    request_hash: str
    transaction_ids: list[uuid.UUID]
    linked_row_ids: list[uuid.UUID]
    remaining_group_ids: list[uuid.UUID]
    commit_state: Literal["not_committed", "partial", "committed"]


class JobDTO(ImportDTO):
    id: uuid.UUID
    source_id: uuid.UUID
    revision_id: uuid.UUID
    state: Literal["queued", "processing", "ready", "error", "unsupported"]
    attempt: int
    error_code: str | None = None
