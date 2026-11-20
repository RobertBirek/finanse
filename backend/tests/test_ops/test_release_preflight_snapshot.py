"""Approved bytes must remain the only configuration consumed by a renderer."""

import hashlib
import json
import os
import sys
from contextlib import nullcontext
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


def test_pinned_graph_captures_shared_dependency_once(inputs):
    snapshot = module("release_preflight_snapshot")
    dependency = inputs.root / "shared.yaml"
    dependency.write_text("services:\n  base:\n    image: synthetic:base\n")
    inputs.base.write_text(
        "services:\n"
        f"  backend:\n    extends: {{file: {dependency}, service: base}}\n"
        f"  auxiliary:\n    extends: {{file: {dependency}, service: base}}\n"
    )
    records = [
        {"path": str(path), "sha256": hashlib.sha256(path.read_bytes()).hexdigest()}
        for path in (inputs.base, inputs.override, dependency)
    ]
    assert hasattr(snapshot, "capture_compose_graph")
    captured = snapshot.capture_compose_graph(
        records[:2], records[2:], approved_env=inputs.env, limits=inputs.limits
    )
    assert [item.path for item, _ in captured] == [inputs.base, inputs.override, dependency]
    assert captured[-1][1] == dependency.read_bytes()


@pytest.mark.parametrize("drift", [None, "original", "copy", "extra-dir", "unlink"])
def test_isolated_tree_has_only_approved_files(inputs, monkeypatch, drift):
    snapshot = module("release_preflight_snapshot")
    trust = module("release_preflight_trust")
    binary = inputs.root / "synthetic-compose"
    binary.write_bytes(b"synthetic executable fixture")
    binary.chmod(0o555)
    inputs.inventory.update(version=2, compose_dependencies=[])
    inputs.path.write_text(json.dumps(inputs.inventory))
    inventory_pin = replace(
        inputs.inventory_pin, sha256=hashlib.sha256(inputs.path.read_bytes()).hexdigest()
    )
    binary_pin = trust.FilePin(
        binary, hashlib.sha256(binary.read_bytes()).hexdigest(), 0o555, os.geteuid()
    )
    assert hasattr(snapshot, "capture_isolated_inputs")
    frozen = snapshot.capture_isolated_inputs(
        inputs.inventory,
        inventory_pin=inventory_pin,
        active_pin=inputs.active_pin,
        compose_pin=binary_pin,
        scratch=inputs.scratch,
        limits=inputs.limits,
    )
    copy = frozen.root / inputs.base.relative_to("/")
    with (
        (
            pytest.raises(
                snapshot.PreflightInputError, match="snapshot_.*_failed|snapshot_input_changed"
            )
            if drift
            else nullcontext()
        ),
        frozen,
    ):
        assert frozen.compose_files == (inputs.base, inputs.override)
        assert frozen.env_file == inputs.env
        assert {
            file.relative_to(frozen.root) for file in frozen.root.rglob("*") if file.is_file()
        } == {
            Path("bin/compose"),
            *(path.relative_to("/") for path in (inputs.base, inputs.override, inputs.env)),
        }
        assert copy.read_bytes() == inputs.base.read_bytes()
        assert copy.stat().st_mode & 0o777 == 0o444
        frozen.verify_originals()
        if drift in {"original", "copy"}:
            path = inputs.base if drift == "original" else copy
            replacement = path.with_suffix(".replacement")
            replacement.write_bytes(path.read_bytes())
            replacement.chmod(path.stat().st_mode & 0o777)
            replacement.replace(path)
            with pytest.raises(snapshot.PreflightInputError, match="snapshot_input_changed"):
                frozen.verify_originals()
        elif drift == "extra-dir":
            (frozen.root / "unexpected").mkdir()
        elif drift == "unlink":
            unlink = Path.unlink

            def refuse(path, *args, **kwargs):
                if path == copy:
                    raise PermissionError("synthetic cleanup failure")
                return unlink(path, *args, **kwargs)

            monkeypatch.setattr(Path, "unlink", refuse)
    if drift == "extra-dir":
        assert (frozen.root / "unexpected").is_dir()
    elif drift in {"copy", "unlink"}:
        assert copy.is_file()
    else:
        assert not list(inputs.scratch.iterdir())


