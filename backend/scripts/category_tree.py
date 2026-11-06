"""Operator-only CLI. Data-bundle code is never imported; production APPLY is opt-in."""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import os
import re
import stat
from collections.abc import Sequence
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Never
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.engine import make_url
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from scripts.category_tree_manifest import (
    CategoryTreeError,
    GuardReport,
    PreparedTree,
    _private_bytes,
    canonical_hash,
    compile_tree,
    load_bundle,
)


class SafeParser(argparse.ArgumentParser):
    def error(self, message: str) -> Never:
        raise CategoryTreeError("invalid_arguments")


def _positive(value: str) -> int:
    number = int(value)
    if not 0 < number <= 2147483647:
        raise ValueError()
    return number


def _parser() -> argparse.ArgumentParser:
    parser = SafeParser(description="Private category-tree operator", allow_abbrev=False)
    modes = parser.add_mutually_exclusive_group()
    for mode in ["preflight", "verify", "apply"]:
        modes.add_argument("--" + mode, action="store_true")
    for name in ["bundle-dir", "report-file"]:
        parser.add_argument("--" + name, type=Path, required=True)
    for name in ["owner", "operation-id"]:
        parser.add_argument("--" + name, type=UUID, required=True)
    for name in ["source-sha", "mapping-sha", "proposal-sha"]:
        parser.add_argument("--" + name, required=True)
    parser.add_argument("--statement-timeout-ms", type=_positive, required=True)
    parser.add_argument("--lock-timeout-ms", type=_positive)
    parser.add_argument("--approval-file", type=Path)
    parser.add_argument("--expected-report", type=Path)
    parser.add_argument("--operator-sha")
    parser.add_argument("--actual-migration-closed", action="store_true")
    return parser


def operator_digest() -> str:
    root = Path(__file__).parent
    return canonical_hash(
        {
            name: hashlib.sha256((root / name).read_bytes()).hexdigest()
            for name in [
                "category_tree_manifest.py",
                "category_tree_guard.py",
                "category_tree_apply.py",
                "category_tree.py",
            ]
        }
    )


def _json(path: Path) -> dict[str, Any]:
    value = json.loads(_private_bytes(path))
    if not isinstance(value, dict):
        raise CategoryTreeError("invalid_private_json")
    return value


def _fresh(value: Any, now: datetime, max_age: int) -> None:
    when = datetime.fromisoformat(value)
    if when.tzinfo is None or not 0 < max_age or not 0 <= (now - when).total_seconds() <= max_age:
        raise CategoryTreeError("stale_evidence")


def validate_approval(approval: dict[str, Any], identity: dict[str, Any], *, now: datetime) -> None:
    """Private operator attestations, not cryptographic grants issued by the app."""
    try:
        if set(approval) != {
            "version",
            "scope",
            "production_apply_approved",
            "identity",
            "issued_at",
            "max_age_seconds",
            "evidence",
        }:
            raise ValueError()
        if (
            approval["version"] != 1
            or approval["scope"] != "category_tree_apply_v1"
            or approval["production_apply_approved"] is not True
            or approval["identity"] != identity
        ):
            raise ValueError()
        age = approval["max_age_seconds"]
        if type(age) is not int:
            raise ValueError()
        _fresh(approval["issued_at"], now, age)
        evidence = approval["evidence"]
        if set(evidence) != {"backup_restore", "rehearsal", "fence"}:
            raise ValueError()
        for kind, pointer in evidence.items():
            if set(pointer) != {"path", "sha256"}:
                raise ValueError()
            raw = _private_bytes(Path(pointer["path"]))
            if hashlib.sha256(raw).hexdigest() != pointer["sha256"]:
                raise ValueError()
            proof = json.loads(raw)
            if (
                proof["kind"] != kind
                or proof["passed"] is not True
                or proof["identity"] != identity
            ):
                raise ValueError()
            _fresh(proof["issued_at"], now, age)
            if (
                kind == "backup_restore"
                and re.fullmatch("[0-9a-f]{64}", proof["snapshot_sha"]) is None
            ):
                raise ValueError()
    except CategoryTreeError:
        raise
    except (ValueError, TypeError, KeyError, OSError):
        raise CategoryTreeError("invalid_apply_approval") from None


