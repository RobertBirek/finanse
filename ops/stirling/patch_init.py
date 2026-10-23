"""Build-time-only patch for one audited upstream image; fail closed on drift."""

import hashlib
import sys
from pathlib import Path

EXPECTED_SHA256 = "63361a4e8d4452830eeffe1e557c3a5927105ce90edcb1c95bc0e555595e8ce9"
DIAGNOSTIC_BLOCK = b"""if [ -x /scripts/stirling-diagnostics.sh ]; then
  mkdir -p /usr/local/bin
  ln -sf /scripts/stirling-diagnostics.sh /usr/local/bin/diagnostics
  ln -sf /scripts/stirling-diagnostics.sh /usr/local/bin/stirling-diagnostics
  ln -sf /scripts/stirling-diagnostics.sh /usr/local/bin/diag
  ln -sf /scripts/stirling-diagnostics.sh /usr/local/bin/debug
  ln -sf /scripts/stirling-diagnostics.sh /usr/local/bin/diagnostic
fi
"""
AOT_BLOCK = b"""if [ -x /scripts/aot-diagnostics.sh ] && [ "${STIRLING_AOT_ENABLE:-false}" = "true" ]; then
  mkdir -p /usr/local/bin
  ln -sf /scripts/aot-diagnostics.sh /usr/local/bin/aot-diag
  ln -sf /scripts/aot-diagnostics.sh /usr/local/bin/aot-diagnostics
fi
"""
REPLACEMENT = b"# Diagnostics aliases are created at image build time.\n"


def patch_init(source: bytes) -> bytes:
    if hashlib.sha256(source).hexdigest() != EXPECTED_SHA256:
        raise ValueError("Unexpected vendor init checksum")
    for block in (DIAGNOSTIC_BLOCK, AOT_BLOCK):
        if source.count(block) != 1:
            raise ValueError("Expected alias block exactly once")
        source = source.replace(block, REPLACEMENT, 1)
    return source


if __name__ == "__main__":
    path = Path(sys.argv[1])
    path.write_bytes(patch_init(path.read_bytes()))