def test_pinned_graph_rejects_symlink_ancestor(inputs):
    snapshot = module("release_preflight_snapshot")
    actual = inputs.root / "actual"
    actual.mkdir()
    source = actual / "dependency.yaml"
    source.write_text("services:\n  base:\n    image: synthetic:base\n")
    alias = inputs.root / "alias"
    alias.symlink_to(actual, target_is_directory=True)
    target = alias / source.name
    inputs.base.write_text(
        f"services:\n  backend:\n    extends: {{file: {target}, service: base}}\n"
    )
    roots = [
        {"path": str(path), "sha256": hashlib.sha256(path.read_bytes()).hexdigest()}
        for path in (inputs.base, inputs.override)
    ]
    with pytest.raises(snapshot.PreflightInputError):
        snapshot.capture_compose_graph(
            roots,
            [{"path": str(target), "sha256": hashlib.sha256(source.read_bytes()).hexdigest()}],
            approved_env=inputs.env,
            limits=inputs.limits,
        )


@pytest.mark.parametrize(
    ("case", "reason"),
    [
        ("unpinned", "compose_dependency_unapproved"),
        ("missing-service", "compose_dependency_service_missing"),
        ("cycle", "compose_dependency_cycle"),
        ("unused", "compose_dependency_unused"),
        ("alias", "unsupported_compose_input"),
        ("merge", "unsupported_compose_input"),
        ("include", "unsupported_compose_input"),
    ],
)
def test_pinned_graph_rejects_invalid_dependencies(inputs, monkeypatch, case, reason):
    snapshot = module("release_preflight_snapshot")
    dependency = inputs.root / "shared.yaml"
    declaration = f"extends: {{file: {dependency}, service: base}}"
    inputs.base.write_text(f"services:\n  auxiliary:\n    {declaration}\n")
    body = "    image: synthetic:base\n"
    if case == "cycle":
        inputs.override.write_text(f"services:\n  backend:\n    {declaration}\n")
        body = f"    extends: {{file: {inputs.override}, service: backend}}\n"
    if case == "alias":
        inputs.base.write_text(
            f"x-shared: &shared\n  {declaration}\nservices:\n  auxiliary: *shared\n"
        )
    if case == "merge":
        inputs.base.write_text(
            f"x-shared: &shared\n  {declaration}\nservices:\n  auxiliary:\n    <<: *shared\n"
        )
    if case == "include":
        dependency.write_text("include: other.yaml\n")
    if case == "unused":
        inputs.base.write_text("services:\n  auxiliary:\n    image: synthetic:base\n")
    service = "wrong" if case == "missing-service" else "base"
    if case != "include":
        dependency.write_text(f"services:\n  {service}:\n{body}")
    records = [
        {"path": str(path), "sha256": hashlib.sha256(path.read_bytes()).hexdigest()}
        for path in (inputs.base, inputs.override, dependency)
    ]
    if case == "unpinned":
        capture = snapshot._capture

        def exclude_unapproved(path, *args, **kwargs):
            assert path != dependency
            return capture(path, *args, **kwargs)

        monkeypatch.setattr(snapshot, "_capture", exclude_unapproved)
    assert hasattr(snapshot, "capture_compose_graph")
    with pytest.raises(snapshot.PreflightInputError, match=f"^{reason}$"):
        snapshot.capture_compose_graph(
            records[:2],
            [] if case == "unpinned" else records[2:],
            approved_env=inputs.env,
            limits=inputs.limits,
        )


@pytest.mark.parametrize("edges", [32, 33])
def test_pinned_graph_longest_shared_path(inputs, edges):
    snapshot = module("release_preflight_snapshot")
    dep = inputs.root / "chain.yaml"
    lines = ["services:", f"  shortcut:\n    extends: {{file: {dep}, service: leaf}}"]
    lines += [f"  long:\n    extends: {{file: {dep}, service: node0}}"]
    inputs.base.write_text("\n".join(lines) + "\n")
    dep.write_text(
        "services:\n  leaf:\n    image: synthetic:base\n"
        + "".join(
            f"  node{i}:\n    extends: {{file: {dep}, service: {target}}}\n"
            for i in range(edges - 1)
            for target in [f"node{i + 1}" if i < edges - 2 else "leaf"]
        )
    )
    records = [
        {"path": str(path), "sha256": hashlib.sha256(path.read_bytes()).hexdigest()}
        for path in (inputs.base, inputs.override, dep)
    ]
    if edges == 32:
        assert (
            len(
                snapshot.capture_compose_graph(
                    records[:2], records[2:], approved_env=inputs.env, limits=inputs.limits
                )
            )
            == 3
        )
    else:
        with pytest.raises(snapshot.PreflightInputError, match="^compose_dependency_limit$"):
            snapshot.capture_compose_graph(
                records[:2], records[2:], approved_env=inputs.env, limits=inputs.limits
            )


