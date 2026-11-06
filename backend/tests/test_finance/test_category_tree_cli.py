"""Pure boundary tests: invalid authorization must not even construct an engine."""

import importlib
import json
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any
from uuid import uuid4

import pytest

from scripts.category_tree_manifest import CategoryTreeError, compile_tree, load_bundle
from tests.test_finance.category_tree_cases import cases, write_bundle


def cli() -> Any:
    return importlib.import_module("scripts.category_tree")


def authorization(tmp_path: Path) -> tuple[Any, ...]:
    hashes = write_bundle(tmp_path / "input", *cases())
    plan = compile_tree(load_bundle(tmp_path / "input", **hashes))
    owner = uuid4()
    operation = uuid4()
    now = datetime(2026, 11, 6, tzinfo=UTC)
    identity = {
        "owner": str(owner),
        "operation_id": str(operation),
        "source_sha": hashes["expected_source_sha"],
        "mapping_sha": plan.mapping_sha,
        "proposal_sha": plan.proposal_sha,
        "before_fingerprint": plan.before_fingerprint,
        "operator_sha": "a" * 64,
        "runtime_revision": "test-revision",
        "runtime_image": "sha256:test-image",
        "schema_revision": plan.schema_revision,
        "target_sha": "b" * 64,
    }
    approval = {
        "version": 1,
        "scope": "category_tree_apply_v1",
        "production_apply_approved": True,
        "identity": identity,
        "issued_at": now.isoformat(),
        "max_age_seconds": 60,
        "evidence": {},
    }
    import hashlib

    for kind in ["backup_restore", "rehearsal", "fence"]:
        proof = {"kind": kind, "passed": True, "identity": identity, "issued_at": now.isoformat()}
        if kind == "backup_restore":
            proof["snapshot_sha"] = "c" * 64
        path = tmp_path / (kind + ".json")
        path.write_text(json.dumps(proof))
        path.chmod(0o600)
        approval["evidence"][kind] = {
            "path": str(path),
            "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
        }
    return approval, identity, now


def test_design_approval_cannot_authorize_production_apply(tmp_path: Path) -> None:
    _, identity, now = authorization(tmp_path)
    with pytest.raises(CategoryTreeError):
        cli().validate_approval(
            {"design_approved": True, "production_apply_approved": False}, identity, now=now
        )


@pytest.mark.parametrize(
    "mutation",
    [
        "missing",
        "stale",
        "future",
        "runtime",
        "owner",
        "db",
        "hash",
        "backup",
        "rehearsal",
        "fence",
        "zero_age",
        "bad_snapshot",
    ],
)
def test_missing_stale_or_mismatched_runtime_backup_rehearsal_fence_proof_refuses_apply(
    tmp_path: Path, mutation: str
) -> None:
    approval, identity, now = authorization(tmp_path)
    if mutation == "missing":
        approval.pop("identity")
    elif mutation == "stale":
        approval["issued_at"] = (now - timedelta(seconds=61)).isoformat()
    elif mutation == "future":
        approval["issued_at"] = (now + timedelta(seconds=1)).isoformat()
    elif mutation == "zero_age":
        approval["max_age_seconds"] = 0
    elif mutation in {"backup", "rehearsal", "fence"}:
        approval["evidence"].pop("backup_restore" if mutation == "backup" else mutation)
    elif mutation == "bad_snapshot":
        import hashlib

        p = Path(approval["evidence"]["backup_restore"]["path"])
        proof = json.loads(p.read_text())
        proof.pop("snapshot_sha")
        p.write_text(json.dumps(proof))
        approval["evidence"]["backup_restore"]["sha256"] = hashlib.sha256(
            p.read_bytes()
        ).hexdigest()
    else:
        approval["identity"] = dict(
            identity,
            **{
                {
                    "runtime": "runtime_image",
                    "owner": "owner",
                    "db": "target_sha",
                    "hash": "operator_sha",
                }[mutation]: "mismatch"
            },
        )
    with pytest.raises(CategoryTreeError):
        cli().validate_approval(approval, identity, now=now)


def test_matching_approval_checks_every_evidence_digest(tmp_path: Path) -> None:
    approval, identity, now = authorization(tmp_path)
    cli().validate_approval(approval, identity, now=now)
    Path(approval["evidence"]["fence"]["path"]).write_text("tampered")
    with pytest.raises(CategoryTreeError):
        cli().validate_approval(approval, identity, now=now)


