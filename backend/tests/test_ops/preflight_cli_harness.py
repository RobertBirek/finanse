"""Test-only cold adapter entry with a synthetic already-verified bootstrap.

Not shipped in tooling bundles and not a production CLI/permission bypass.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

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
