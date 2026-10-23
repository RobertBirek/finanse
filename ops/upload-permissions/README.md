# Upload permissions — staging only

Policy: application UID/GID 10001, no default ACL inheritance. Existing originals
retain their owner and contents; named access ACL grants read only. Directories
grant UID 10001 rwx, `.backup.lock` grants rw. New originals are created by the
same UID used by backend/worker, with mode 0600. Root backup reads and locks;
worker only reads. Do not add other upload writers without reviewing permissions.

The tests use synthetic copies, never `/docker/finanse/data/uploads`. A future
production procedure needs separate approval, stopped writers and a verified
backup. No production-mutating command is provided here.

## Snapshot and rollback contract

Inside a validated staging root, save `getfacl -R -p -n .` in a separate 0700
operator-owned directory, manifest mode 0600. Retain relative inventory, numeric
owners/modes/inodes and hashes. Reject symlinks, special files, newline names,
absolute paths and `..`; each `# file:` record must be `.` or a contained `./`
relative path. Validate again before applying `setfacl --restore=before.acl`
from that same root. Do not log document paths or ACL manifests publicly.

Rollback aborts if inventory/inodes changed. It never deletes new documents or
guesses their ACL. New-write tests use a separate fixture from rollback tests.
Verify exact ACL/mode/owner restoration and unchanged content hashes.

## Backup lock and restore

Backend uses flock LOCK_EX on `.backup.lock` opened `a+b`; root backup uses
`flock "$UPLOAD_DIR/.backup.lock" tar ...`. Never replace that lock inode while
writers are active. ACL changes must not replace it. Restore and GC require
quiesced writers, not only a lock on a possibly replaced file.

Current backup archives normalize ownership to root and do not preserve ACLs.
After restore, verify non-root failure on root-owned 0600 originals first; then
reapply the approved access ACL policy and verify hashes, reads, writes and lock
contention before starting consumers. This is mandatory without default ACLs.

`Dockerfile.test` adds ACL tooling to a verified application image ONLY for tests.
The production runtime must not be confused with this helper image.

Build the application from the approved revision's backend Dockerfile and record
`docker image inspect --format '{{.Id}}' IMAGE` plus `pip freeze` output privately.
Build this test helper with
`--build-arg APPLICATION_IMAGE=local/finanse-backend@sha256:<immutable-manifest-digest>`;
the helper label `advisor.application-runtime` preserves the exact base ID.
Pass the resulting helper's immutable ID as `ACL_TEST_IMAGE`. Tests require the
test-only label and verify embedded requirements/service hashes against checkout.
No live environment files, credentials or production storage enter either build.
