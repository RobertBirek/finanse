"""Prepare an unapproved local checker bundle. Never install, approve, or deploy."""

from __future__ import annotations

import argparse
import email
import hashlib
import json
import os
import shutil
import stat
import sys
import sysconfig
from pathlib import Path
from typing import NoReturn

from preflight_launcher import YAML_FILES, BootstrapError, runtime_tree_digest
from release_preflight_exec import capture_process
from release_preflight_policy import CHECKER_SOURCE_PATHS, SHA, PreflightInputError
from release_preflight_trust import (
    FilePin,
    absolute,
    read_regular,
    require,
    token,
    verify_pinned_file,
)


def describe_runtime(python_runtime: Path) -> dict[str, object]:
    python = absolute(python_runtime)
    require(
        sys.version_info >= (3, 12) and python == Path(sys.executable).resolve(),
        "bundle_runtime_selection",
    )
    info = python.stat()
    require(info.st_uid == 0 and not info.st_mode & 0o022, "bundle_runtime_untrusted")
    stdlib = Path(sysconfig.get_path("stdlib")).resolve()
    try:
        tree_hash = runtime_tree_digest(stdlib)
    except BootstrapError:
        raise PreflightInputError("bundle_runtime_untrusted") from None
    return {
        "python_path": str(python),
        "python_sha256": hashlib.sha256(read_regular(python)).hexdigest(),
        "stdlib_root": str(stdlib),
        "stdlib_tree_sha256": tree_hash,
    }


def _yaml_payload(source: Path) -> dict[str, bytes]:
    source = absolute(source)
    candidates = [
        p for p in source.iterdir() if p.name.lower() == "pyyaml-6.0.3.dist-info"
    ]
    require(len(candidates) == 1, "bundle_yaml_source_invalid")
    info = absolute(candidates[0])
    raw = read_regular(info / "METADATA")
    metadata = email.message_from_bytes(raw)
    require(
        metadata.get_all("Name") == ["PyYAML"]
        and metadata.get_all("Version") == ["6.0.3"],
        "bundle_yaml_version_invalid",
    )
    licenses = [p for p in (info / "licenses/LICENSE", info / "LICENSE") if p.exists()]
    require(len(licenses) == 1, "bundle_yaml_license_missing")
    result = {
        "vendor/PyYAML-METADATA": raw,
        "vendor/PyYAML-LICENSE": read_regular(absolute(licenses[0])),
    }
    for name in YAML_FILES:
        result["vendor/yaml/" + name] = read_regular(absolute(source / "yaml" / name))
    return result


