"""Approval evidence binds exact Git objects; it never filters the source diff."""

import hashlib
import json
import subprocess
from dataclasses import asdict, replace
from pathlib import Path

import pytest

from tests.test_ops.preflight_fixtures import PinnedScenario, module


class SourceScenario(PinnedScenario):
    def __init__(self, root):
        super().__init__(root)
        trust = module("release_preflight_trust")
        git = Path("/usr/bin/git").resolve()
        self.tools = replace(
            self.tools,
            git=trust.FilePin(
                git,
                hashlib.sha256(git.read_bytes()).hexdigest(),
                git.stat().st_mode & 0o7777,
                0,
            ),
        )
        self.git("init", "-q")
        self.git("config", "user.name", "Synthetic")
        self.git("config", "user.email", "synthetic@example.invalid")
        self.write("ops/release_preflight.py", b"# original\n")
        self.base = self.commit()
        self.write("ops/release_preflight.py", b"# reviewed\n")
        self.write("ops/release_preflight_review.py", b"# newly added\n")
        self.candidate = self.commit()
        self.baselines = dict.fromkeys(("backend", "worker", "frontend"), self.base)
        self.report = root / "review.md"
        self.report.write_text("Synthetic accepted review. Not real operator approval.")
        self.report.chmod(0o600)
        self.proof = root / "review-proof.json"
        self.bundle_hash = "e" * 64

    def git(self, *args):
        return subprocess.check_output(
            [
                str(self.tools.git.path),
                "--no-pager",
                "--no-replace-objects",
                "-c",
                "core.hooksPath=/dev/null",
                "-C",
                str(self.repo),
                *args,
            ],
            text=True,
            stderr=subprocess.PIPE,
            env={
                "PATH": "/usr/bin:/bin",
                "HOME": str(self.root),
                "GIT_CONFIG_NOSYSTEM": "1",
                "GIT_CONFIG_GLOBAL": "/dev/null",
            },
        ).strip()

    def write(self, name, content):
        path = self.repo / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(content)

    def commit(self):
        self.git("add", ".")
        self.git("commit", "-qm", "synthetic")
        return self.git("rev-parse", "HEAD")

    def changes(self):
        return module("release_preflight_review").collect_source_changes(
            self.runner(),
            candidate=self.candidate,
            service_revisions=self.baselines,
        )

    def proof_record(self):
        return {
            "version": 1,
            "candidate": self.candidate,
            "service_revisions": self.baselines,
            "checker_bundle_sha256": self.bundle_hash,
            "review_report_sha256": hashlib.sha256(self.report.read_bytes()).hexdigest(),
            "review_result": "accepted_no_open_critical_or_important",
            "changes": [asdict(change) for change in self.changes()],
        }

    def verify(self, record=None):
        if record is None:
            record = self.proof_record()
        self.proof.write_text(json.dumps(record))
        self.proof.chmod(0o600)
        return module("release_preflight_review").verify_review_scope(
            self.proof,
            hashlib.sha256(self.proof.read_bytes()).hexdigest(),
            candidate=self.candidate,
            service_revisions=self.baselines,
            checker_bundle_sha256=self.bundle_hash,
            actual_changes=self.changes(),
            review_report=self.report,
        )


@pytest.fixture
def source(tmp_path):
    return SourceScenario(tmp_path)


def facts(policy, changes, scope=None, source=None):
    return policy.ReleaseFacts(
        candidate=source.candidate if source else "a" * 40,
        service_revisions=source.baselines
        if source
        else dict.fromkeys(
            ("backend", "worker", "frontend"),
            "b" * 40,
        ),
        image_ids=dict.fromkeys(("backend", "worker", "frontend"), "sha256:" + "c" * 64),
        changed_paths=changes,
        schema_heads=("head",),
        lineage={"head": None},
        compose_up_flags=frozenset({"--no-start", "--no-deps", "--no-build"}),
        ancestry_ok=True,
        historical_migration_changed=False,
        tooling_scope=scope,
        checker_bundle_sha256=source.bundle_hash if source else "e" * 64,
    )


def test_unknown_ops_stays_blocked_without_scope():
    policy = module("release_preflight_policy")
    result = policy.classify(
        facts(
            policy,
            {"backend": ("ops/release_preflight.py",), "worker": (), "frontend": ()},
        )
    )
    assert result.action == "blocked"
    assert result.reason_codes == ("unknown_change_scope",)


def _node_ci_change(policy, service="backend"):
    return policy.SourceChange(
        service,
        ".github/workflows/ci.yml",
        "100644",
        "14501064d0b671310fb713ed67f2db0490e43da2",
        "100644",
        "15a67462ad13053766cc1359dc11142fc40a245c",
        "0ed9e79f0ab37b7163481e0fa1db1c99a6a3c9ef2f20214c18b7544bfda71ebe",
    )


