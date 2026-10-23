# Candidate Stirling runtime — staging only

Base: `frooodle/s-pdf@sha256:3b3670fce70b396ec56ba380a3cc7858e0abf83fe13f31c88f7737847763a396`.
Vendor init hashes are checked before replacing alias-refresh blocks and
root-oriented permission-repair blocks (including bootstrap temp initialization).
Strict UID/GID 1001 and mode0700 validation replaces chmod/chown repair.
JVM, OCR and shutdown code remains intact. Inherited entrypoint is `tini --
/scripts/init.sh`. Root is used at build time only; runtime is UID/GID 1001.

Polish model: official `tesseract-ocr/tessdata_fast`, commit
`87416418657359cb625c412a48b6e1d6d41c29bd`, file `pol.traineddata`,
4,765,518 bytes, SHA-256
`c4476cdbc0e33d898d32345122b7be1cbf85ace15f920f06c7714756e1ef79b2`.
Model licensing: upstream Apache-2.0 LICENSE from that same commit.

Prepare a new private build context containing ONLY Dockerfile, patch_init.py,
validate_runtime_paths.py,
the checked model and upstream LICENSE named TESSDATA_LICENSE. Download via
`https://raw.githubusercontent.com/tesseract-ocr/tessdata_fast/<commit>/<file>`
in an explicit preparation step, never in Dockerfile or at container startup.
Cache the model at `/tmp/opencode/stirling-artifacts/<sha256>/pol.traineddata`.
Reject a cache miss/mismatch rather than fetching a mutable branch. No production
configs, uploads, environment files or credential material belong in build context.

Build with `docker build --network=none -t local/stirling-pdf:nonroot-staging CONTEXT`.
Record the resulting immutable image ID and pass that to staging. Do not apply
the production hardening overlay until actual OCR and permissions gates pass.

Staging has no published ports; the host test client accesses the private IP on
an isolated internal Docker bridge. Set immutable `STIRLING_TEST_IMAGE` and run
`pytest -m proxy tests/test_stirling_staging.py`. Writable paths: /tmp (512 MiB),
/pipeline (16 MiB UID1001 mode0700 tmpfs), and separate UID1001-owned mode0700
staging /configs and /logs. The vendor Java startup always writes default pipeline
configs. Existing internal OCR login-disabled settings are mirrored only inside
this isolated network; never expose this staging service publicly.

## Verified staging artifact (2026-10-23)

- Stirling image ID: `sha256:e0d315bd87b07b0ee411ea4a42a08e52c4a9267de4b69c552718eb400df8a9e5`.
- A4 portrait PNG/JPEG/scanned PDF OCR with pol+eng and identity responses passed;
  includes accented Polish output. Effective PID1/Java identity, private mode0700,
  read-only settings and shutdown verified. /pipeline consumed 16 KiB of 16 MiB.
- This is NOT a production release or worst-case capacity certification.
- Known existing product issue: default img/pdf fillPage stretches wide images
  to portrait A4 and can yield empty OCR with HTTP200. Independent Tesseract
  reproduction confirms distortion; the runtime patch does not fix conversion.
