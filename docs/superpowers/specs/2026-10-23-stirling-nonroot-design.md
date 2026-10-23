# Stirling non-root/read-only — staging design

## Intent and scope

Unblock the document-safety release without removing read-only, non-root,
cap-drop, no-new-privileges or resource limits. User approved preparing a
compatible runtime and testing upload permissions on a copy, followed by OCR
staging and independent review. This work does not apply production ACLs,
change production volumes, migrate PostgreSQL or deploy a new revision.

## Evidence

- Base image: `frooodle/s-pdf@sha256:3b3670fce70b396ec56ba380a3cc7858e0abf83fe13f31c88f7737847763a396`.
- Its `/scripts/init-without-ocr.sh` SHA-256 is
  `63361a4e8d4452830eeffe1e557c3a5927105ce90edcb1c95bc0e555595e8ce9`.
- Startup always refreshes diagnostics symlinks in `/usr/local/bin`; even
  precreating them does not prevent `ln -sf` from failing on read-only rootfs.
- Vendor UID/GID is `1001:1001`. Keep `tini -- /scripts/init.sh`, JVM options,
  Xvfb/unoserver startup, watchdog and SIGTERM handling.
- Base tessdata includes `eng`, not `pol`. Runtime copying from legacy
  `/usr/share/tessdata` fails silently with read-only system tessdata.
- Upload storage contains root-owned 0600 originals and 0755 directories.
  The application opens `.backup.lock` in `a+b`; backup uses the same inode.

## Chosen approach (proposed implementation decisions)

1. Derive an image from the exact base digest. Verify the vendor script hash
   before a contextual, single-occurrence patch removes both alias-refresh
   blocks and replaces root-oriented permission repair with strict validation.
   User explicitly approved this extension after actual permission drift.
   Create aliases during build. Never delete lines by number.
2. Bake Polish tessdata into the system tessdata path, owned root and read-only.
   Resolve an official `tesseract-ocr/tessdata_fast` immutable commit, record
   source/license and SHA-256, and validate bytes before COPY. No mutable URL
   in the Docker build and no download during startup. Keep base English model.
   Resolved input: commit `87416418657359cb625c412a48b6e1d6d41c29bd`,
   `pol.traineddata` (4,765,518 bytes), SHA-256
   `c4476cdbc0e33d898d32345122b7be1cbf85ace15f920f06c7714756e1ef79b2`.
   Download only from that commit under official `tesseract-ocr/tessdata_fast`;
   cache at `/tmp/opencode/stirling-artifacts/<sha256>/pol.traineddata`.
   A separate preparation step verifies size/hash and supplies a minimal private
   build context. A missing artifact fails build; Dockerfile never downloads it.
   Carry upstream license/notice from the same commit, outside application data.
3. Run UID/GID 1001, `HOME=/tmp/stirling-home`, AOT disabled; retain current
   /tmp noexec/nosuid tmpfs and limits. Provide writable /configs and /logs on
   staging-only owned volumes. Do not expose production networks or mounts.
   Pipeline initial setup unconditionally writes defaultWebUIConfigs even when
   pipeline features are unused (InitialSetup.init -> GeneralUtils.extractPipeline).
   Add a bounded 16 MiB noexec/nosuid tmpfs at `/pipeline`, UID/GID 1001,
   mode 0700; it contains no production pipeline state. The former assumption
   that pipeline was best-effort applies only to shell mkdir, not Java startup.
   Optional storage features remain disabled; if OCR needs further
   writable paths, stop and amend the documented allowlist with evidence.
4. For uploads, evaluate narrowly scoped POSIX ACLs on a COPY only: app UID
   10001 gets rwx on directories, read on existing regular originals and rw on
   `.backup.lock`. No world permissions, owner changes or recursive chown.
   Both backend and worker use UID 10001; new 0600 files remain readable to both.
   Owner-approved policy: NO default ACLs. Only the backend
   creates new originals; worker reads, root backup reads/locks. An importer or
   restore writer must not resume non-root consumers before ACL reapplication.
   Use synthetic files with production-like modes for automated tests; do not
   print document contents or paths from any real copy.
5. ACL application is a separate future operator action: exact-root validation,
   symlink/special-file refusal, ACL snapshot/rollback, quiesced writers and hash
   verification are mandatory. Existing backup tar does not preserve ACLs;
   document reapplication after restore and verify it on isolated restored data.
   No production ACL application is authorized by this staging plan.
6. Build a fresh backend runtime using actual current requirements, then verify
   imports and parser execution under UID 10001/read-only. Do not label the old
   production runtime as compatible with new dependencies.

