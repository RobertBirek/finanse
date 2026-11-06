"""Pure, fail-closed category-tree proposal compiler. No database or executable input."""

from __future__ import annotations

import hashlib
import json
import os
import re
import stat
from collections import Counter
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Annotated, Any, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, StrictBool, StrictInt, StrictStr, ValidationError


class CategoryTreeError(Exception):
    def __init__(self, code: str) -> None:
        self.code = code
        super().__init__(code)


Kind = Literal["expense", "income"]
Action = Literal["KEEP", "EDIT", "HOLD"]
Label = Annotated[StrictStr, Field(min_length=1, max_length=200)]


class Frozen(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")


class GuardReport(Frozen):
    """Pure preflight contract, usable before any application/database import."""

    owner_id: UUID
    before_fingerprint: str
    reference_fingerprints: dict[str, str]
    reference_counts: dict[str, int]
    blockers: tuple[str, ...]
    actual_migration_closed: bool
    schema_revision: str
    control_ids: dict[str, tuple[UUID, ...]] = Field(default_factory=dict)


class CategoryBefore(Frozen):
    id: UUID
    parent_id: UUID | None
    name: Label
    type: Kind
    source: StrictStr
    is_active: StrictBool


class NewRef(Frozen):
    key: StrictStr


class NewNode(Frozen):
    key: StrictStr
    name: Label
    parent: UUID | NewRef | None
    type: Literal["expense"] = "expense"


class CategoryPatch(Frozen):
    id: UUID
    name: Label | None
    parent_changed: StrictBool
    parent: UUID | NewRef | None


class SourceRow(CategoryBefore):
    transaction_count: Annotated[StrictInt, Field(ge=0)]


class SourceFile(Frozen):
    read_only: Literal[True]
    rolled_back: Literal[True]
    schema_revision: StrictStr = Field(alias="schema")
    observed_at: StrictStr
    categories: tuple[SourceRow, ...]


class MappingDecision(Frozen):
    source_id: UUID
    type: Kind
    source_path: StrictStr
    target_path: StrictStr
    action: Action
    reason: StrictStr
    preserve_id: StrictBool
    source: StrictStr
    is_active: StrictBool
    direct_transaction_count: Annotated[StrictInt, Field(ge=0)]


class MappingFile(Frozen):
    status: Literal["proposal_not_approved_not_executed"]
    snapshot_sha256: StrictStr
    source_count: Annotated[StrictInt, Field(gt=0)]
    target_count: Annotated[StrictInt, Field(gt=0)]
    action_counts: dict[Action, StrictInt]
    new_expense_nodes: tuple[StrictStr, ...]
    mapping: tuple[MappingDecision, ...]
    blocked_automatic_actions: tuple[StrictStr, ...]


@dataclass(frozen=True)
class CategoryTreeBundle:
    source: tuple[CategoryBefore, ...]
    decisions: tuple[MappingDecision, ...]
    new_paths: tuple[str, ...]
    source_count: int
    target_count: int
    action_counts: dict[Action, int]
    source_sha: str
    mapping_sha: str
    proposal_sha: str
    schema_revision: str


@dataclass(frozen=True)
class PreparedTree:
    before_fingerprint: str
    patches: tuple[CategoryPatch, ...]
    creates: tuple[NewNode, ...]
    expected_paths: dict[UUID | NewRef, str]
    hold_ids: frozenset[UUID]
    keep_ids: frozenset[UUID]
    mapping_sha: str
    proposal_sha: str
    source: tuple[CategoryBefore, ...]
    schema_revision: str


def canonical_hash(value: Any) -> str:
    return hashlib.sha256(
        json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()
    ).hexdigest()


def tree_fingerprint(rows: Sequence[CategoryBefore]) -> str:
    return canonical_hash(
        [row.model_dump(mode="json") for row in sorted(rows, key=lambda r: str(r.id))]
    )


_FILES = frozenset(
    {
        "source-private.json",
        "mapping-private.json",
        "proposal-private.md",
        "prepare_design.py",
        "verification-private.json",
    }
)
_BLOCKED = frozenset(
    {
        "delete",
        "merge",
        "deactivate",
        "change_type",
        "rewrite_postings",
        "FX_conversion",
        "loan_account_creation",
        "enable_marker_or_consent",
        "historical_rule_scan",
    }
)


def _private_bytes(path: Path) -> bytes:
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    try:
        info = os.fstat(fd)
        if not stat.S_ISREG(info.st_mode) or info.st_uid != os.geteuid() or info.st_mode & 0o077:
            raise CategoryTreeError("bundle_integrity")
        with os.fdopen(fd, "rb", closefd=False) as stream:
            return stream.read()
    finally:
        os.close(fd)


def load_bundle(
    directory: Path,
    *,
    expected_source_sha: str,
    expected_mapping_sha: str,
    expected_proposal_sha: str,
) -> CategoryTreeBundle:
    try:
        info = directory.lstat()
        if not stat.S_ISDIR(info.st_mode) or info.st_uid != os.geteuid() or info.st_mode & 0o077:
            raise CategoryTreeError("bundle_integrity")
        pinned = {
            "source-private.json": expected_source_sha,
            "mapping-private.json": expected_mapping_sha,
            "proposal-private.md": expected_proposal_sha,
        }
        if any(re.fullmatch(r"[0-9a-f]{64}", sha) is None for sha in pinned.values()):
            raise CategoryTreeError("bundle_integrity")
        manifest = json.loads(_private_bytes(directory / "manifest-private.json"))
        hashes = manifest["files"]
        if not isinstance(hashes, dict) or set(hashes) != _FILES:
            raise CategoryTreeError("bundle_integrity")
        payloads = {name: _private_bytes(directory / name) for name in _FILES}
        if any(
            hashlib.sha256(payload).hexdigest() != hashes[name]
            for name, payload in payloads.items()
        ):
            raise CategoryTreeError("bundle_integrity")
        if any(hashes[name] != sha for name, sha in pinned.items()):
            raise CategoryTreeError("bundle_integrity")
        source = SourceFile.model_validate_json(payloads["source-private.json"])
        mapping = MappingFile.model_validate_json(payloads["mapping-private.json"])
        if (
            mapping.snapshot_sha256 != expected_source_sha
            or frozenset(mapping.blocked_automatic_actions) != _BLOCKED
        ):
            raise CategoryTreeError("bundle_integrity")
        return CategoryTreeBundle(
            source=tuple(
                CategoryBefore.model_validate(row.model_dump(exclude={"transaction_count"}))
                for row in source.categories
            ),
            decisions=mapping.mapping,
            new_paths=mapping.new_expense_nodes,
            source_count=mapping.source_count,
            target_count=mapping.target_count,
            action_counts=mapping.action_counts,
            source_sha=expected_source_sha,
            mapping_sha=expected_mapping_sha,
            proposal_sha=expected_proposal_sha,
            schema_revision=source.schema_revision,
        )
    except CategoryTreeError:
        raise
    except (OSError, ValueError, TypeError, KeyError, ValidationError):
        raise CategoryTreeError("bundle_integrity") from None


def compile_tree(bundle: CategoryTreeBundle) -> PreparedTree:
    def fail() -> None:
        raise CategoryTreeError("invalid_tree")

    before = {row.id: row for row in bundle.source}
    decisions = {row.source_id: row for row in bundle.decisions}
    if (
        len(before) != len(bundle.source)
        or len(decisions) != len(bundle.decisions)
        or set(before) != set(decisions)
        or len(before) != bundle.source_count
        or Counter(row.action for row in bundle.decisions) != bundle.action_counts
    ):
        fail()
    original_paths: dict[UUID, str] = {}

    def original_path(ident: UUID, seen: frozenset[UUID] = frozenset()) -> str:
        if ident not in before or ident in seen:
            fail()
        row = before[ident]
        if not row.name.strip() or " / " in row.name:
            fail()
        if row.parent_id is None:
            return row.name
        if row.parent_id not in before or before[row.parent_id].type != row.type:
            fail()
        return original_path(row.parent_id, seen | {ident}) + " / " + row.name

    typed_paths: dict[tuple[Kind, str], UUID | NewRef] = {}
    expected_paths: dict[UUID | NewRef, str] = {}
    for row in bundle.source:
        decision = decisions[row.id]
        original_paths[row.id] = original_path(row.id)
        if (
            decision.type != row.type
            or decision.source != row.source
            or decision.is_active != row.is_active
            or not decision.preserve_id
            or decision.source_path != original_paths[row.id]
            or (decision.action != "EDIT" and decision.target_path != decision.source_path)
        ):
            fail()
        typed = (row.type, decision.target_path)
        if typed in typed_paths:
            fail()
        typed_paths[typed] = row.id
        expected_paths[row.id] = decision.target_path
    for path in bundle.new_paths:
        if ("expense", path) in typed_paths:
            fail()
        ref = NewRef(key=path)
        typed_paths["expense", path] = ref
        expected_paths[ref] = path
    if len(expected_paths) != bundle.target_count:
        fail()

    def target_parts(kind: Kind, path: str) -> tuple[str, UUID | NewRef | None]:
        parts = path.split(" / ")
        if len(parts) > 2 or any(not p.strip() or len(p) > 200 for p in parts):
            fail()
        parent = typed_paths.get((kind, parts[0])) if len(parts) == 2 else None
        if len(parts) == 2 and parent is None:
            fail()
        return parts[-1], parent

    creates = []
    for path in bundle.new_paths:
        name, parent = target_parts("expense", path)
        creates.append(NewNode(key=path, name=name, parent=parent))
    creates.sort(key=lambda n: expected_paths[NewRef(key=n.key)].count(" / "))
    patches = []
    for row in bundle.source:
        decision = decisions[row.id]
        name, parent = target_parts(row.type, decision.target_path)
        if name != row.name or parent != row.parent_id:
            if decision.action != "EDIT":
                fail()
            patches.append(
                CategoryPatch(
                    id=row.id,
                    name=name if name != row.name else None,
                    parent_changed=parent != row.parent_id,
                    parent=parent,
                )
            )
    return PreparedTree(
        before_fingerprint=tree_fingerprint(bundle.source),
        patches=tuple(patches),
        creates=tuple(creates),
        expected_paths=expected_paths,
        hold_ids=frozenset(row.source_id for row in bundle.decisions if row.action == "HOLD"),
        keep_ids=frozenset(row.source_id for row in bundle.decisions if row.action == "KEEP"),
        mapping_sha=bundle.mapping_sha,
        proposal_sha=bundle.proposal_sha,
        source=bundle.source,
        schema_revision=bundle.schema_revision,
    )
