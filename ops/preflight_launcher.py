"""Externally pinned bootstrap. Run with a trusted clean Python -I -S -B."""

from __future__ import annotations

import argparse
import hashlib
import importlib
import importlib.util
import json
import os
import re
import stat
import sys
import sysconfig
from pathlib import Path
from types import ModuleType
from typing import Any, NoReturn

sys.dont_write_bytecode = True

CODE_FILES = frozenset(
    {
        "release_preflight.py",
        "release_preflight_policy.py",
        "release_preflight_trust.py",
        "release_preflight_exec.py",
        "release_preflight_snapshot.py",
        "release_preflight_isolation.py",
        "release_preflight_review.py",
        "prepare_preflight_bundle.py",
        "preflight-requirements.txt",
    }
)
YAML_FILES = frozenset(
    {
        "__init__.py",
        "composer.py",
        "constructor.py",
        "cyaml.py",
        "dumper.py",
        "emitter.py",
        "error.py",
        "events.py",
        "loader.py",
        "nodes.py",
        "parser.py",
        "reader.py",
        "representer.py",
        "resolver.py",
        "scanner.py",
        "serializer.py",
        "tokens.py",
    }
)
REQUIRED_MEMBERS = (
    {"preflight_launcher.py", "vendor/PyYAML-METADATA", "vendor/PyYAML-LICENSE"}
    | {"code/" + name for name in CODE_FILES}
    | {"vendor/yaml/" + name for name in YAML_FILES}
)
HEX64 = re.compile(r"[0-9a-f]{64}")
SHA40 = re.compile(r"[0-9a-f]{40}")


class BootstrapError(ValueError):
    def __init__(self, code: str) -> None:
        self.code = code
        super().__init__(code)


def _require(ok: object, code: str) -> None:
    if not ok:
        raise BootstrapError(code)


def _object(value: Any, keys: set[str] | None = None) -> dict[str, Any]:
    _require(isinstance(value, dict), "bootstrap_shape_invalid")
    _require(keys is None or set(value) == keys, "bootstrap_shape_invalid")
    return dict(value)


def _digest(value: Any) -> str:
    _require(
        isinstance(value, str) and HEX64.fullmatch(value), "bootstrap_digest_invalid"
    )
    return str(value)


def _path(value: str | Path) -> Path:
    path = Path(value)
    _require(
        path.is_absolute() and path.resolve() == path and ".." not in path.parts,
        "bootstrap_path_invalid",
    )
    return path


def _identity(info: os.stat_result) -> tuple[int, ...]:
    return (
        info.st_dev,
        info.st_ino,
        info.st_size,
        info.st_uid,
        info.st_gid,
        info.st_mode,
        info.st_mtime_ns,
        info.st_ctime_ns,
    )


def _ancestors(path: Path, owner_uid: int) -> None:
    for parent in path.parents:
        info = parent.stat()
        sticky_root = info.st_uid == 0 and bool(info.st_mode & stat.S_ISVTX)
        _require(
            stat.S_ISDIR(info.st_mode)
            and info.st_uid in {0, owner_uid}
            and (not info.st_mode & 0o022 or sticky_root),
            "bootstrap_parent_untrusted",
        )


def _read(path: Path, *, owner_uid: int, private: bool = False) -> bytes:
    path = _path(path)
    _ancestors(path, owner_uid)
    before = path.lstat()
    _require(
        stat.S_ISREG(before.st_mode)
        and before.st_uid in {0, owner_uid}
        and not before.st_mode & 0o6022,
        "bootstrap_file_untrusted",
    )
    if private:
        parent = path.parent.stat()
        _require(
            stat.S_IMODE(before.st_mode) == 0o600
            and parent.st_uid in {0, owner_uid}
            and stat.S_IMODE(parent.st_mode) == 0o700,
            "bootstrap_permissions_invalid",
        )
    flags = os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK
    with os.fdopen(os.open(path, flags), "rb") as stream:
        opened = os.fstat(stream.fileno())
        _require(_identity(before) == _identity(opened), "bootstrap_file_changed")
        raw = stream.read()
        _require(
            _identity(opened) == _identity(os.fstat(stream.fileno()))
            and _identity(opened) == _identity(path.lstat())
            and len(raw) == opened.st_size,
            "bootstrap_file_changed",
        )
    return raw


