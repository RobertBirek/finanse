"""Cold bootstrap must verify bytes before imports, never approve its own inputs."""

import hashlib
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

from tests.test_ops.preflight_fixtures import OPS, module
from tests.test_ops.test_release_preflight_review import SourceScenario

CODE = (
    "release_preflight.py",
    "release_preflight_policy.py",
    "release_preflight_trust.py",
    "release_preflight_exec.py",
    "release_preflight_snapshot.py",
    "release_preflight_review.py",
    "prepare_preflight_bundle.py",
    "preflight-requirements.txt",
)
YAML = (
    "__init__.py",
    "composer.py",
    "constructor.py",
    "cyaml.py",
    "dumper.py",
    "emitter.py",
    "error.py",
    "events.py",
    "loader.py",
    "nodes.py",
    "parser.py",
    "reader.py",
    "representer.py",
    "resolver.py",
    "scanner.py",
    "serializer.py",
    "tokens.py",
)


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


class Bundle:
    def __init__(self, root):
        root.chmod(0o700)
        self.root = root
        self.bundle = root / "bundle"
        self.bundle.mkdir(mode=0o700)
        for name in ("code", "vendor", "vendor/yaml"):
            (self.bundle / name).mkdir(mode=0o700)
        self.marker = root / "executed"
        stdlib = root / "stdlib"
        stdlib.mkdir(mode=0o700)
        safe = stdlib / "safe.py"
        safe.write_bytes(b"safe = 1\n")
        safe.chmod(0o600)
        tree = [["safe.py", digest(safe), 0o600]]
        self.runtime = {
            "python_path": str(Path(sys.executable).resolve()),
            "python_sha256": digest(Path(sys.executable).resolve()),
            "stdlib_root": str(stdlib),
            "stdlib_tree_sha256": hashlib.sha256(
                json.dumps(tree, ensure_ascii=True, separators=(",", ":")).encode()
            ).hexdigest(),
        }
        files = {}
        for name in CODE:
            files["code/" + name] = b"# synthetic member\n"
        files["code/preflight-requirements.txt"] = b"PyYAML==6.0.3\n"
        files["preflight_launcher.py"] = b"# separately approved bootstrap\n"
        files["code/release_preflight.py"] = (
            f"from pathlib import Path\nPath({str(self.marker)!r}).write_text('executed')\n"
        ).encode()
        files.update({"vendor/yaml/" + name: b"# synthetic yaml\n" for name in YAML})
        files["vendor/PyYAML-METADATA"] = b"Name: PyYAML\nVersion: 6.0.3\n"
        files["vendor/PyYAML-LICENSE"] = b"Synthetic license fixture\n"
        members = []
        for name, raw in files.items():
            path = self.bundle / name
            path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
            path.write_bytes(raw)
            path.chmod(0o600)
            members.append({"path": name, "sha256": digest(path), "mode": 0o600})
        self.manifest = {
            "version": 1,
            "source_revision": "a" * 40,
            "runtime": self.runtime,
            "files": sorted(members, key=lambda r: r["path"]),
        }
        self.manifest_path = self.bundle / "bundle-manifest.json"
        self.save()

    def save(self):
        self.manifest_path.write_text(json.dumps(self.manifest, sort_keys=True))
        self.manifest_path.chmod(0o600)
        return digest(self.manifest_path)


@pytest.fixture
def bundle(tmp_path):
    return Bundle(tmp_path)


@pytest.mark.parametrize("kind", ["digest", "member", "extra", "pyc", "runtime", "owner", "escape"])
def test_bundle_digest_and_members_are_checked_before_import(bundle, kind):
    launcher = module("preflight_launcher")
    expected = digest(bundle.manifest_path)
    owner = os.geteuid()
    if kind == "digest":
        expected = "0" * 64
    elif kind == "member":
        (bundle.bundle / "code/release_preflight.py").write_text("changed")
    elif kind in {"extra", "pyc"}:
        name = "extra.pth" if kind == "extra" else "__pycache__/extra.pyc"
        path = bundle.bundle / "code" / name
        path.parent.mkdir(exist_ok=True, mode=0o700)
        path.write_bytes(b"private-canary")
    elif kind == "runtime":
        bundle.manifest["runtime"]["python_sha256"] = "0" * 64
        expected = bundle.save()
    elif kind == "owner":
        owner += 1
    else:
        bundle.manifest["files"][0]["path"] = "../outside.py"
        expected = bundle.save()
    with pytest.raises(launcher.BootstrapError):
        launcher.verify_bundle(bundle.bundle, expected, owner_uid=owner)
    assert not bundle.marker.exists()