@pytest.mark.parametrize("mutation", ["db", "owner", "hash", "approval", "timeout", "mode"])
def test_owner_db_or_hash_mismatch_opens_no_write_transaction(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    mutation: str,
) -> None:
    module = cli()
    hashes = write_bundle(tmp_path / "input", *cases())
    operation = uuid4()
    owner = uuid4()
    args = [
        "--apply",
        "--bundle-dir",
        str(tmp_path / "input"),
        "--owner",
        str(owner),
        "--operation-id",
        str(operation),
        "--report-file",
        str(tmp_path / "result.json"),
        "--statement-timeout-ms",
        "1000",
        "--lock-timeout-ms",
        "1000",
        "--source-sha",
        hashes["expected_source_sha"],
        "--mapping-sha",
        hashes["expected_mapping_sha"],
        "--proposal-sha",
        hashes["expected_proposal_sha"],
    ]
    monkeypatch.setenv(
        "CATEGORY_TREE_DATABASE_URL", "postgresql+asyncpg://private:secret@invalid/private"
    )
    if mutation == "owner":
        args[args.index("--owner") + 1] = "not-a-uuid"
    elif mutation == "hash":
        args[args.index("--mapping-sha") + 1] = "0" * 64
    elif mutation == "timeout":
        args[args.index("--statement-timeout-ms") + 1] = "0"
    elif mutation == "mode":
        args.append("--preflight")
    elif mutation == "approval":
        p = tmp_path / "design.json"
        p.write_text('{"design_approved":true}')
        p.chmod(0o600)
        args.extend(["--approval-file", str(p)])

    def no_engine(*a: Any, **kw: Any) -> None:
        pytest.fail("constructed engine on invalid input")

    monkeypatch.setattr(module, "create_async_engine", no_engine)
    assert module.run(args) == 2
    output = capsys.readouterr()
    assert "secret" not in output.out + output.err
    assert (
        str(owner) not in output.out + output.err and str(operation) not in output.out + output.err
    )
    assert not (tmp_path / "result.json").exists()


def test_errors_do_not_print_url_private_labels_or_uuid(capsys: pytest.CaptureFixture[str]) -> None:
    assert cli().run(["--unknown", "private-label/secret"]) == 2
    output = capsys.readouterr()
    assert "private-label" not in output.out + output.err


@pytest.mark.parametrize(
    "mutation", ["arguments", "owner", "mode", "target", "hash", "approval", "report"]
)
def test_invalid_input_never_constructs_global_or_operator_engine_in_fresh_process(
    tmp_path: Path, mutation: str
) -> None:
    import os
    import subprocess
    import sys

    hashes = write_bundle(tmp_path / "input", *cases())
    args = [
        "--apply",
        "--bundle-dir",
        str(tmp_path / "input"),
        "--owner",
        str(uuid4()),
        "--operation-id",
        str(uuid4()),
        "--report-file",
        str(tmp_path / "result.json"),
        "--statement-timeout-ms",
        "1000",
        "--lock-timeout-ms",
        "1000",
        "--source-sha",
        hashes["expected_source_sha"],
        "--mapping-sha",
        hashes["expected_mapping_sha"],
        "--proposal-sha",
        hashes["expected_proposal_sha"],
    ]
    env = dict(
        os.environ,
        CATEGORY_TREE_DATABASE_URL=os.environ["TEST_DATABASE_URL"],
        CATEGORY_TREE_RUNTIME_REVISION="test-revision",
        CATEGORY_TREE_RUNTIME_IMAGE="test-image",
    )
    if mutation == "arguments":
        args = ["--unknown", "private-label"]
    elif mutation == "owner":
        args[args.index("--owner") + 1] = "not-a-uuid"
    elif mutation == "mode":
        args.append("--verify")
    elif mutation == "target":
        env["CATEGORY_TREE_DATABASE_URL"] = "postgresql+asyncpg://private:secret@invalid/private"
    elif mutation == "hash":
        args[args.index("--mapping-sha") + 1] = "0" * 64
    elif mutation == "report":
        (tmp_path / "result.json").write_text("already-exists")
    # approval case intentionally has a valid bundle/target but no APPLY authority.
    marker = tmp_path / "engine-attempt"
    program = """
import json,os
from pathlib import Path
import sqlalchemy.ext.asyncio
def forbidden(*args,**kwargs):
 Path(os.environ['ENGINE_MARKER']).write_text('engine_attempted')
 raise RuntimeError('engine construction before validation')
sqlalchemy.ext.asyncio.create_async_engine=forbidden
from scripts.category_tree import run
assert run(json.loads(os.environ['INPUT_ARGS']))==2
"""
    env.update(ENGINE_MARKER=str(marker), INPUT_ARGS=json.dumps(args))
    result = subprocess.run(
        [sys.executable, "-c", program],
        env=env,
        capture_output=True,
        text=True,
        check=False,
        timeout=20,
    )
    assert not marker.exists(), "application/global engine was constructed before validation"
    assert result.returncode == 0, result.stderr
