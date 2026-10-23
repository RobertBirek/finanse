# Candidate Stirling runtime — staging only

Base: `frooodle/s-pdf@sha256:3b3670fce70b396ec56ba380a3cc7858e0abf83fe13f31c88f7737847763a396`.
Vendor init hash is checked before removing only alias-refresh blocks; all other
startup and shutdown code remains intact. Inherited entrypoint is `tini --
/scripts/init.sh`. Root is used at build time only; runtime is UID/GID 1001.

Polish model: official `tesseract-ocr/tessdata_fast`, commit
`87416418657359cb625c412a48b6e1d6d41c29bd`, file `pol.traineddata`,
4,765,518 bytes, SHA-256
`c4476cdbc0e33d898d32345122b7be1cbf85ace15f920f06c7714756e1ef79b2`.
Model licensing: upstream Apache-2.0 LICENSE from that same commit.

Prepare a new private build context containing ONLY Dockerfile, patch_init.py,
the checked model and upstream LICENSE named TESSDATA_LICENSE. Download via
`https://raw.githubusercontent.com/tesseract-ocr/tessdata_fast/<commit>/<file>`
in an explicit preparation step, never in Dockerfile or at container startup.
Cache the model at `/tmp/opencode/stirling-artifacts/<sha256>/pol.traineddata`.
Reject a cache miss/mismatch rather than fetching a mutable branch. No production
configs, uploads, environment files or credential material belong in build context.

Build with `docker build --network=none -t local/stirling-pdf:nonroot-staging CONTEXT`.
Record the resulting immutable image ID and pass that to staging. Do not apply
the production hardening overlay until actual OCR and permissions gates pass.
