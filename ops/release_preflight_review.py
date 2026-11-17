"""Check exact operator-approved review evidence against pinned Git objects."""

from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Any

from release_preflight_exec import ReadOnlyRunner
from release_preflight_policy import (
    SERVICES,
    SHA,
    TOOLING_PATHS,
    PreflightInputError,
    SourceChange,
    VerifiedToolingScope,
    _runtime_scope,
    valid_tooling_change,
)
from release_preflight_trust import (
    mapping,
    read_private_json,
    read_regular,
    require,
    token,
)


def _tree(runner: ReadOnlyRunner, revision: str) -> dict[str, tuple[str, str]]:
    output = runner.run(runner.git_prefix + ["ls-tree", "-r", "-z", revision, "--"])
    require(not output or output.endswith("\0"), "git_tree_invalid")
    result: dict[str, tuple[str, str]] = {}
    for row in output.split("\0")[:-1]:
        header, separator, path = row.partition("\t")
        parts = header.split(" ")
        require(
            separator and len(parts) == 3 and path not in result, "git_tree_invalid"
        )
        mode, kind, blob = parts
        token(blob, SHA)
        require(kind in {"blob", "commit"}, "git_tree_invalid")
        result[path] = (mode, blob)
    return result


def collect_source_changes(
    runner: ReadOnlyRunner,
    *,
    candidate: str,
    service_revisions: dict[str, str],
) -> tuple[SourceChange, ...]:
    token(candidate, SHA)
    require(set(service_revisions) == SERVICES, "source_services_invalid")
    revisions = {candidate}
    for revision in service_revisions.values():
        revisions.add(token(revision, SHA))
    trees = {}
    for revision in sorted(revisions):
        observed = runner.run(
            runner.git_prefix + ["rev-parse", "--verify", revision + "^{commit}"]
        )
        require(observed.strip() == revision, "git_commit_invalid")
        trees[revision] = _tree(runner, revision)
    target = trees[candidate]
    content_hashes: dict[str, str] = {}
    result = []
    for service, revision in sorted(service_revisions.items()):
        runner.run(
            runner.git_prefix + ["merge-base", "--is-ancestor", revision, candidate]
        )
        output = runner.run(
            runner.git_prefix
            + [
                "diff",
                "--no-ext-diff",
                "--no-textconv",
                "--no-renames",
                "--name-only",
                "-z",
                revision,
                candidate,
                "--",
            ]
        )
        require(not output or output.endswith("\0"), "git_diff_invalid")
        paths = output.split("\0")[:-1]
        require(len(paths) == len(set(paths)), "git_diff_invalid")
        for path in paths:
            before, after = trees[revision].get(path), target.get(path)
            require(before is not None or after is not None, "git_diff_invalid")
            require(
                all(
                    entry is None or entry[0] in {"100644", "100755"}
                    for entry in (before, after)
                ),
                "git_entry_type_changed",
            )
            after_hash = None
            # SHA256 is a review witness for eligible tooling, not an attempt
            # to UTF-8 decode unrelated binary application assets.
            if after is not None and path in TOOLING_PATHS:
                blob = after[1]
                if blob not in content_hashes:
                    content = runner.run(runner.git_prefix + ["cat-file", "blob", blob])
                    content_hashes[blob] = hashlib.sha256(
                        content.encode("utf-8")
                    ).hexdigest()
                after_hash = content_hashes[blob]
            result.append(
                SourceChange(
                    service,
                    path,
                    before[0] if before else None,
                    before[1] if before else None,
                    after[0] if after else None,
                    after[1] if after else None,
                    after_hash,
                )
            )
    return tuple(result)


def _change(value: Any) -> SourceChange:
    record = mapping(value, set(SourceChange.__dataclass_fields__))
    require(
        isinstance(record["path"], str) and record["path"] in TOOLING_PATHS,
        "unknown_change_scope",
    )
    change = SourceChange(**record)
    require(valid_tooling_change(change), "review_scope_invalid")
    return change


def verify_review_scope(
    path: Path,
    expected_sha256: str,
    *,
    candidate: str,
    service_revisions: dict[str, str],
    checker_bundle_sha256: str,
    actual_changes: tuple[SourceChange, ...],
    review_report: Path,
) -> VerifiedToolingScope:
    token(candidate, SHA)
    token(checker_bundle_sha256)
    require(set(service_revisions) == SERVICES, "review_scope_invalid")
    for value in service_revisions.values():
        token(value, SHA)
    actual = []
    for change in actual_changes:
        try:
            _runtime_scope(change.path)
        except PreflightInputError:
            require(change.path in TOOLING_PATHS, "unknown_change_scope")
            actual.append(change)
    require(bool(actual), "review_scope_unnecessary")
    record = mapping(
        read_private_json(path, expected_sha256),
        {
            "version",
            "candidate",
            "service_revisions",
            "checker_bundle_sha256",
            "review_report_sha256",
            "review_result",
            "changes",
        },
    )
    require(
        type(record["version"]) is int
        and record["version"] == 1
        and record["candidate"] == candidate
        and mapping(record["service_revisions"], set(SERVICES)) == service_revisions
        and record["checker_bundle_sha256"] == checker_bundle_sha256
        and record["review_result"] == "accepted_no_open_critical_or_important",
        "review_scope_mismatch",
    )
    expected_report = token(record["review_report_sha256"])
    report = read_regular(review_report, private=True)
    require(
        hashlib.sha256(report).hexdigest() == expected_report, "review_report_changed"
    )
    changes = record["changes"]
    require(isinstance(changes, list), "review_scope_invalid")
    proposed = tuple(_change(item) for item in changes)
    keys = [(item.service, item.path) for item in proposed]
    require(len(keys) == len(set(keys)), "review_scope_invalid")

    def ordering(item: SourceChange) -> tuple[str, str]:
        return item.service, item.path

    canonical = tuple(sorted(actual, key=ordering))
    require(tuple(sorted(proposed, key=ordering)) == canonical, "review_scope_mismatch")
    return VerifiedToolingScope(
        proof_sha256=expected_sha256,
        changes=canonical,
        candidate=candidate,
        service_revisions=tuple(sorted(service_revisions.items())),
        checker_bundle_sha256=checker_bundle_sha256,
    )
