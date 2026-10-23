"""Build-time-only patch for one audited upstream image; fail closed on drift."""

import hashlib
import sys
from pathlib import Path

EXPECTED_SHA256 = "63361a4e8d4452830eeffe1e557c3a5927105ce90edcb1c95bc0e555595e8ce9"
BOOTSTRAP_SHA256 = "4e6ef88d9cf4730d699982f9fa8db08561b1a8b340ad443c1cb00703935de84a"
TEMP_BLOCK = b"""# === Temp dir ===
# Ensure the temporary directory exists and has proper permissions.
mkdir -p /tmp/stirling-pdf
chown -R stirlingpdfuser:stirlingpdfgroup /tmp/stirling-pdf || true
chmod -R 755 /tmp/stirling-pdf || true
"""
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
PERMISSIONS_BLOCK = b"""# ---------- Permissions ----------
# Ensure required directories exist and set correct permissions.
log "Setting permissions..."
mkdir -p /tmp/stirling-pdf /tmp/stirling-pdf/heap_dumps /logs /configs /configs/heap_dumps /configs/cache /customFiles /pipeline /storage || true
CHOWN_PATHS=("$HOME" "/logs" "/scripts" "/configs" "/customFiles" "/pipeline" "/storage" "/tmp/stirling-pdf" "/app.jar")
[ -d /usr/share/fonts/truetype ] && CHOWN_PATHS+=("/usr/share/fonts/truetype")
CHOWN_OK=true
for p in "${CHOWN_PATHS[@]}"; do
  if [ -e "$p" ]; then
    chown -R "stirlingpdfuser:stirlingpdfgroup" "$p" 2>/dev/null || CHOWN_OK=false
    chmod -R 755 "$p" 2>/dev/null || true
  fi
done

# Verify write access to critical directories; repair if chown failed on bind mounts
CRITICAL_DIRS=("/configs" "/logs" "/customFiles" "/pipeline" "/storage")
for dir in "${CRITICAL_DIRS[@]}"; do
  if [ -d "$dir" ]; then
    # Test write access as the runtime user
    if ! run_as_runtime_user test -w "$dir" 2>/dev/null; then
      log "WARNING: ${RUNTIME_USER} cannot write to $dir - attempting to fix permissions"
      # Try adding group-write and world-write as fallbacks
      chmod -R o+rwX "$dir" 2>/dev/null \\
        || chmod -R a+rwX "$dir" 2>/dev/null \\
        || log "ERROR: Could not grant ${RUNTIME_USER} write access to $dir. Check your volume mount permissions (e.g. set PUID/PGID or fix host directory ownership)."
    fi
  fi
done
"""
PERMISSIONS_REPLACEMENT = b"""# ---------- Validated non-root writable paths ----------
umask 077
python3 /scripts/validate_runtime_paths.py
"""


def patch_bootstrap(source: bytes) -> bytes:
    if hashlib.sha256(source).hexdigest() != BOOTSTRAP_SHA256:
        raise ValueError("Unexpected vendor bootstrap checksum")
    if source.count(TEMP_BLOCK) != 1:
        raise ValueError("Expected temp block exactly once")
    return source.replace(TEMP_BLOCK, b"# Temp paths validated by main init.\n", 1)


def patch_init(source: bytes) -> bytes:
    if hashlib.sha256(source).hexdigest() != EXPECTED_SHA256:
        raise ValueError("Unexpected vendor init checksum")
    for block in (DIAGNOSTIC_BLOCK, AOT_BLOCK):
        if source.count(block) != 1:
            raise ValueError("Expected alias block exactly once")
        source = source.replace(block, REPLACEMENT, 1)
    if source.count(PERMISSIONS_BLOCK) != 1:
        raise ValueError("Expected permissions block exactly once")
    source = source.replace(PERMISSIONS_BLOCK, PERMISSIONS_REPLACEMENT, 1)
    return source


if __name__ == "__main__":
    path = Path(sys.argv[1])
    path.write_bytes(patch_init(path.read_bytes()))
    bootstrap = path.with_name("init.sh")
    bootstrap.write_bytes(patch_bootstrap(bootstrap.read_bytes()))
