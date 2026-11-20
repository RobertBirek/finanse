"""Test-only cold adapter entry with a synthetic already-verified bootstrap.

Not shipped in tooling bundles and not a production CLI/permission bypass.
"""

from __future__ import annotations

import json
import sys
import tempfile
from pathlib import Path
from types import SimpleNamespace

OPS = Path(__file__).resolve().parents[3] / "ops"
sys.path.insert(0, str(OPS))

import release_preflight
import release_preflight_exec as execution
from release_preflight_trust import (
    BootstrapContext,
    FilePin,
    InputLimits,
    PgEndpoint,
    Toolchain,
    verify_pinned_file,
)


def main() -> int:
    raw = json.loads(Path(sys.argv[1]).read_text())
    pins = {
        name: FilePin(Path(value["path"]), value["sha256"], value["mode"], value["uid"])
        for name, value in raw["executables"].items()
    }
    tools = Toolchain(
        **pins, postgres=PgEndpoint(**raw["postgres"]), limits=InputLimits(**raw["limits"])
    )
    original = execution.ReadOnlyRunner

    def fixture_runner(repository: Path, toolchain: Toolchain) -> execution.ReadOnlyRunner:
        return original(
            repository,
            toolchain,
            verifier=lambda pin: verify_pinned_file(pin, owner_uid=pin.uid),
        )

    execution.ReadOnlyRunner = fixture_runner
    if "synthetic_isolated_render" in raw:
        import release_preflight_isolation as isolation
        import release_preflight_snapshot as snapshots

        class FixtureSnapshot(SimpleNamespace):
            def __enter__(self):
                return self

            def __exit__(self, *exc):
                self.directory.cleanup()

            def verify_originals(self):
                pass

        def capture(inventory, *, inventory_pin, active_pin, compose_pin, scratch, limits):
            # The adapter test owns only synthetic files. Real snapshot ownership,
            # cleanup and renderer isolation are tested by the Linux qualification.
            env = Path(inventory["env_file"]["path"])
            records = inventory["compose_files"]
            graph = snapshots.capture_compose_graph(
                records, inventory["compose_dependencies"], approved_env=env, limits=limits
            )
            directory = tempfile.TemporaryDirectory(dir=scratch)
            try:
                root = Path(directory.name)
                for path, content in [(env, env.read_bytes()), *((p.path, b) for p, b in graph)]:
                    dest = root / path.relative_to("/")
                    dest.parent.mkdir(parents=True, exist_ok=True)
                    dest.write_bytes(content)
                files = tuple(Path(record["path"]) for record in records)
                return FixtureSnapshot(
                    directory=directory,
                    root=root,
                    compose_files=files,
                    project_directory=files[0].parent,
                    env_file=env,
                )
            except BaseException:
                directory.cleanup()
                raise

        def render(root: Path, argv: tuple[str, ...], *, max_output_bytes: int) -> str:
            assert root.is_dir() and max_output_bytes > 0
            assert isolation._valid_argv(argv)
            assert (root / argv[5].lstrip("/")).is_file()
            for index in range(7, len(argv) - 3, 2):
                assert (root / argv[index].lstrip("/")).is_file()
            key = "help" if argv[-1] == "--help" else "config"
            result = raw["synthetic_isolated_render"][key]
            if result is None:
                raise isolation.PreflightInputError("renderer_failed")
            return str(result)

        isolation.run_isolated_compose = render
        snapshots.capture_isolated_inputs = capture
        if not raw.get("synthetic_wrong_compose_pin"):
            isolation.ISOLATED_COMPOSE_SHA256 = tools.compose.sha256
    context = BootstrapContext(
        bundle_sha256="e" * 64,
        toolchain_sha256="f" * 64,
        toolchain=tools,
        review_scope_sha256=raw.get("review_scope_sha256"),
        runtime_root=OPS,
        isolated_approval=(
            tuple(raw["synthetic_isolated_approval"])
            if "synthetic_isolated_approval" in raw
            else None
        ),
    )
    return release_preflight.main(sys.argv[2:], bootstrap=context)


if __name__ == "__main__":
    raise SystemExit(main())