def _json(raw: bytes) -> dict[str, Any]:
    def unique(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
        result: dict[str, Any] = {}
        for key, value in pairs:
            _require(key not in result, "bootstrap_duplicate_key")
            result[key] = value
        return result

    def constant(value: str) -> None:
        raise BootstrapError("bootstrap_json_invalid")

    return _object(json.loads(raw, object_pairs_hook=unique, parse_constant=constant))


def runtime_tree_digest(root: Path, *, owner_uid: int = 0) -> str:
    root = _path(root)
    rows = []

    def unavailable(error: OSError) -> NoReturn:
        raise BootstrapError("bootstrap_runtime_unavailable") from None

    for directory, dirs, files in os.walk(root, followlinks=False, onerror=unavailable):
        parent = Path(directory)
        info = parent.lstat()
        _require(
            stat.S_ISDIR(info.st_mode)
            and info.st_uid in {0, owner_uid}
            and not info.st_mode & 0o022,
            "bootstrap_runtime_untrusted",
        )
        for name in tuple(dirs):
            path = parent / name
            _require(not path.is_symlink(), "bootstrap_runtime_untrusted")
            if name in {"site-packages", "dist-packages"}:
                dirs.remove(name)
        for name in files:
            path = parent / name
            _require(not path.is_symlink(), "bootstrap_runtime_untrusted")
            if path.suffix not in {".py", ".pyc", ".so"}:
                continue
            raw = _read(path, owner_uid=owner_uid)
            rows.append(
                [
                    path.relative_to(root).as_posix(),
                    hashlib.sha256(raw).hexdigest(),
                    stat.S_IMODE(path.stat().st_mode),
                ]
            )
    _require(bool(rows), "bootstrap_runtime_invalid")
    encoded = json.dumps(
        sorted(rows), ensure_ascii=True, separators=(",", ":")
    ).encode()
    return hashlib.sha256(encoded).hexdigest()


def verify_bundle(
    bundle_root: Path,
    expected_sha256: str,
    *,
    owner_uid: int = 0,
) -> dict[str, object]:
    try:
        root = _path(bundle_root)
        _ancestors(root, owner_uid)
        info = root.lstat()
        _require(
            stat.S_ISDIR(info.st_mode)
            and info.st_uid == owner_uid
            and stat.S_IMODE(info.st_mode) == 0o700,
            "bootstrap_bundle_untrusted",
        )
        raw = _read(root / "bundle-manifest.json", owner_uid=owner_uid, private=True)
        _require(
            hashlib.sha256(raw).hexdigest() == _digest(expected_sha256),
            "bootstrap_bundle_changed",
        )
        manifest = _object(
            _json(raw), {"version", "source_revision", "runtime", "files"}
        )
        _require(
            type(manifest["version"]) is int
            and manifest["version"] == 1
            and isinstance(manifest["source_revision"], str)
            and SHA40.fullmatch(manifest["source_revision"]),
            "bootstrap_manifest_invalid",
        )
        _require(isinstance(manifest["files"], list), "bootstrap_manifest_invalid")
        names: set[str] = set()
        for value in manifest["files"]:
            item = _object(value, {"path", "sha256", "mode"})
            name = item["path"]
            _require(
                isinstance(name, str)
                and name in REQUIRED_MEMBERS
                and name not in names,
                "bootstrap_member_invalid",
            )
            names.add(name)
            path = root / name
            _require(
                type(item["mode"]) is int and 0 <= item["mode"] <= 0o777,
                "bootstrap_member_invalid",
            )
            content = _read(path, owner_uid=owner_uid)
            _require(
                stat.S_IMODE(path.stat().st_mode) == item["mode"]
                and hashlib.sha256(content).hexdigest() == _digest(item["sha256"]),
                "bootstrap_member_changed",
            )
        _require(names == REQUIRED_MEMBERS, "bootstrap_members_missing")
        actual: set[str] = set()
        allowed_dirs = {Path(name).parent.as_posix() for name in names}
        allowed_dirs |= {"code", "vendor", "vendor/yaml"}
        for path in root.rglob("*"):
            _require(not path.is_symlink(), "bootstrap_member_invalid")
            if path.is_dir():
                _require(
                    path.relative_to(root).as_posix() in allowed_dirs
                    and path.stat().st_uid == owner_uid
                    and stat.S_IMODE(path.stat().st_mode) == 0o700,
                    "bootstrap_directory_invalid",
                )
            else:
                actual.add(path.relative_to(root).as_posix())
        _require(actual == names | {"bundle-manifest.json"}, "bootstrap_extra_member")
        runtime = _object(
            manifest["runtime"],
            {"python_path", "python_sha256", "stdlib_root", "stdlib_tree_sha256"},
        )
        python = _path(runtime["python_path"])
        _require(
            hashlib.sha256(_read(python, owner_uid=owner_uid)).hexdigest()
            == _digest(runtime["python_sha256"]),
            "bootstrap_runtime_changed",
        )
        _require(
            runtime_tree_digest(_path(runtime["stdlib_root"]), owner_uid=owner_uid)
            == _digest(runtime["stdlib_tree_sha256"]),
            "bootstrap_runtime_changed",
        )
        return manifest
    except BootstrapError:
        raise
    except (OSError, ValueError, TypeError, KeyError, RuntimeError, RecursionError):
        raise BootstrapError("bootstrap_input_invalid") from None


def check_approval(
    path: Path,
    bundle_sha256: str,
    toolchain_sha256: str,
    review_scope_sha256: str | None,
    *,
    readiness_report: Path | None = None,
) -> dict[str, object]:
    try:
        record = _object(_json(_read(path, owner_uid=os.geteuid(), private=True)))
        version = record.get("version")
        keys = {
            "version",
            "operator_reference",
            "bundle_sha256",
            "toolchain_sha256",
            "review_scope_sha256",
        }
        if version == 2:
            keys.add("isolated_readiness")
        _object(record, keys)
        _require(
            type(version) is int
            and version in {1, 2}
            and isinstance(record["operator_reference"], str)
            and record["operator_reference"].strip()
            and record["bundle_sha256"] == _digest(bundle_sha256)
            and record["toolchain_sha256"] == _digest(toolchain_sha256)
            and record["review_scope_sha256"] == review_scope_sha256,
            "bootstrap_approval_mismatch",
        )
        if review_scope_sha256 is not None:
            _digest(review_scope_sha256)
        if version == 2:
            evidence = _object(
                record["isolated_readiness"],
                {
                    "candidate",
                    "inventory_sha256",
                    "report_sha256",
                    "kernel_release",
                    "kernel_version",
                    "machine",
                    "compose_sha256",
                },
            )
            candidate = evidence["candidate"]
            _require(
                isinstance(candidate, str) and re.fullmatch(r"[0-9a-f]{40}", candidate),
                "bootstrap_approval_invalid",
            )
            for key in ("inventory_sha256", "report_sha256", "compose_sha256"):
                _digest(evidence[key])
            if readiness_report is None:
                raise BootstrapError("bootstrap_readiness_report_required")
            readiness = _read(readiness_report, owner_uid=os.geteuid(), private=True)
            _require(
                hashlib.sha256(readiness).hexdigest() == evidence["report_sha256"],
                "bootstrap_readiness_report_mismatch",
            )
            host = os.uname()
            _require(
                (
                    evidence["kernel_release"],
                    evidence["kernel_version"],
                    evidence["machine"],
                )
                == (host.release, host.version, host.machine),
                "bootstrap_readiness_host_mismatch",
            )
        else:
            _require(readiness_report is None, "bootstrap_readiness_report_unexpected")
        return record
    except BootstrapError:
        raise
    except (OSError, ValueError, TypeError, KeyError, RuntimeError, RecursionError):
        raise BootstrapError("bootstrap_approval_invalid") from None


def validate_external_locations(repository: Path, bundle: Path, *paths: Path) -> None:
    repository, bundle = _path(repository), _path(bundle)
    _require(not bundle.is_relative_to(repository), "bootstrap_bundle_location")
    for path in paths:
        path = _path(path)
        _require(
            not path.is_relative_to(repository) and not path.is_relative_to(bundle),
            "bootstrap_approval_location",
        )


def import_checked(name: str, expected: Path) -> ModuleType:
    spec = importlib.util.find_spec(name)
    _require(
        spec is not None and spec.origin == str(expected),
        "bootstrap_import_origin",
    )
    loaded = importlib.import_module(name)
    _require(
        getattr(loaded, "__file__", None) == str(expected), "bootstrap_import_origin"
    )
    return loaded


def _blocked(code: str) -> int:
    print(
        json.dumps(
            {
                "report_version": 2,
                "action": "blocked",
                "reason_codes": [code],
                "authorized": False,
                "production_ready": False,
                "content_provenance_verified": False,
                "external_configuration_reviewed": False,
                "source_binding": "operator_approved_inventory",
                "candidate": None,
                "service_revisions": None,
                "image_ids": None,
                "schema_from": None,
                "schema_to": None,
                "pending_migrations": [],
                "required_gates": ["external_configuration_scope_review"],
                "checker_bundle_sha256": None,
                "toolchain_sha256": None,
                "review_scope_sha256": None,
                "reviewed_tooling_changes": [],
            },
            sort_keys=True,
        )
    )
    return 2


class _Parser(argparse.ArgumentParser):
    def error(self, message: str) -> NoReturn:
        raise BootstrapError("arguments_invalid")


def main(argv: list[str] | None = None) -> int:
    parser = _Parser(description=__doc__, allow_abbrev=False)
    for name in (
        "bundle",
        "bundle-sha256",
        "toolchain",
        "toolchain-sha256",
        "approval",
    ):
        parser.add_argument("--" + name, required=True)
    parser.add_argument("--repository", required=True)
    parser.add_argument("--review-scope")
    parser.add_argument("--review-report")
    parser.add_argument("--review-scope-sha256")
    parser.add_argument("--readiness-report", type=Path)
    try:
        args, forwarded = parser.parse_known_args(argv)
        optional = (args.review_scope, args.review_report, args.review_scope_sha256)
        _require(
            all(value is None for value in optional)
            or all(value is not None for value in optional),
            "arguments_invalid",
        )
        root = _path(args.bundle)
        external = [Path(args.toolchain), Path(args.approval)]
        if args.review_scope is not None:
            external += [Path(args.review_scope), Path(args.review_report)]
        if args.readiness_report is not None:
            external.append(args.readiness_report)
        validate_external_locations(Path(args.repository), root, *external)
        manifest = verify_bundle(root, args.bundle_sha256)
        _require(
            Path(__file__).resolve() == root / "preflight_launcher.py",
            "bootstrap_launcher_origin",
        )
        runtime = _object(manifest["runtime"])
        _require(
            sys.flags.isolated
            and sys.flags.no_site
            and sys.flags.dont_write_bytecode
            and sys.version_info >= (3, 12)
            and Path(sys.executable).resolve() == Path(runtime["python_path"])
            and Path(sysconfig.get_path("stdlib")).resolve()
            == Path(runtime["stdlib_root"]),
            "bootstrap_runtime_selection",
        )
        for variable in os.environ:
            _require(
                not variable.startswith(("PYTHON", "LD_"))
                and variable not in {"DYLD_INSERT_LIBRARIES"},
                "bootstrap_startup_environment",
            )
        stdlib = Path(runtime["stdlib_root"])
        for entry in sys.path:
            path = Path(entry)
            _require(
                path.is_absolute()
                and (
                    path == stdlib
                    or path == stdlib / "lib-dynload"
                    or (path.suffix == ".zip" and not path.exists())
                ),
                "bootstrap_import_path",
            )
        approval = check_approval(
            Path(args.approval),
            args.bundle_sha256,
            args.toolchain_sha256,
            args.review_scope_sha256,
            readiness_report=args.readiness_report,
        )
        code, vendor = root / "code", root / "vendor"
        names = {"yaml"} | {
            Path(name).stem for name in CODE_FILES if name.endswith(".py")
        }
        _require(
            not any(name in sys.modules for name in names), "bootstrap_cached_module"
        )
        sys.path[:] = [str(stdlib), str(stdlib / "lib-dynload"), str(code), str(vendor)]
        trust = import_checked(
            "release_preflight_trust", code / "release_preflight_trust.py"
        )
        toolchain_path = _path(args.toolchain)
        tools = trust.load_toolchain(toolchain_path, args.toolchain_sha256)
        isolated_approval = None
        if approval["version"] == 2:
            evidence = _object(approval["isolated_readiness"])
            _require(
                evidence["compose_sha256"] == tools.compose.sha256,
                "bootstrap_readiness_compose_mismatch",
            )
            isolated_approval = (evidence["candidate"], evidence["inventory_sha256"])
        context = trust.BootstrapContext(
            bundle_sha256=args.bundle_sha256,
            toolchain_sha256=args.toolchain_sha256,
            toolchain=tools,
            review_scope_sha256=args.review_scope_sha256,
            runtime_root=root,
            isolated_approval=isolated_approval,
        )
        for name in (
            "release_preflight_policy",
            "release_preflight_exec",
            "release_preflight_snapshot",
            "release_preflight_isolation",
            "release_preflight_review",
        ):
            import_checked(name, code / (name + ".py"))
        import_checked("yaml", vendor / "yaml/__init__.py")
        checker = import_checked("release_preflight", code / "release_preflight.py")
        for name in names:
            loaded = sys.modules.get(name)
            if loaded is not None:
                expected = (
                    vendor / "yaml/__init__.py"
                    if name == "yaml"
                    else code / (name + ".py")
                )
                origin = loaded.__file__
                if origin is None:
                    raise BootstrapError("bootstrap_import_origin")
                _require(
                    Path(origin).resolve() == expected,
                    "bootstrap_import_origin",
                )
        forwarded += ["--repository", args.repository]
        if args.review_scope_sha256 is not None:
            forwarded += [
                "--review-scope",
                args.review_scope,
                "--review-report",
                args.review_report,
                "--review-scope-sha256",
                args.review_scope_sha256,
            ]
        return int(checker.main(forwarded, bootstrap=context))
    except BootstrapError as error:
        return _blocked(error.code)
    except (
        OSError,
        ValueError,
        TypeError,
        KeyError,
        AttributeError,
        ImportError,
        RuntimeError,
    ):
        return _blocked("bootstrap_input_invalid")


if __name__ == "__main__":
    raise SystemExit(main())
