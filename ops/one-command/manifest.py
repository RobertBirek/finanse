"""Record only the image IDs that passed acceptance and checksum their archive."""
import hashlib
import json
import subprocess
import sys
from pathlib import Path

revision, schema, output, *tags = sys.argv[1:]
directory = Path(output)
with (directory / "images.tar.gz").open("rb") as archive:
    digest = hashlib.file_digest(archive, "sha256").hexdigest()
images = {}
for service, tag in zip(("backend", "worker", "frontend"), tags, strict=True):
    image_id = subprocess.check_output(
        ["docker", "image", "inspect", "--format", "{{.Id}}", tag], text=True
    ).strip()
    images[service] = {"tag": tag, "id": image_id}
(directory / "manifest.json").write_text(
    json.dumps({"version": 1, "revision": revision, "schema": schema,
                "archive_sha256": digest, "images": images}, sort_keys=True) + "\n"
)