def _is_test_target(url: str) -> bool:
    parsed = make_url(url)
    return bool(
        parsed.drivername == "postgresql+asyncpg"
        and parsed.host in {"127.0.0.1", "localhost"}
        and parsed.database
        and parsed.database.endswith(("_test", "_restore"))
    )


def _identity(args: argparse.Namespace, plan: PreparedTree, url: str) -> dict[str, Any]:
    revision = os.environ.get("CATEGORY_TREE_RUNTIME_REVISION", "")
    image = os.environ.get("CATEGORY_TREE_RUNTIME_IMAGE", "")
    if not revision or not image:
        raise CategoryTreeError("runtime_identity_required")
    return {
        "owner": str(args.owner),
        "operation_id": str(args.operation_id),
        "source_sha": args.source_sha,
        "mapping_sha": plan.mapping_sha,
        "proposal_sha": plan.proposal_sha,
        "before_fingerprint": plan.before_fingerprint,
        "operator_sha": operator_digest(),
        "runtime_revision": revision,
        "runtime_image": image,
        "schema_revision": plan.schema_revision,
        "target_sha": canonical_hash(
            {"url": url, "schema": os.environ.get("CATEGORY_TREE_TEST_SCHEMA", "public")}
        ),
    }


def _output(path: Path, value: Any) -> None:
    parent = path.parent.lstat()
    if not stat.S_ISDIR(parent.st_mode) or parent.st_uid != os.geteuid() or parent.st_mode & 0o077:
        raise CategoryTreeError("private_output_required")
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
    with os.fdopen(fd, "w") as stream:
        json.dump(value, stream, ensure_ascii=False, sort_keys=True, indent=2)
        stream.flush()
        os.fsync(stream.fileno())


def _authorize(
    args: argparse.Namespace, identity: dict[str, Any], url: str, *, now: datetime
) -> GuardReport:
    if args.approval_file is None or args.expected_report is None or args.lock_timeout_ms is None:
        raise CategoryTreeError("apply_approval_required")
    if args.operator_sha != identity["operator_sha"]:
        raise CategoryTreeError("operator_digest_mismatch")
    raw = _private_bytes(args.expected_report)
    envelope = json.loads(raw)
    if envelope["identity"] != identity or envelope["mode"] != "preflight":
        raise CategoryTreeError("preflight_identity_mismatch")
    expected = GuardReport.model_validate(envelope["report"])
    approval = _json(args.approval_file)
    # A separate test-only attestation is permitted ONLY for disposable loopback DBs.
    if approval.get("scope") == "category_tree_rehearsal_v1":
        if not _is_test_target(url) or approval.get("production_apply_approved") is not False:
            raise CategoryTreeError("invalid_rehearsal_target")
        approval = dict(approval, scope="category_tree_apply_v1", production_apply_approved=True)
    identity_with_preflight = {**identity, "preflight_sha": hashlib.sha256(raw).hexdigest()}
    validate_approval(approval, identity_with_preflight, now=now)
    _fresh(envelope["issued_at"], now, approval["max_age_seconds"])
    if expected.owner_id != args.owner or expected.blockers or not expected.actual_migration_closed:
        raise CategoryTreeError("invalid_preflight")
    return expected