def test_valid_bundle_verification_never_imports_checker(bundle):
    launcher = module("preflight_launcher")
    value = launcher.verify_bundle(
        bundle.bundle,
        digest(bundle.manifest_path),
        owner_uid=os.geteuid(),
    )
    assert value["source_revision"] == "a" * 40
    assert not bundle.marker.exists()


def test_read_access_time_is_not_treated_as_integrity_drift(bundle):
    launcher = module("preflight_launcher")
    member = bundle.bundle / "code/release_preflight.py"
    os.utime(member, (1, 2))
    assert (
        launcher.verify_bundle(
            bundle.bundle,
            digest(bundle.manifest_path),
            owner_uid=os.geteuid(),
        )["source_revision"]
        == "a" * 40
    )
    assert not bundle.marker.exists()


def test_writable_nonsticky_package_ancestor_blocks_before_import(bundle):
    launcher = module("preflight_launcher")
    bundle.root.chmod(0o777)
    with pytest.raises(launcher.BootstrapError):
        launcher.verify_bundle(bundle.bundle, digest(bundle.manifest_path), owner_uid=os.geteuid())
    assert not bundle.marker.exists()


@pytest.mark.parametrize("optimize", [False, True])
def test_candidate_import_and_pth_canaries_never_execute(bundle, optimize):
    module("preflight_launcher")
    candidate = bundle.root / "candidate"
    candidate.mkdir()
    for name in ("release_preflight.py", "sitecustomize.py", "candidate.pth"):
        (candidate / name).write_text(
            f"from pathlib import Path;Path({str(bundle.marker)!r}).write_text('executed')"
        )
    result = subprocess.run(
        [
            sys.executable,
            *(["-O"] if optimize else []),
            "-I",
            "-S",
            "-B",
            str(OPS / "preflight_launcher.py"),
            "--bundle",
            str(bundle.bundle),
            "--bundle-sha256",
            "0" * 64,
            "--repository",
            str(candidate),
            "--toolchain",
            str(bundle.root / "not-present"),
            "--toolchain-sha256",
            "a" * 64,
            "--approval",
            str(bundle.root / "not-present"),
        ],
        env={"PATH": "/usr/bin:/bin", "PYTHONPATH": str(candidate)},
        cwd=candidate,
        text=True,
        capture_output=True,
        check=False,
        timeout=20,
    )
    assert result.returncode == 2
    assert json.loads(result.stdout)["action"] == "blocked"
    assert result.stderr == ""
    assert not bundle.marker.exists()


def test_candidate_directory_cannot_hold_approval_authority(bundle):
    launcher = module("preflight_launcher")
    repository = bundle.root / "candidate"
    repository.mkdir(mode=0o700)
    with pytest.raises(launcher.BootstrapError):
        launcher.validate_external_locations(
            repository,
            bundle.bundle,
            repository / "approval.json",
        )


def test_checker_bundle_must_be_outside_candidate_checkout(bundle):
    launcher = module("preflight_launcher")
    with pytest.raises(launcher.BootstrapError):
        launcher.validate_external_locations(
            bundle.root,
            bundle.bundle,
            bundle.root.parent / "external-approval.json",
        )


def test_wrong_import_origin_is_rejected_before_module_execution(bundle, monkeypatch):
    launcher = module("preflight_launcher")
    candidate = bundle.root / "candidate-import"
    candidate.mkdir()
    name = "synthetic_unapproved_checker"
    (candidate / (name + ".py")).write_text(
        f"from pathlib import Path\nPath({str(bundle.marker)!r}).write_text('executed')\n"
    )
    monkeypatch.syspath_prepend(str(candidate))
    with pytest.raises(launcher.BootstrapError):
        launcher.import_checked(name, bundle.bundle / "code/release_preflight.py")
    assert not bundle.marker.exists()