def test_reviewed_node_ci_pin_does_not_waive_migration_and_runtime_gates():
    policy = module("release_preflight_policy")
    baselines = dict.fromkeys(("backend", "frontend", "worker"), "b" * 40)
    changes = {
        "backend": (".github/workflows/ci.yml", "backend/requirements.txt"),
        "worker": (".github/workflows/ci.yml",),
        "frontend": (".github/workflows/ci.yml", "frontend/Dockerfile"),
    }
    scope = policy.VerifiedToolingScope(
        proof_sha256="d" * 64,
        changes=tuple(_node_ci_change(policy, service) for service in baselines),
        candidate="a" * 40,
        service_revisions=tuple(sorted(baselines.items())),
        checker_bundle_sha256="e" * 64,
    )
    value = replace(
        facts(policy, changes, scope),
        lineage={"head": None, "first": "head", "second": "first"},
    )
    assert policy.classify(replace(value, tooling_scope=None)).reason_codes == (
        "unknown_change_scope",
    )
    result = policy.classify(value)
    assert result.action == "migration_then_app"
    assert result.pending_migrations == ("first", "second")
    assert {
        "approved_tooling_review",
        "rebuild_and_verify_runtime",
        "exact_migration_approval",
        "backup_restore",
        "verify_release",
    } <= set(result.required_gates)
    incomplete = replace(scope, changes=scope.changes[:-1])
    assert policy.classify(replace(value, tooling_scope=incomplete)).action == "blocked"


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("before_mode", "100755"),
        ("before_blob", "1" * 40),
        ("before_blob", None),
        ("after_mode", "100755"),
        ("after_blob", "2" * 40),
        ("after_blob", None),
        ("after_sha256", "3" * 64),
        ("path", ".github/workflows/release.yml"),
    ],
)
def test_other_ci_transitions_cannot_enter_approved_scope(field, value):
    policy = module("release_preflight_policy")
    change = replace(_node_ci_change(policy), **{field: value})
    assert not policy.valid_tooling_change(change)


def test_review_collector_hashes_ci_bytes_and_scope_match_is_exact(source, monkeypatch):
    policy = module("release_preflight_policy")
    path = ".github/workflows/ci.yml"
    before = b'node-version: "22"\n'
    after = b'node-version: "24.22.3"\n'
    source.write(path, before)
    source.base = source.commit()
    source.write(path, after)
    source.candidate = source.commit()
    source.baselines = dict.fromkeys(source.baselines, source.base)
    monkeypatch.setattr(
        policy,
        "REVIEWED_NODE_CI_TRANSITION",
        (
            source.git("rev-parse", f"{source.base}:{path}"),
            source.git("rev-parse", f"{source.candidate}:{path}"),
            hashlib.sha256(after).hexdigest(),
        ),
    )
    scope = source.verify()
    assert len(scope.changes) == 3
    assert all(change.after_sha256 == hashlib.sha256(after).hexdigest() for change in scope.changes)
    source.write(path, after + b"other-step: not-reviewed\n")
    source.candidate = source.commit()
    with pytest.raises(policy.PreflightInputError, match="review_scope_invalid"):
        source.verify()


def test_exact_reviewed_checker_paths_are_reported_not_filtered(source):
    policy = module("release_preflight_policy")
    scope = source.verify()
    paths = {
        service: tuple(c.path for c in source.changes() if c.service == service)
        for service in source.baselines
    }
    original = dict(paths)
    result = policy.classify(facts(policy, paths, scope, source))
    assert result.action == "no_rollout"
    assert "approved_tooling_review" in result.required_gates
    assert paths == original
    runtime = {**paths, "backend": (*paths["backend"], "backend/app/main.py")}
    result = policy.classify(facts(policy, runtime, scope, source))
    assert result.action == "app_only"
    assert {"backup_restore", "runtime", "approved_tooling_review"} <= set(result.required_gates)