async def _execute(
    args: argparse.Namespace,
    plan: PreparedTree,
    url: str,
    identity: dict[str, Any],
    expected: GuardReport | None,
) -> int:
    schema = os.environ.get("CATEGORY_TREE_TEST_SCHEMA")
    connect: dict[str, Any] = {}
    if schema:
        if (
            not _is_test_target(url)
            or re.fullmatch("category_tree_test_[0-9a-f]{32}", schema) is None
        ):
            raise CategoryTreeError("invalid_test_schema")
        connect = {"server_settings": {"search_path": schema}}
    # Importing app.database constructs its global (unused here) engine. Delay all
    # app/metadata/service imports until arguments, target, bundle and approval pass.
    from scripts.category_tree_apply import apply_tree, inspect_operation, request_fingerprint
    from scripts.category_tree_guard import preflight

    engine = create_async_engine(url, echo=False, connect_args=connect)
    try:
        factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
        async with factory() as db:
            try:
                if args.apply:
                    await db.execute(text("SET TRANSACTION ISOLATION LEVEL SERIALIZABLE"))
                elif args.verify:
                    await db.execute(
                        text("SET TRANSACTION ISOLATION LEVEL READ COMMITTED READ ONLY")
                    )
                else:
                    await db.execute(
                        text("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY")
                    )
                await db.execute(
                    text("SELECT set_config('statement_timeout',:value,true)"),
                    {"value": str(args.statement_timeout_ms)},
                )
                await db.execute(
                    text("SELECT set_config('lock_timeout',:value,true)"),
                    {"value": str(args.lock_timeout_ms or args.statement_timeout_ms)},
                )
                request = request_fingerprint(args.owner, args.operation_id, plan)
                if args.apply:
                    if expected is None:
                        raise CategoryTreeError("invalid_preflight")
                    # Re-read private proofs immediately before writes as well as before engine construction.
                    _authorize(args, identity, url, now=datetime.now(UTC))
                    result = await apply_tree(
                        db,
                        args.owner,
                        plan,
                        operation_id=args.operation_id,
                        expected=expected,
                        request_hash=request,
                    )
                    await db.commit()
                    payload = result.model_dump(mode="json")
                    code = 0
                    mode = "apply"
                elif args.verify:
                    verification = await inspect_operation(
                        db, args.owner, plan, operation_id=args.operation_id, request_hash=request
                    )
                    payload = verification.model_dump(mode="json")
                    mode = "verify"
                    code = {
                        "applied": 0,
                        "not_applied": 3,
                        "busy_or_conflict": 4,
                        "applied_state_changed": 5,
                        "receipt_conflict": 2,
                    }[verification.status]
                else:
                    report = await preflight(
                        db, args.owner, plan, actual_migration_closed=args.actual_migration_closed
                    )
                    payload = report.model_dump(mode="json")
                    code = 2 if report.blockers else 0
                    mode = "preflight"
                await db.rollback()
            except BaseException:
                await db.rollback()
                raise
        _output(
            args.report_file,
            {
                "version": 1,
                "mode": mode,
                "identity": identity,
                "issued_at": datetime.now(UTC).isoformat(),
                "report": payload,
            },
        )
        print("category_tree: " + mode + (" pass" if code == 0 else " stop"))
        return code
    finally:
        await engine.dispose()


def run(args: Sequence[str]) -> int:
    try:
        parsed = _parser().parse_args(args)
        from app.config import settings

        url = os.environ.get("CATEGORY_TREE_DATABASE_URL", "")
        if not url or url != settings.DATABASE_URL:
            raise CategoryTreeError("database_target_mismatch")
        target = make_url(url)
        if target.drivername != "postgresql+asyncpg":
            raise CategoryTreeError("invalid_database_target")
        if parsed.report_file.exists() or parsed.report_file.is_symlink():
            raise CategoryTreeError("report_already_exists")
        bundle = load_bundle(
            parsed.bundle_dir,
            expected_source_sha=parsed.source_sha,
            expected_mapping_sha=parsed.mapping_sha,
            expected_proposal_sha=parsed.proposal_sha,
        )
        plan = compile_tree(bundle)
        identity = _identity(parsed, plan, url)
        expected = (
            _authorize(parsed, identity, url, now=datetime.now(UTC)) if parsed.apply else None
        )
        return asyncio.run(_execute(parsed, plan, url, identity, expected))
    except CategoryTreeError as error:
        print("category_tree: " + error.code)
        return 2
    except (Exception, KeyboardInterrupt):  # noqa: BLE001 - secret-safe process boundary
        # Even SQLAlchemy errors can embed raw SQL parameters, URLs or user labels.
        print("category_tree: failed_or_unknown; use read-only verify")
        return 2


if __name__ == "__main__":
    import sys

    raise SystemExit(run(sys.argv[1:]))