## Builder-check resolutions

- Leave `ops/document-hardening.compose.yaml` unchanged in this follow-up.
  Use only `ops/stirling/staging.compose.yaml`; production integration is a
  separate reviewed revision/action, not implicit in passing staging.
- Patch anchors are the exact complete `if` blocks starting with
  `if [ -x /scripts/stirling-diagnostics.sh ]; then` and
  `if [ -x /scripts/aot-diagnostics.sh ] && [ "${STIRLING_AOT_ENABLE:-false}" = "true" ]; then`.
  Store exact block literals from the hash-verified script and replace each once
  with a comment saying aliases are created at build time. Any mismatch fails.
  Verified base includes Python 3.12.3; run `python3 patch_init.py` during build,
  remove patch helper afterward, add no runtime dependencies.
- Permission repair in the main init and temp setup in bootstrap are replaced
  under exact hash/whole-block guards; bootstrap `/scripts/init.sh` SHA-256:
  `4e6ef88d9cf4730d699982f9fa8db08561b1a8b340ad443c1cb00703935de84a`.
  Main init runs `python3 /scripts/validate_runtime_paths.py` under umask077.
  Runtime must be UID:GID1001:1001, HOME=/tmp/stirling-home; prepared /configs,
  /logs and /pipeline must be directories owned by that UID/GID with mode0700.
  Validator probes writes without permission repair and creates only private
  home/temp/cache/heap-dump subdirectories under allowed roots. Wrong type,
  symlink, ownership, mode or access aborts startup. Other startup logic remains.
- ACL snapshots are private operator artifacts, never Git/application records:
  create a root-owned 0700 staging metadata directory and 0600 manifest.
  From the validated staging root run `getfacl -R -p -n .` into `before.acl`;
  this preserves numeric ownership, access/default ACLs, masks and special bits.
  Validate every `# file:` entry is `.` or `./<relative path>`, with no `..`,
  absolute paths, newline names, symlinks, special files or paths outside root.
  Save relative inventory, lstat owner/mode/inode and file hashes separately.
  Restore only inside the same validated root with `setfacl --restore=before.acl`.
  Do not persist snapshot output or filenames in public logs.
- Quiesce all staging writers before ACL capture/application/rollback. Compare
  inventory before rollback; additions/deletions/replacements cause an abort,
  not automatic deletion or guessed ACLs for new files. Test rollback on an
  unchanged fixture separately from creation tests. Assert owner/mode/ACL equality.
- Lock participants: backend UID 10001 uses Python flock LOCK_EX on `a+b`;
  root backup runs `flock "$UPLOAD_DIR/.backup.lock" tar ...`. Worker does not
  open this lock. Neither normal writer replaces its inode. Restore/GC are
  maintenance operations requiring stopped writers and post-restore acceptance.
  Compare lock inode during contention tests; ACL operations must not replace it.
- No default ACLs means archive restore must first be demonstrated to fail for
  UID 10001 on root-owned 0600 files. Then apply named ACLs, assert intended mask,
  verify byte hashes/ownership and prove reads/writes/lock sharing succeed.
- Writable allowlist: `/tmp` (including HOME), `/configs`, `/logs`, and the
  bounded 16 MiB `/pipeline` tmpfs justified by actual Java startup failure.
  Inspect actual mounts/security flags and health/OCR/shutdown logs; unexpected
  permission errors, failed OCR, or hidden degradation of required components
  fail staging. Optional disabled-feature warnings must be explicitly attributed
  to upstream code, recorded and reviewed, never automatically ignored.
  `docker diff` detects rootfs changes, not writes within allowed mounts; it is
  supplementary evidence, not a complete syscall audit. Any additional writable
  path requires a plan amendment and review before another acceptance run.

## Acceptance

- Actual derived image starts under hardening; pol+eng listed; PDF, PNG and JPEG
  with rendered text traverse conversion/OCR/text extraction with recognizable
  Polish/English output (not blank PDFs or skip-text-only false positives).
- Responses support identity encoding; original input hashes remain unchanged.
- Container image ID, non-root/read-only/caps/limits/mounts are recorded;
  no unexplained rootfs changes or privileged initialization at runtime.
- SIGTERM cleanly stops within 45 seconds; no OOM/PID exhaustion in representative
  fixtures. Tests do not imply worst-case production capacity certification.
- Upload ACL test proves old 0600 reads, new atomic writes, duplicate integrity,
  backup lock contention, rejection of symlinks and ACL restore/reapplication.
- Independent review, full project gate and explicit new-release approval precede
  any production rollout. Preserve existing runtime/metadata and rollback images.
