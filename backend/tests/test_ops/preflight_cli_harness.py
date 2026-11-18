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
    context = BootstrapContext(
        bundle_sha256="e" * 64,
        toolchain_sha256="f" * 64,
        toolchain=tools,
        review_scope_sha256=raw.get("review_scope_sha256"),
        runtime_root=OPS,
    )
    return release_preflight.main(sys.argv[2:], bootstrap=context)


if __name__ == "__main__":
    raise SystemExit(main())