@pytest.mark.parametrize(
    "kind",
    [
        "candidate",
        "backend",
        "worker",
        "frontend",
        "bundle",
        "report",
        "unresolved",
        "duplicate",
        "missing",
        "forged_blob",
        "mode",
        "extra",
        "path_type",
        "service_type",
        "mode_type",
    ],
)
def test_scope_proof_binds_every_service_and_exact_candidate(source, kind):
    review = module("release_preflight_review")
    record = source.proof_record()
    if kind == "candidate":
        record["candidate"] = "f" * 40
    elif kind in source.baselines:
        record["service_revisions"] = {**source.baselines, kind: "f" * 40}
    elif kind == "bundle":
        record["checker_bundle_sha256"] = "f" * 64
    elif kind == "report":
        record["review_report_sha256"] = "f" * 64
    elif kind == "unresolved":
        record["review_result"] = "open_important"
    elif kind == "duplicate":
        record["changes"].append(dict(record["changes"][0]))
    elif kind == "missing":
        record["changes"].pop()
    elif kind == "forged_blob":
        record["changes"][0]["after_blob"] = "f" * 40
    elif kind == "mode":
        record["changes"][0]["after_mode"] = "100755"
    elif kind in {"path_type", "service_type", "mode_type"}:
        field = {"path_type": "path", "service_type": "service", "mode_type": "after_mode"}[kind]
        record["changes"][0][field] = []
    else:
        record["approve_all_ops"] = True
    with pytest.raises(review.PreflightInputError):
        source.verify(record)


@pytest.mark.parametrize("path", ["ops/prepare_release.py", ".github/workflows/changed.yml"])
def test_foreign_ops_workflow_or_forged_blob_still_blocks(source, path):
    review = module("release_preflight_review")
    source.write(path, b"# not eligible\n")
    source.candidate = source.commit()
    with pytest.raises(review.PreflightInputError):
        source.verify()


def test_docs_only_new_candidate_still_invalidates_prior_scope(source):
    review = module("release_preflight_review")
    old_proof = source.proof_record()
    source.write("docs/new.md", b"new documentation\n")
    source.candidate = source.commit()
    with pytest.raises(review.PreflightInputError):
        source.verify(old_proof)


def test_collect_source_changes_preserves_binary_runtime_paths(source):
    review = module("release_preflight_review")
    source.write("frontend/src/icon.bin", b"\xff\x00binary")
    source.candidate = source.commit()
    changes = review.collect_source_changes(
        source.runner(),
        candidate=source.candidate,
        service_revisions=source.baselines,
    )
    binary = [change for change in changes if change.path == "frontend/src/icon.bin"]
    assert len(binary) == 3
    assert all(change.after_blob is not None for change in binary)
    assert all(change.after_sha256 is None for change in binary)


def test_changed_symlink_cannot_become_reviewed_code(source):
    review = module("release_preflight_review")
    path = source.repo / "ops/release_preflight.py"
    path.unlink()
    path.symlink_to("release_preflight_review.py")
    source.candidate = source.commit()
    with pytest.raises(review.PreflightInputError):
        source.changes()


def test_pure_policy_rejects_forged_scope_for_unrelated_operator():
    policy = module("release_preflight_policy")
    change = policy.SourceChange(
        "backend",
        "ops/prepare_release.py",
        None,
        None,
        "100644",
        "a" * 40,
        "b" * 64,
    )
    scope = policy.VerifiedToolingScope(
        proof_sha256="c" * 64,
        changes=(change,),
        candidate="a" * 40,
        service_revisions=tuple((s, "b" * 40) for s in ("backend", "frontend", "worker")),
        checker_bundle_sha256="e" * 64,
    )
    result = policy.classify(
        facts(
            policy,
            {"backend": ("ops/prepare_release.py",), "worker": (), "frontend": ()},
            scope,
        )
    )
    assert result.action == "blocked"
    assert result.reason_codes == ("unknown_change_scope",)


@pytest.mark.parametrize("kind", ["candidate", "baseline", "bundle"])
def test_pure_policy_scope_cannot_be_reused_for_changed_context(source, kind):
    policy = module("release_preflight_policy")
    scope = source.verify()
    paths = {
        service: tuple(c.path for c in source.changes() if c.service == service)
        for service in source.baselines
    }
    value = facts(policy, paths, scope, source)
    if kind == "candidate":
        value = replace(value, candidate="f" * 40)
    elif kind == "baseline":
        value = replace(value, service_revisions={**source.baselines, "worker": "f" * 40})
    else:
        value = replace(value, checker_bundle_sha256="f" * 64)
    assert policy.classify(value).action == "blocked"


@pytest.mark.parametrize("field", ["path", "service", "after_mode"])
def test_malformed_witness_is_blocked_without_raw_type_errors(source, field):
    policy = module("release_preflight_policy")
    scope = source.verify()
    paths = {
        service: tuple(c.path for c in source.changes() if c.service == service)
        for service in source.baselines
    }
    broken = replace(scope, changes=(replace(scope.changes[0], **{field: []}), *scope.changes[1:]))
    assert policy.classify(facts(policy, paths, broken, source)).action == "blocked"