@pytest.mark.parametrize("count", [32, 33])
def test_compose_graph_dependency_file_limit(inputs, count):
    snapshot = module("release_preflight_snapshot")
    dependencies = [inputs.root / f"dependency-{index}.yaml" for index in range(count)]
    inputs.base.write_text(
        "services:\n"
        + "".join(
            f"  app{index}:\n    extends: {{file: {path}, service: base}}\n"
            for index, path in enumerate(dependencies)
        )
    )
    for path in dependencies:
        path.write_text("services:\n  base:\n    image: synthetic:base\n")
    records = [
        {"path": str(path), "sha256": hashlib.sha256(path.read_bytes()).hexdigest()}
        for path in (inputs.base, inputs.override, *dependencies)
    ]
    if count == 32:
        assert (
            len(
                snapshot.capture_compose_graph(
                    records[:2], records[2:], approved_env=inputs.env, limits=inputs.limits
                )
            )
            == 34
        )
    else:
        with pytest.raises(snapshot.PreflightInputError, match="^compose_dependency_limit$"):
            snapshot.capture_compose_graph(
                records[:2], records[2:], approved_env=inputs.env, limits=inputs.limits
            )


@pytest.mark.parametrize("count", [256, 257])
def test_compose_graph_reference_limit(inputs, count):
    snapshot = module("release_preflight_snapshot")
    dep = inputs.root / "shared.yaml"
    dep.write_text("services:\n  base:\n    image: synthetic:base\n")
    inputs.base.write_text(
        "services:\n"
        + "".join(
            f"  app{index}:\n    extends: {{file: {dep}, service: base}}\n"
            for index in range(count)
        )
    )
    records = [
        {"path": str(path), "sha256": hashlib.sha256(path.read_bytes()).hexdigest()}
        for path in (inputs.base, inputs.override, dep)
    ]
    limits = replace(inputs.limits, max_yaml_nodes=8192)
    if count == 256:
        assert (
            len(
                snapshot.capture_compose_graph(
                    records[:2], records[2:], approved_env=inputs.env, limits=limits
                )
            )
            == 3
        )
    else:
        with pytest.raises(snapshot.PreflightInputError, match="^compose_dependency_limit$"):
            snapshot.capture_compose_graph(
                records[:2], records[2:], approved_env=inputs.env, limits=limits
            )


@pytest.mark.parametrize("extra", [0, 1])
def test_compose_graph_total_bytes_limit(inputs, extra, monkeypatch):
    snapshot = module("release_preflight_snapshot")
    # Exercise real pinned reads and the aggregate quota independently of YAML
    # parser performance on a large synthetic comment.
    inspect = snapshot._inspect_compose
    monkeypatch.setattr(
        snapshot, "_inspect_compose", lambda raw, **kwargs: inspect(raw.split(b"#", 1)[0], **kwargs)
    )
    total = 8 * 1024 * 1024 + extra
    base = inputs.base.read_bytes()
    override = inputs.override.read_bytes()
    inputs.base.write_bytes(base + b"#" + b" " * (total - len(override) - len(base) - 2) + b"\n")
    roots = [
        {"path": str(path), "sha256": hashlib.sha256(path.read_bytes()).hexdigest()}
        for path in (inputs.base, inputs.override)
    ]
    limits = replace(inputs.limits, max_file_bytes=total)
    if extra == 0:
        assert (
            len(snapshot.capture_compose_graph(roots, [], approved_env=inputs.env, limits=limits))
            == 2
        )
    else:
        with pytest.raises(snapshot.PreflightInputError, match="^compose_dependency_limit$"):
            snapshot.capture_compose_graph(roots, [], approved_env=inputs.env, limits=limits)


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
