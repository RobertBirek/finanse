"""Approved bytes must remain the only configuration consumed by a renderer."""

import hashlib
import json
import os
import sys
from dataclasses import replace
from pathlib import Path

import pytest
import yaml

from tests.test_ops.preflight_fixtures import PinnedScenario, module


class Inputs:
    def __init__(self, root: Path):
        trust = module("release_preflight_trust")
        root.chmod(0o700)
        self.root = root
        self.env = root / ".env"
        self.env.write_text("SYNTHETIC_SECRET=private-canary\n")
        self.base = root / "compose.yaml"
        self.base.write_text(
            "services:\n  backend:\n    image: local/synthetic:old\n"
            "    env_file: .env\n    volumes: [./uploads:/data]\n"
        )
        self.override = root / "compose.release.yaml"
        self.override.write_text("services:\n  backend:\n    image: local/synthetic:new\n")
        self.active = root / "active.json"
        self.active.write_text("{}")
        self.inventory = {
            "active_release_sha256": hashlib.sha256(self.active.read_bytes()).hexdigest(),
            "compose_files": [
                {"path": str(p), "sha256": hashlib.sha256(p.read_bytes()).hexdigest()}
                for p in (self.base, self.override)
            ],
            "env_file": {
                "path": str(self.env),
                "sha256": hashlib.sha256(self.env.read_bytes()).hexdigest(),
            },
        }
        self.path = root / "inventory.json"
        self.path.write_text(json.dumps(self.inventory))
        for path in (self.path, self.env, self.base, self.override, self.active):
            path.chmod(0o600)
        self.inventory_pin = trust.FilePin(
            self.path, hashlib.sha256(self.path.read_bytes()).hexdigest(), 0o600, os.geteuid()
        )
        self.active_pin = trust.FilePin(
            self.active, hashlib.sha256(self.active.read_bytes()).hexdigest(), 0o600, os.geteuid()
        )
        self.scratch = root / "scratch"
        self.scratch.mkdir(mode=0o700)
        self.limits = trust.InputLimits(65536, 2048, 32, 131072)

    def capture(self):
        return module("release_preflight_snapshot").capture_inputs(
            self.inventory,
            inventory_pin=self.inventory_pin,
            active_pin=self.active_pin,
            scratch=self.scratch,
            limits=self.limits,
        )


@pytest.fixture
def inputs(tmp_path):
    return Inputs(tmp_path)


def test_mutation_after_hash_never_changes_consumed_bytes(inputs):
    snapshot = module("release_preflight_snapshot")
    tool_root = inputs.root / "tools"
    tool_root.mkdir(mode=0o700)
    tools = PinnedScenario(tool_root)
    with pytest.raises(snapshot.PreflightInputError) as error, inputs.capture() as frozen:
        # A real synthetic consumer opens the paths the runner actually passes.
        fake = tools.tools.compose.path
        fake.write_text(
            f"#!{sys.executable}\n"
            "import json,sys\nfrom pathlib import Path\n"
            "args=sys.argv[1:]\n"
            "env=Path(args[args.index('--env-file')+1]).read_text()\n"
            "files=[Path(args[i+1]).read_text() for i,a in enumerate(args) if a=='-f']\n"
            "print(json.dumps({'env':env,'files':files,'directory':args[args.index('--project-directory')+1]}))\n"
        )
        tools.tools = replace(
            tools.tools,
            compose=replace(
                tools.tools.compose, sha256=hashlib.sha256(fake.read_bytes()).hexdigest()
            ),
        )
        runner = tools.runner()
        runner.bind(
            frozen.compose_files,
            frozen.env_file,
            frozen.project_directory,
            "synthetic",
            tools.inventory,
        )
        inputs.env.write_text("SYNTHETIC_SECRET=changed-after-hash\n")
        inputs.base.write_text("services: {}\n")
        rendered = json.loads(runner.run(runner.compose_prefix + ["config", "--format", "json"]))
        assert rendered["env"] == "SYNTHETIC_SECRET=private-canary\n"
        assert "local/synthetic:old" in rendered["files"][0]
        assert rendered["directory"] == str(inputs.root)
        frozen.verify_originals()
    assert "private-canary" not in str(error.value)
    assert list(inputs.scratch.iterdir()) == []