def test_unreadable_runtime_subtree_cannot_be_silently_omitted(bundle, monkeypatch):
    launcher = module("preflight_launcher")
    root = Path(bundle.runtime["stdlib_root"])
    hidden = root / "hidden"
    hidden.mkdir(mode=0o700)
    original = launcher.os.scandir

    def denied(path):
        if isinstance(path, (str, Path)) and Path(path) == hidden:
            raise PermissionError("private-canary")
        return original(path)

    monkeypatch.setattr(launcher.os, "scandir", denied)
    with pytest.raises(launcher.BootstrapError) as error:
        launcher.runtime_tree_digest(root, owner_uid=os.geteuid())
    assert "private-canary" not in str(error.value)


@pytest.mark.parametrize("kind", ["bundle", "toolchain", "scope", "extra", "duplicate"])
def test_launcher_requires_external_artifact_pins_not_receipt_claims(bundle, kind):
    launcher = module("preflight_launcher")
    record = {
        "version": 1,
        "operator_reference": "synthetic-admin-acceptance",
        "bundle_sha256": "a" * 64,
        "toolchain_sha256": "b" * 64,
        "review_scope_sha256": None,
    }
    if kind in {"bundle", "toolchain"}:
        record[kind + "_sha256"] = "f" * 64
    elif kind == "scope":
        record["review_scope_sha256"] = "f" * 64
    elif kind == "extra":
        record["authorized"] = True
    path = bundle.root / "approval.json"
    path.write_text(json.dumps(record))
    if kind == "duplicate":
        path.write_text(path.read_text()[:-1] + ',"version":1}')
    path.chmod(0o600)
    with pytest.raises(launcher.BootstrapError):
        launcher.check_approval(path, "a" * 64, "b" * 64, None)


def test_bundle_prepare_never_installs_approves_or_changes_existing_output(bundle, monkeypatch):
    package = module("prepare_preflight_bundle")
    source_root = bundle.root / "source"
    source_root.mkdir(mode=0o700)
    source = SourceScenario(source_root)
    for name in CODE:
        source.write(
            "ops/" + name,
            b"PyYAML==6.0.3\n" if name.endswith(".txt") else b"# committed fixture\n",
        )
    source.write("ops/preflight_launcher.py", b"# committed bootstrap\n")
    revision = source.commit()
    source.write("ops/release_preflight.py", b"dirty private-canary\n")
    provider = bundle.root / "provider"
    (provider / "yaml").mkdir(parents=True)
    info = provider / "PyYAML-6.0.3.dist-info"
    (info / "licenses").mkdir(parents=True)
    (info / "METADATA").write_bytes(b"Name: PyYAML\nVersion: 6.0.3\n")
    (info / "licenses/LICENSE").write_bytes(b"Synthetic license fixture\n")
    for name in YAML:
        (provider / "yaml" / name).write_bytes(b"# synthetic yaml\n")
    monkeypatch.setattr(package, "describe_runtime", lambda path: dict(bundle.runtime))
    output = bundle.root / "prepared"
    manifest = package.prepare_bundle(
        source.repo,
        revision,
        source.tools.git,
        Path(sys.executable).resolve(),
        provider,
        output,
        max_output_bytes=131072,
    )
    assert manifest == output / "bundle-manifest.json"
    assert (output / "code/release_preflight.py").read_bytes() == b"# committed fixture\n"
    assert not list(output.rglob("*approval*"))
    before = manifest.read_bytes()
    with pytest.raises(package.PreflightInputError):
        package.prepare_bundle(
            source.repo,
            revision,
            source.tools.git,
            Path(sys.executable).resolve(),
            provider,
            output,
            max_output_bytes=131072,
        )
    assert manifest.read_bytes() == before


def test_missing_bootstrap_never_calls_tools(monkeypatch, capsys):
    adapter = module("release_preflight")

    def forbidden(*args, **kwargs):
        raise AssertionError("unbootstrapped checker attempted a tool")

    monkeypatch.setattr(subprocess, "Popen", forbidden)
    assert adapter.main([]) == 2
    report = json.loads(capsys.readouterr().out)
    assert report["reason_codes"] == ["checker_not_bootstrapped"]
    assert report["candidate"] is None