def prepare_bundle(
    repository: Path,
    revision: str,
    git_pin: FilePin,
    python_runtime: Path,
    yaml_source: Path,
    output: Path,
    *,
    max_output_bytes: int,
) -> Path:
    repository, output = absolute(repository), absolute(output)
    require(not output.exists(), "bundle_output_exists")
    parent = output.parent.stat()
    require(
        stat.S_IMODE(parent.st_mode) == 0o700 and parent.st_uid in {0, os.geteuid()},
        "bundle_output_parent_untrusted",
    )
    token(revision, SHA)
    require(
        type(max_output_bytes) is int and max_output_bytes > 0, "tool_limit_invalid"
    )
    prefix = [
        str(git_pin.path),
        "--no-pager",
        "--no-replace-objects",
        "-c",
        "core.hooksPath=/dev/null",
        "-c",
        "core.attributesFile=/dev/null",
        "-C",
        str(repository),
    ]
    env = {
        "PATH": "/usr/bin:/bin",
        "HOME": "/nonexistent",
        "LC_ALL": "C.UTF-8",
        "GIT_CONFIG_NOSYSTEM": "1",
        "GIT_CONFIG_GLOBAL": "/dev/null",
        "GIT_TERMINAL_PROMPT": "0",
        "GIT_OPTIONAL_LOCKS": "0",
    }

    def git(args: list[str]) -> str:
        verify_pinned_file(git_pin)
        result = capture_process(
            prefix + args, env, cwd=repository, max_output_bytes=max_output_bytes
        )
        verify_pinned_file(git_pin)
        return result

    require(
        git(["rev-parse", "--show-toplevel"]).strip() == str(repository)
        and git(["rev-parse", "--verify", revision + "^{commit}"]).strip() == revision,
        "bundle_source_invalid",
    )
    tree = git(["ls-tree", "-r", "-z", revision, "--"])
    require(tree.endswith("\0"), "bundle_source_invalid")
    blobs: dict[str, str] = {}
    for row in tree.split("\0")[:-1]:
        head, separator, path = row.partition("\t")
        if path not in CHECKER_SOURCE_PATHS:
            continue
        fields = head.split(" ")
        require(
            separator
            and len(fields) == 3
            and fields[0] in {"100644", "100755"}
            and fields[1] == "blob"
            and path not in blobs,
            "bundle_source_invalid",
        )
        blobs[path] = token(fields[2], SHA)
    require(set(blobs) == CHECKER_SOURCE_PATHS, "bundle_sources_missing")
    payloads = {}
    for source_path, blob in sorted(blobs.items()):
        name = Path(source_path).name
        target = name if name == "preflight_launcher.py" else "code/" + name
        payloads[target] = git(["cat-file", "blob", blob]).encode("utf-8")
    requirements = payloads["code/preflight-requirements.txt"].decode().splitlines()
    require(
        [
            line.strip()
            for line in requirements
            if line.strip() and not line.lstrip().startswith("#")
        ]
        == ["PyYAML==6.0.3"],
        "bundle_yaml_version_invalid",
    )
    payloads.update(_yaml_payload(yaml_source))
    runtime = describe_runtime(python_runtime)
    created = False
    root_identity = (0, 0)
    try:
        output.mkdir(mode=0o700)
        created = True
        info = output.lstat()
        root_identity = (info.st_dev, info.st_ino)
        for name in ("code", "vendor", "vendor/yaml"):
            (output / name).mkdir(mode=0o700)
        members = []
        for name, raw in sorted(payloads.items()):
            member_path = output / name
            member_path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
            with member_path.open("xb") as f:
                f.write(raw)
            mode = 0o555 if name == "preflight_launcher.py" else 0o644
            member_path.chmod(mode)
            members.append(
                {"path": name, "sha256": hashlib.sha256(raw).hexdigest(), "mode": mode}
            )
        manifest = output / "bundle-manifest.json"
        manifest.write_text(
            json.dumps(
                {
                    "version": 1,
                    "source_revision": revision,
                    "runtime": runtime,
                    "files": members,
                },
                sort_keys=True,
            )
        )
        manifest.chmod(0o600)
        return manifest
    except BaseException:
        if created:
            info = output.lstat()
            require(
                stat.S_ISDIR(info.st_mode)
                and (info.st_dev, info.st_ino) == root_identity,
                "bundle_cleanup_failed",
            )
            shutil.rmtree(output)
        raise


class _Parser(argparse.ArgumentParser):
    def error(self, message: str) -> NoReturn:
        raise PreflightInputError("arguments_invalid")


def main(argv: list[str] | None = None) -> int:
    parser = _Parser(description=__doc__, allow_abbrev=False)
    for name in (
        "repository",
        "revision",
        "git",
        "git-sha256",
        "python-runtime",
        "yaml-source",
        "output",
    ):
        parser.add_argument("--" + name, required=True)
    parser.add_argument("--max-output-bytes", required=True, type=int)
    try:
        args = parser.parse_args(argv)
        path = absolute(args.git)
        info = path.stat()
        pin = FilePin(path, args.git_sha256, stat.S_IMODE(info.st_mode), 0)
        manifest = prepare_bundle(
            Path(args.repository),
            args.revision,
            pin,
            Path(args.python_runtime),
            Path(args.yaml_source),
            Path(args.output),
            max_output_bytes=args.max_output_bytes,
        )
        print(
            json.dumps(
                {
                    "manifest": str(manifest),
                    "bundle_sha256": hashlib.sha256(manifest.read_bytes()).hexdigest(),
                    "approved": False,
                    "installed": False,
                }
            )
        )
        return 0
    except (PreflightInputError, BootstrapError) as error:
        code = error.code
    except (OSError, ValueError, TypeError, KeyError, RuntimeError):
        code = "bundle_input_invalid"
    print(json.dumps({"prepared": False, "approved": False, "reason_code": code}))
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