def test_compose_tags_aliases_and_relative_paths_keep_meaning(inputs):
    snapshot = module("release_preflight_snapshot")
    raw = (
        b"x-env: &e .env\n"
        b"x-common: &common {env_file: *e, image: local/synthetic:base}\n"
        b"services:\n  backend:\n    <<: *common\n    volumes: !override [./uploads:/data]\n"
        b"  worker:\n    env_file: *e\n    volumes: !reset []\n"
    )
    refs = snapshot.validate_compose_nodes(
        raw,
        source=inputs.base,
        project_directory=inputs.root,
        approved_env=inputs.env,
        limits=inputs.limits,
    )
    assert len(refs) == 1
    text = raw.decode()
    ref = refs[0]
    transformed = (
        text[: ref.start] + json.dumps(str(inputs.scratch / "frozen.env")) + text[ref.end :]
    )
    node = yaml.compose(transformed, Loader=yaml.SafeLoader)
    fields = {key.value: value for key, value in node.value}
    assert fields["x-env"].value == str(inputs.scratch / "frozen.env")
    services = {key.value: value for key, value in fields["services"].value}
    backend = {key.value: value for key, value in services["backend"].value}
    worker = {key.value: value for key, value in services["worker"].value}
    assert backend["volumes"].tag == "!override"
    assert backend["volumes"].value[0].value == "./uploads:/data"
    assert worker["volumes"].tag == "!reset"
    assert worker["env_file"] is fields["x-env"]


def test_merge_sequence_first_source_and_explicit_value_take_precedence(inputs):
    snapshot = module("release_preflight_snapshot")
    raw = (
        b"x-first: &a {env_file: .env}\n"
        b"x-second: &b {env_file: other.env}\n"
        b"services:\n  backend: {<<: [*a, *b]}\n"
        b"  worker: {<<: *b, env_file: .env}\n"
    )
    refs = snapshot.validate_compose_nodes(
        raw,
        source=inputs.base,
        project_directory=inputs.root,
        approved_env=inputs.env,
        limits=inputs.limits,
    )
    assert len(refs) == 2


def test_yaml_constructor_never_executes(inputs):
    snapshot = module("release_preflight_snapshot")
    marker = inputs.root / "constructor-executed"
    raw = (
        "services: {backend: {image: !!python/object/apply:os.system "
        + json.dumps([f"touch {marker}"])
        + "}}"
    ).encode()
    with pytest.raises(snapshot.PreflightInputError):
        snapshot.validate_compose_nodes(
            raw,
            source=inputs.base,
            project_directory=inputs.root,
            approved_env=inputs.env,
            limits=inputs.limits,
        )
    assert not marker.exists()


@pytest.mark.parametrize(
    "raw",
    [
        "include: other.yaml\nservices: {}",
        "services: {backend: {extends: {file: other.yaml, service: backend}}}",
        "services: {backend: {label_file: other.env}}",
        "services: {}\nsecrets: {password: {file: other.env}}",
        "services: {backend: {credential_spec: {file: other.json}}}",
        "services: {backend: {provider: {type: external}}}",
        "services: {backend: {build: {context: ., ssh: [default]}}}",
        "services: {backend: {new_future_file_mechanism: other.env}}",
    ],
)
def test_external_include_extends_label_file_and_secret_file_block_before_render(inputs, raw):
    snapshot = module("release_preflight_snapshot")
    with pytest.raises(snapshot.PreflightInputError):
        snapshot.validate_compose_nodes(
            raw.encode(),
            source=inputs.base,
            project_directory=inputs.root,
            approved_env=inputs.env,
            limits=inputs.limits,
        )
    assert list(inputs.scratch.iterdir()) == []


