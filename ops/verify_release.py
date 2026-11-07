#!/usr/bin/env python3
"""Offline built-image import gate; never applies Compose or contacts live services.

Use explicit numeric non-root users from the final rendered deployment config, not
the image's default USER. A successful result proves only the recorded image IDs.
"""

import argparse
import json
import re
import subprocess
from pathlib import Path
from typing import Any
from uuid import uuid4

IMAGE = re.compile(r"[a-z0-9][a-z0-9./_-]*:[a-zA-Z0-9_.-]+")
IMAGE_ID = re.compile(r"sha256:[0-9a-f]{64}")
USER = re.compile(r"[1-9][0-9]*:[1-9][0-9]*")

PROBE = """import importlib,json,os,sys
from pathlib import Path
uid,gid=int(sys.argv[1]),int(sys.argv[2]); name=sys.argv[3]
if os.getuid()!=uid or os.getgid()!=gid or uid==0 or gid==0:
 raise RuntimeError('unexpected probe user')
# Do not inherit image credentials/feature flags or read an application .env.
os.environ.clear()
os.environ.update({
 'ENVIRONMENT':'test',
 'DATABASE_URL':'postgresql+asyncpg://release:synthetic@127.0.0.1:5432/release_test',
 'REDIS_URL':'redis://127.0.0.1:6379/15',
 'SECRET_KEY':'offline-release-probe-synthetic-secret-only',
 'DOCUMENT_VISION_ENABLED':'false',
 'DOCUMENT_RECEIPT_ITEMS_ENABLED':'false',
 'FINANCE_SUGGESTIONS_ENABLED':'false',
})
os.chdir('/')
sys.path.insert(0,'/app')
def walk_error(error): raise error
files_read=0
for directory,dirs,files in os.walk('/app/app',onerror=walk_error):
 for filename in files:
  Path(directory,filename).read_bytes(); files_read+=1
if files_read==0: raise RuntimeError('application source missing')
module=importlib.import_module(name)
getattr(module,'app' if name=='app.main' else 'WorkerSettings')
# Import only: never start ASGI lifespan, an ARQ worker, DB or provider requests.
print(json.dumps({'uid':uid,'gid':gid,'module':name,'files_read':files_read}))
"""


def verify_release(
    release: Path,
    *,
    backend_user: str,
    worker_user: str,
    timeout: int = 60,
) -> dict[str, Any]:
    users = {"backend": backend_user, "worker": worker_user}
    if any(USER.fullmatch(value) is None for value in users.values()):
        raise ValueError("Explicit non-root numeric UID:GID required for each service")
    if timeout <= 0:
        raise ValueError("Probe timeout must be positive")
    metadata = json.loads((release / "release.json").read_text())
    revision = metadata.get("revision", "")
    if not isinstance(revision, str) or re.fullmatch(r"[0-9a-f]{40}", revision) is None:
        raise ValueError("Invalid release revision")
    if any(
        not isinstance(metadata.get(s), str) or IMAGE.fullmatch(metadata[s]) is None
        for s in users
    ):
        raise ValueError("Explicit local image tags required in release metadata")
    images: dict[str, str] = {}
    for service in users:
        rows = json.loads(
            subprocess.run(
                ["docker", "image", "inspect", metadata[service]],
                check=True,
                capture_output=True,
                text=True,
                timeout=timeout,
            ).stdout
        )
        if len(rows) != 1:
            raise ValueError("Expected exactly one local image")
        image = rows[0]
        if (image.get("Config", {}).get("Labels") or {}).get(
            "org.opencontainers.image.revision"
        ) != revision:
            raise ValueError(f"{service} image revision does not match release")
        if IMAGE_ID.fullmatch(image.get("Id", "")) is None:
            raise ValueError(f"{service} invalid local image ID")
        images[service] = image["Id"]
    services: dict[str, Any] = {}
    for service, user in users.items():
        uid, gid = map(int, user.split(":"))
        module = "app.main" if service == "backend" else "app.worker"
        name = "finanse-release-probe-" + uuid4().hex
        try:
            result = subprocess.run(
                [
                    "docker",
                    "run",
                    "--rm",
                    "--pull",
                    "never",
                    "--name",
                    name,
                    "--network",
                    "none",
                    "--read-only",
                    "--cap-drop",
                    "ALL",
                    "--security-opt",
                    "no-new-privileges",
                    "--user",
                    user,
                    "--workdir",
                    "/app",
                    "--entrypoint",
                    "python",
                    images[service],
                    "-I",
                    "-B",
                    "-c",
                    PROBE,
                    str(uid),
                    str(gid),
                    module,
                ],
                check=True,
                capture_output=True,
                text=True,
                timeout=timeout,
            )
            proof = json.loads(result.stdout.strip().splitlines()[-1])
            if (proof.get("uid"), proof.get("gid"), proof.get("module")) != (
                uid,
                gid,
                module,
            ):
                raise ValueError("Invalid probe identity/module result")
            if not isinstance(proof.get("files_read"), int) or proof["files_read"] <= 0:
                raise ValueError("Probe did not read application source")
            services[service] = {
                "image_id": images[service],
                "image_tag": metadata[service],
                **proof,
            }
        except (subprocess.SubprocessError, ValueError, IndexError) as error:
            raise RuntimeError(
                f"{service} offline import probe failed; no release approval"
            ) from error
        finally:
            # A host-side timeout must not leave a probe running. Only our random
            # owned name is removed; never touch a production/container image tag.
            subprocess.run(
                ["docker", "rm", "-f", name],
                capture_output=True,
                timeout=timeout,
                check=False,
            )
    return {"passed": True, "revision": revision, "services": services}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--release", type=Path, required=True)
    parser.add_argument(
        "--backend-user", required=True, help="UID:GID from final Compose"
    )
    parser.add_argument(
        "--worker-user", required=True, help="UID:GID from final Compose"
    )
    parser.add_argument("--timeout", type=int, default=60)
    args = parser.parse_args()
    try:
        result = verify_release(**vars(args))
    except (ValueError, OSError, RuntimeError, subprocess.SubprocessError) as error:
        # Do not echo image import tracebacks or values of inherited settings.
        parser.exit(
            1, f"Release verification failed ({type(error).__name__}); do not deploy.\n"
        )
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