@pytest.mark.parametrize(
    "raw",
    [
        "x-cycle: &a [*a]\nservices: {}",
        "services: {backend: {image: one, image: two}}",
        "services: {backend: {env_file: '${ENV_FILE}'}}",
        "services: {backend: {env_file: other.env}}",
        "services: {backend: {env_file: {path: .env}}}",
        "services: {backend: {image: !!python/object/apply:os.system ['private-canary']}}",
    ],
)
def test_cycle_duplicate_key_and_dynamic_env_file_block(inputs, raw):
    snapshot = module("release_preflight_snapshot")
    with pytest.raises(snapshot.PreflightInputError) as error:
        snapshot.validate_compose_nodes(
            raw.encode(),
            source=inputs.base,
            project_directory=inputs.root,
            approved_env=inputs.env,
            limits=inputs.limits,
        )
    assert "private-canary" not in str(error.value)


@pytest.mark.parametrize("limit", ["max_file_bytes", "max_yaml_nodes", "max_yaml_depth"])
def test_parser_limits_block_without_echoing_document(inputs, limit):
    snapshot = module("release_preflight_snapshot")
    with pytest.raises(snapshot.PreflightInputError):
        snapshot.validate_compose_nodes(
            inputs.base.read_bytes(),
            source=inputs.base,
            project_directory=inputs.root,
            approved_env=inputs.env,
            limits=replace(inputs.limits, **{limit: 1}),
        )


def test_snapshot_cleanup_failure_redacts_and_blocks(inputs, monkeypatch):
    snapshot = module("release_preflight_snapshot")
    original = Path.unlink
    with pytest.raises(snapshot.PreflightInputError) as error, inputs.capture() as frozen:
        private_root = frozen.env_file.parent

        def fail_private(path, *args, **kwargs):
            if path.parent == private_root:
                raise OSError("private-canary")
            return original(path, *args, **kwargs)

        monkeypatch.setattr(Path, "unlink", fail_private)
    assert error.value.code == "snapshot_cleanup_failed"
    assert "private-canary" not in str(error.value)


@pytest.mark.parametrize(
    "kind", ["permissions", "nonempty", "symlink", "changed_inventory", "interpolated_path"]
)
def test_snapshot_refuses_bad_scratch_or_changed_approval(inputs, kind):
    snapshot = module("release_preflight_snapshot")
    if kind == "permissions":
        inputs.scratch.chmod(0o755)
    elif kind == "nonempty":
        (inputs.scratch / "not-ours").write_text("keep")
    elif kind == "symlink":
        link = inputs.root / "scratch-link"
        link.symlink_to(inputs.scratch)
        inputs.scratch = link
    elif kind == "interpolated_path":
        inputs.scratch = inputs.root / "scratch-$HOME"
        inputs.scratch.mkdir(mode=0o700)
    else:
        inputs.path.write_text("{}")
    with pytest.raises(snapshot.PreflightInputError):
        inputs.capture()
    if kind == "nonempty":
        assert (inputs.scratch / "not-ours").read_text() == "keep"


@pytest.mark.parametrize("kind", ["inventory_mode", "active_uid"])
def test_capture_enforces_supplied_filepin_metadata(inputs, kind):
    snapshot = module("release_preflight_snapshot")
    if kind == "inventory_mode":
        inputs.inventory_pin = replace(inputs.inventory_pin, mode=0o400)
    else:
        inputs.active_pin = replace(inputs.active_pin, uid=os.geteuid() + 1)
    with pytest.raises(snapshot.PreflightInputError):
        inputs.capture()


def test_missing_parser_is_controlled_and_redacted(inputs, monkeypatch):
    snapshot = module("release_preflight_snapshot")
    original = snapshot.importlib.import_module

    def unavailable(name, *args, **kwargs):
        if name == "yaml":
            raise ImportError("private-canary")
        return original(name, *args, **kwargs)

    monkeypatch.setattr(snapshot.importlib, "import_module", unavailable)
    with pytest.raises(snapshot.PreflightInputError) as error:
        snapshot.validate_compose_nodes(
            inputs.base.read_bytes(),
            source=inputs.base,
            project_directory=inputs.root,
            approved_env=inputs.env,
            limits=inputs.limits,
        )
    assert "private-canary" not in str(error.value)
