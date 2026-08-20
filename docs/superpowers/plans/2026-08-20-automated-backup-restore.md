# Automated Backup and Restore Drill Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Automate the encrypted daily production backup and monthly isolated restore drill with systemd timers, safe cleanup and observable failures.

**Architecture:** Versioned systemd unit templates and a restore-drill wrapper live in `ops/systemd/`. The explicit root-only installer copies units to `/etc/systemd/system`, installs the wrapper as `root:root` `0750` at `/usr/local/lib/finanse/run-restore-drill.sh`, and creates the persistent empty restore parent and Restic cache as `root:root` `0700`. The external `/docker/finanse/Makefile` remains the boundary that loads root-only environment files and sets `RESTIC_CACHE_DIR=/docker/finanse/data/restic-cache`. Services and manual backup targets share the 15-minute host lock; production restore drills use only the service, whose installed wrapper creates the guarded isolated database before verification and ownership-aware cleanup removes only the drill's exact outputs after success or failure. Restore selection uses `RESTORE_SNAPSHOT_ID`; legacy `snapshot=` is rejected before runner or Restic execution.

**Tech Stack:** Bash, GNU Make, systemd 255 timers/services, flock, Restic, PostgreSQL client tools, pytest static/subprocess tests.

---

## File structure

| File | Responsibility |
| --- | --- |
| `backend/tests/test_ops/test_backup_scripts.py` | Regression tests for systemd calendars, no-secret units, wrapper guards and installer behaviour. |
| `ops/systemd/finanse-backup.service` | One-shot, hardened daily backup service. |
| `ops/systemd/finanse-backup.timer` | Persistent daily timer at 02:30 Europe/Warsaw. |
| `ops/systemd/finanse-restore-verify.service` | One-shot, hardened monthly restore-drill service. |
| `ops/systemd/finanse-restore-verify.timer` | Persistent first-Sunday timer at 04:30 Europe/Warsaw. |
| `ops/systemd/finanse-operation-failure@.service` | Secret-free journald alert for a failed operation. |
| `ops/systemd/run-restore-drill.sh` | Source for the guarded invocation and ownership-aware cleanup installed outside the repository. |
| `ops/systemd/install-timers.sh` | Root-only, idempotent installation of units, wrapper, persistent restore parent and timers. |
| `/docker/finanse/Makefile` | Loads configuration and the persistent Restic cache for backup and the wrapper's internal `restore-verify` target; external infrastructure, not committed to this repository. |
| `docs/operations/backup-restore.md` | Installation, status, logs, manual run, disable and incident procedure. |
| `docs/CHANGELOG.md`, `docs/TASKS.md`, `docs/JOURNAL.md` | Delivery record and operational status. |

### Task 1: Add regression tests for scheduler definitions

**Files:**
- Modify: `backend/tests/test_ops/test_backup_scripts.py`
- Create: `ops/systemd/finanse-backup.service`
- Create: `ops/systemd/finanse-backup.timer`
- Create: `ops/systemd/finanse-restore-verify.service`
- Create: `ops/systemd/finanse-restore-verify.timer`
- Create: `ops/systemd/finanse-operation-failure@.service`

- [ ] **Step 1: Write failing static tests for the five unit files.**

  Add constants and tests near the existing script constants:

  ```python
  SYSTEMD_DIRECTORY = REPOSITORY_ROOT / "ops" / "systemd"
  BACKUP_TIMER = SYSTEMD_DIRECTORY / "finanse-backup.timer"
  RESTORE_TIMER = SYSTEMD_DIRECTORY / "finanse-restore-verify.timer"
  BACKUP_SERVICE = SYSTEMD_DIRECTORY / "finanse-backup.service"
  RESTORE_SERVICE = SYSTEMD_DIRECTORY / "finanse-restore-verify.service"
  FAILURE_SERVICE = SYSTEMD_DIRECTORY / "finanse-operation-failure@.service"

  def test_backup_timer_is_persistent_and_uses_warsaw_schedule() -> None:
      content = read_script(BACKUP_TIMER)
      assert "OnCalendar=*-*-* 02:30:00 Europe/Warsaw" in content
      assert "Persistent=true" in content
      assert "Unit=finanse-backup.service" in content
      assert "WantedBy=timers.target" in content

  def test_restore_timer_is_persistent_and_uses_first_sunday_warsaw_schedule() -> None:
      content = read_script(RESTORE_TIMER)
      assert "OnCalendar=Sun *-*-01..07 04:30:00 Europe/Warsaw" in content
      assert "Persistent=true" in content
      assert "Unit=finanse-restore-verify.service" in content

  def test_scheduled_services_use_the_shared_lock_and_never_embed_secrets() -> None:
      for path in (BACKUP_SERVICE, RESTORE_SERVICE, FAILURE_SERVICE):
          content = read_script(path)
          assert "SECRET_KEY=" not in content
          assert "PASSWORD=" not in content
          assert "RESTIC_PASSWORD=" not in content
      for path in (BACKUP_SERVICE, RESTORE_SERVICE):
          content = read_script(path)
          assert "/usr/bin/flock -w 900 /run/lock/finanse-backup-restore.lock" in content
          assert "NoNewPrivileges=true" in content
          assert "PrivateTmp=true" in content
          assert "UMask=0077" in content
          assert "OnFailure=finanse-operation-failure@%n.service" in content
  ```

- [ ] **Step 2: Run the focused test to confirm RED.**

  Run:

  ```bash
  cd /opt/finanse/backend && .venv/bin/pytest tests/test_ops/test_backup_scripts.py -k 'backup_timer or restore_timer or scheduled_services' -v
  ```

  Expected: FAIL because `ops/systemd/` and its unit files do not yet exist.

- [ ] **Step 3: Create the minimal unit definitions.**

  Create `ops/systemd/finanse-backup.service`:

  ```ini
  [Unit]
  Description=Personal Advisor encrypted backup
  Wants=network-online.target
  After=docker.service network-online.target
  OnFailure=finanse-operation-failure@%n.service

  [Service]
  Type=oneshot
  User=root
  Group=root
  WorkingDirectory=/docker/finanse
  UMask=0077
  TimeoutStartSec=2h
  NoNewPrivileges=true
  PrivateTmp=true
  ProtectSystem=strict
  ProtectHome=true
  ReadWritePaths=/docker/finanse/data/backups /run/lock
  ExecStart=/usr/bin/flock -w 900 /run/lock/finanse-backup-restore.lock /usr/bin/make -C /docker/finanse backup
  ```

  Create `ops/systemd/finanse-backup.timer`:

  ```ini
  [Unit]
  Description=Daily Personal Advisor backup

  [Timer]
  OnCalendar=*-*-* 02:30:00 Europe/Warsaw
  Persistent=true
  Unit=finanse-backup.service

  [Install]
  WantedBy=timers.target
  ```

  Create `ops/systemd/finanse-restore-verify.service` with the same unit and
  hardening fields, but `ReadWritePaths=/docker/finanse/data/restore-drill /run/lock`
  and:

  ```ini
   ExecStart=/usr/bin/flock -w 900 /run/lock/finanse-backup-restore.lock /usr/local/lib/finanse/run-restore-drill.sh
  ```

  Create `ops/systemd/finanse-restore-verify.timer`:

  ```ini
  [Unit]
  Description=Monthly Personal Advisor restore verification

  [Timer]
  OnCalendar=Sun *-*-01..07 04:30:00 Europe/Warsaw
  Persistent=true
  Unit=finanse-restore-verify.service

  [Install]
  WantedBy=timers.target
  ```

  Create `ops/systemd/finanse-operation-failure@.service`:

  ```ini
  [Unit]
  Description=Record failed Personal Advisor scheduled operation (%I)

  [Service]
  Type=oneshot
  UMask=0077
  NoNewPrivileges=true
  PrivateTmp=true
  ProtectSystem=strict
  ProtectHome=true
  ExecStart=/usr/bin/logger --priority user.err --tag finanse-operation-failure "Scheduled operation %I failed; inspect journalctl -u %I"
  ```

- [ ] **Step 4: Run static tests and systemd syntax verification.**

  Run:

  ```bash
  cd /opt/finanse/backend && .venv/bin/pytest tests/test_ops/test_backup_scripts.py -k 'backup_timer or restore_timer or scheduled_services' -v
  systemd-analyze verify /opt/finanse/ops/systemd/finanse-backup.service /opt/finanse/ops/systemd/finanse-backup.timer /opt/finanse/ops/systemd/finanse-restore-verify.service /opt/finanse/ops/systemd/finanse-restore-verify.timer /opt/finanse/ops/systemd/finanse-operation-failure@.service
  systemd-analyze calendar '*-*-* 02:30:00 Europe/Warsaw'
  systemd-analyze calendar 'Sun *-*-01..07 04:30:00 Europe/Warsaw'
  ```

  Expected: focused pytest PASS; `systemd-analyze verify` exits 0; calendar
  output identifies 02:30 daily and the next first Sunday at 04:30.

- [ ] **Step 5: Commit the scheduler unit definitions and tests.**

  ```bash
  git add backend/tests/test_ops/test_backup_scripts.py ops/systemd/finanse-backup.service ops/systemd/finanse-backup.timer ops/systemd/finanse-restore-verify.service ops/systemd/finanse-restore-verify.timer ops/systemd/finanse-operation-failure@.service
  git commit -m "feat: dodaj timery backupu i restore drillu"
  ```

### Task 2: Implement guarded restore-drill execution and cleanup

**Files:**
- Modify: `backend/tests/test_ops/test_backup_scripts.py`
- Create: `ops/systemd/run-restore-drill.sh`
- Modify: `/docker/finanse/Makefile`

- [ ] **Step 1: Write failing tests for the scheduler wrapper.**

  Add a wrapper constant and tests that assert explicit guard and ordering:

  ```python
  RESTORE_DRILL_WRAPPER = SYSTEMD_DIRECTORY / "run-restore-drill.sh"

  def test_restore_drill_wrapper_is_private_and_runs_only_the_guarded_target() -> None:
      content = read_script(RESTORE_DRILL_WRAPPER)
      assert RESTORE_DRILL_WRAPPER.stat().st_mode & stat.S_IXUSR
      assert "set -euo pipefail" in content
      assert "umask 077" in content
      assert 'readonly COMPOSE_DIRECTORY="/docker/finanse"' in content
      assert 'readonly RESTORE_DIRECTORY="$COMPOSE_DIRECTORY/data/restore-drill"' in content
      assert 'readonly RESTORE_DATABASE="finanse_restore"' in content
      assert 'RESTORE_SNAPSHOT_ID=latest make -C "$COMPOSE_DIRECTORY" restore-verify' in content
      assert content.index('RESTORE_SNAPSHOT_ID=latest') < content.index('dropdb')
      assert content.index('dropdb') < content.index('rm -rf -- "$RESTORE_DIRECTORY/uploads"')

  def test_restore_drill_wrapper_refuses_any_unexpected_restore_target() -> None:
      content = read_script(RESTORE_DRILL_WRAPPER)
      assert '[[ "$RESTORE_DIR" == "$RESTORE_DIRECTORY" ]]' in content
      assert '[[ "$restore_host" == "127.0.0.1" ]]' in content
      assert '[[ "$restore_database" == "$RESTORE_DATABASE" ]]' in content
      assert 'find "$RESTORE_DIRECTORY" -mindepth 1 -maxdepth 1' in content
  ```

- [ ] **Step 2: Run focused wrapper tests to confirm RED.**

  Run:

  ```bash
  cd /opt/finanse/backend && .venv/bin/pytest tests/test_ops/test_backup_scripts.py -k restore_drill_wrapper -v
  ```

  Expected: FAIL because `run-restore-drill.sh` does not exist.

- [ ] **Step 3: Extend the external Makefile without embedding secrets.**

  In `/docker/finanse/Makefile`, replace the existing `restore-verify` recipe
  with the following recipe. It uses the existing password-free `.pgpass`
  flow and creates only the exact restore directory.

  ```make
  restore-verify:
	@set -eu; \
	set -a; . ./.env; . ./secrets/restic-contabo.env; . ./secrets/backup.env; set +a; \
	mkdir -p /docker/finanse/data/restore-drill; \
	RESTORE_DATABASE_URL_SYNC="postgresql://$$POSTGRES_USER@127.0.0.1:55431/finanse_restore" \
	RESTORE_DIR=/docker/finanse/data/restore-drill \
	bash /opt/finanse/ops/restore-verify.sh
  ```

  Keep the `backup` recipe unchanged. Verify that the existing
  `postgres.pgpass` has a `127.0.0.1:55431` entry before invoking the target;
  do not print the entry.

- [ ] **Step 4: Implement the wrapper with exact guards.**

  Create an executable `ops/systemd/run-restore-drill.sh`:

  ```bash
  #!/usr/bin/env bash
  set -euo pipefail
  umask 077

  readonly COMPOSE_DIRECTORY="/docker/finanse"
  readonly RESTORE_DIRECTORY="$COMPOSE_DIRECTORY/data/restore-drill"
  readonly RESTORE_DATABASE="finanse_restore"

  fail() { printf '%s\n' "$1" >&2; exit 1; }
  [[ -d "$COMPOSE_DIRECTORY" ]] || fail "Compose directory is unavailable."
  [[ -f "$COMPOSE_DIRECTORY/.env" ]] || fail "Compose environment is unavailable."
  [[ -f "$COMPOSE_DIRECTORY/secrets/backup.env" ]] || fail "Backup environment is unavailable."

  set -a
  # shellcheck disable=SC1091
  . "$COMPOSE_DIRECTORY/.env"
  # shellcheck disable=SC1091
  . "$COMPOSE_DIRECTORY/secrets/backup.env"
  set +a

  RESTORE_DIR="$RESTORE_DIRECTORY"
  mapfile -t restore_parts < <(
      POSTGRES_CONNECTION_URL="postgresql://${POSTGRES_USER}@127.0.0.1:55431/${RESTORE_DATABASE}" \
      POSTGRES_PASSFILE="$PGPASSFILE" python3 /opt/finanse/ops/postgres_connection.py
  )
  [[ ${#restore_parts[@]} -eq 5 ]] || fail "Restore connection is invalid."
  restore_host="${restore_parts[0]}"
  restore_port="${restore_parts[1]}"
  restore_user="${restore_parts[2]}"
  restore_database="${restore_parts[3]}"
  [[ "$RESTORE_DIR" == "$RESTORE_DIRECTORY" ]] || fail "Restore directory is not allowed."
  [[ "$restore_host" == "127.0.0.1" ]] || fail "Restore host is not allowed."
  [[ "$restore_database" == "$RESTORE_DATABASE" ]] || fail "Restore database is not allowed."
  [[ -d "$RESTORE_DIRECTORY" ]] || fail "Restore directory is unavailable."
  [[ -z "$(find "$RESTORE_DIRECTORY" -mindepth 1 -maxdepth 1 -print -quit)" ]] || fail "Restore directory is not empty."

  restore_database_created=false
  cleanup() {
      local exit_code=$?
      if [[ "$exit_code" -ne 0 && "$restore_database_created" == true ]]; then
          dropdb --if-exists --host "$restore_host" --port "$restore_port" --username "$restore_user" "$restore_database" || true
          [[ -d "$RESTORE_DIRECTORY/uploads" ]] && rm -rf -- "$RESTORE_DIRECTORY/uploads" || true
      fi
      return "$exit_code"
  }
  trap cleanup EXIT
  createdb --host "$restore_host" --port "$restore_port" --username "$restore_user" "$restore_database"
  restore_database_created=true
  FINANSE_OPERATION_LOCK_HELD=1 RESTORE_SNAPSHOT_ID=latest make -C "$COMPOSE_DIRECTORY" restore-verify
  dropdb --if-exists --host "$restore_host" --port "$restore_port" --username "$restore_user" "$restore_database"
  [[ -d "$RESTORE_DIRECTORY/uploads" ]] || fail "Restore uploads are missing."
  [[ -z "$(find "$RESTORE_DIRECTORY" -mindepth 1 -maxdepth 1 ! -name uploads -print -quit)" ]] || fail "Unexpected restore output."
  rm -rf -- "$RESTORE_DIRECTORY/uploads"
  restore_database_created=false
  trap - EXIT
  ```

  Preserve `PGPASSFILE` from `backup.env`; do not export or log a password.
  `createdb` and `dropdb` operate only after the exact host/database checks.
  The EXIT trap removes the exact database and upload output if the verifier
  fails after database creation; the root-owned empty parent is retained.

  Mark the wrapper executable:

  ```bash
   # The installer applies root:root mode 0750 at its installed destination.
  ```

- [ ] **Step 5: Run wrapper tests and syntax checks.**

  Run:

  ```bash
  cd /opt/finanse/backend && .venv/bin/pytest tests/test_ops/test_backup_scripts.py -k 'restore_drill_wrapper or restore_script' -v
  bash -n /opt/finanse/ops/systemd/run-restore-drill.sh
  # Production drills run only through finanse-restore-verify.service.
  ```

  Expected: focused tests PASS, Bash syntax exits 0, and dry-run emits no
  secret value.

- [ ] **Step 6: Commit the wrapper and its tests.**

  ```bash
  git add backend/tests/test_ops/test_backup_scripts.py ops/systemd/run-restore-drill.sh
  git commit -m "feat: automatyzuj bezpieczny cleanup restore drillu"
  ```

### Task 3: Add an idempotent root-only installer

**Files:**
- Modify: `backend/tests/test_ops/test_backup_scripts.py`
- Create: `ops/systemd/install-timers.sh`

- [ ] **Step 1: Write a failing test for explicit installer scope.**

  ```python
  INSTALLER = SYSTEMD_DIRECTORY / "install-timers.sh"

  def test_timer_installer_verifies_then_installs_only_known_units() -> None:
      content = read_script(INSTALLER)
      assert "set -euo pipefail" in content
      assert '[[ "$(id -u)" -eq 0 ]]' in content
      assert "systemd-analyze verify" in content
      assert "install -o root -g root -m 0644" in content
      assert "systemctl daemon-reload" in content
      assert "systemctl enable --now finanse-backup.timer finanse-restore-verify.timer" in content
      assert "rm -rf" not in content
      assert "secrets/" not in content
  ```

- [ ] **Step 2: Run the installer test to confirm RED.**

  Run:

  ```bash
  cd /opt/finanse/backend && .venv/bin/pytest tests/test_ops/test_backup_scripts.py -k timer_installer -v
  ```

  Expected: FAIL because the installer does not exist.

- [ ] **Step 3: Create the installer.**

  Create executable `ops/systemd/install-timers.sh`:

  ```bash
  #!/usr/bin/env bash
  set -euo pipefail

  readonly UNIT_SOURCE_DIRECTORY="/opt/finanse/ops/systemd"
  readonly UNIT_DESTINATION_DIRECTORY="/etc/systemd/system"
  readonly UNITS=(
      finanse-backup.service
      finanse-backup.timer
      finanse-restore-verify.service
      finanse-restore-verify.timer
      finanse-operation-failure@.service
  )

  [[ "$(id -u)" -eq 0 ]] || { printf '%s\n' "Run as root." >&2; exit 1; }
  systemd-analyze verify "${UNIT_SOURCE_DIRECTORY}"/*.service "${UNIT_SOURCE_DIRECTORY}"/*.timer
  for unit in "${UNITS[@]}"; do
      install -o root -g root -m 0644 "${UNIT_SOURCE_DIRECTORY}/${unit}" "${UNIT_DESTINATION_DIRECTORY}/${unit}"
  done
   install -D -o root -g root -m 0750 "${UNIT_SOURCE_DIRECTORY}/run-restore-drill.sh" \
       /usr/local/lib/finanse/run-restore-drill.sh
   install -d -o root -g root -m 0700 /docker/finanse/data/restore-drill
  systemctl daemon-reload
  systemctl enable --now finanse-backup.timer finanse-restore-verify.timer
  systemctl list-timers --all finanse-backup.timer finanse-restore-verify.timer
  ```

   Install the wrapper outside `/opt/finanse`: the installed unit calls the
   root-owned absolute path, never a repository executable.

- [ ] **Step 4: Verify the installer and unit syntax.**

  Run:

  ```bash
  cd /opt/finanse/backend && .venv/bin/pytest tests/test_ops/test_backup_scripts.py -k timer_installer -v
  bash -n /opt/finanse/ops/systemd/install-timers.sh
  systemd-analyze verify /opt/finanse/ops/systemd/*.service /opt/finanse/ops/systemd/*.timer
  ```

  Expected: all commands exit 0. Do not run the installer in this step.

- [ ] **Step 5: Commit the installer and test.**

  ```bash
  git add backend/tests/test_ops/test_backup_scripts.py ops/systemd/install-timers.sh
  git commit -m "feat: dodaj instalator timerów backupu"
  ```

### Task 4: Document, install and prove the scheduled operations

**Files:**
- Modify: `docs/operations/backup-restore.md`
- Modify: `docs/CHANGELOG.md`
- Modify: `docs/TASKS.md`
- Modify: `docs/JOURNAL.md`
- Modify: `/docker/finanse/Makefile`

- [ ] **Step 1: Add installation and incident instructions.**

  Add an “Automatyzacja systemd” section to `docs/operations/backup-restore.md`
  with these exact operator commands:

  ```bash
  sudo /opt/finanse/ops/systemd/install-timers.sh
  systemctl list-timers --all finanse-backup.timer finanse-restore-verify.timer
  sudo systemctl start finanse-backup.service
  sudo journalctl -u finanse-backup.service -n 100 --no-pager
  sudo systemctl start finanse-restore-verify.service
  sudo journalctl -u finanse-restore-verify.service -n 100 --no-pager
  sudo systemctl disable --now finanse-backup.timer finanse-restore-verify.timer
  ```

  State that a restore drill never targets production, removes `finanse_restore`
  and its temporary uploads after a successful verification, and must be
  investigated through the failure unit/journal before a manual rerun.

- [ ] **Step 2: Run the complete test and static-quality gates.**

  Run:

  ```bash
  cd /opt/finanse && make test && make lint && make typecheck
  git diff --check
  ```

  Expected: backend and frontend tests, linters, typechecks and diff check all
  pass. Treat any failed command as a blocker.

- [ ] **Step 3: Install units and verify scheduled runtime safely.**

  Run, as root on the VPS:

  ```bash
  /opt/finanse/ops/systemd/install-timers.sh
  systemctl list-timers --all finanse-backup.timer finanse-restore-verify.timer
  systemctl start finanse-backup.service
  systemctl is-active --quiet finanse-backup.timer
  systemctl status finanse-backup.service --no-pager
  ```

  Expected: both timers are enabled; the backup service exits successfully; a
  new Restic snapshot is listed. Do **not** start the monthly restore service
  until the backup snapshot and service logs are confirmed.

- [ ] **Step 4: Run the real isolated drill and validate cleanup.**

  Run:

  ```bash
  systemctl start finanse-restore-verify.service
  systemctl status finanse-restore-verify.service --no-pager
   test -d /docker/finanse/data/restore-drill
   test -z "$(find /docker/finanse/data/restore-drill -mindepth 1 -print -quit)"
  set -a; . /docker/finanse/.env; set +a; docker exec finanse-postgres psql -U "$POSTGRES_USER" -d postgres -tAc "SELECT 1 FROM pg_database WHERE datname = 'finanse_restore'" | test -z
  journalctl -u finanse-restore-verify.service -n 100 --no-pager
  ```

   Expected: service exits successfully; the root-owned persistent parent is
   empty, the isolated database is absent, and logs show verification completion
   with no secret values.

- [ ] **Step 5: Update delivery documentation and commit.**

  Mark the scheduler task complete in `TASKS.md`; record schedules, snapshot
  ID, drill result, installed timer names and any warning in `JOURNAL.md`; add
  the feature and verification to `CHANGELOG.md`. Do not include credentials.

  ```bash
   git add docs/operations/backup-restore.md docs/CHANGELOG.md docs/TASKS.md docs/JOURNAL.md docs/superpowers/specs/2026-08-20-automated-backup-restore-design.md docs/superpowers/plans/2026-08-20-automated-backup-restore.md
  git commit -m "docs: opisz automatyczne backupy produkcyjne"
  ```

## Plan self-review

- **Spec coverage:** Task 1 implements persistent Warsaw timers, shared locking,
  hardening and journal failure events. Task 2 implements the exact isolated
  restore invocation and verified cleanup. Task 3 provides deliberate root-only
  installation. Task 4 documents, tests and executes the operational proof.
- **No-secret boundary:** unit files and Git contain no provider credentials;
  Makefile is the only external configuration boundary; tests inspect units for
  common secret assignments.
- **Safety:** production drills run only through the installed systemd wrapper,
  which alone creates and removes `finanse_restore`. `RESTORE_SNAPSHOT_ID` is
  the only internal restore selector and the legacy
  `snapshot=` assignment fails before a runner or Restic process can start. The
  wrapper creates only the literal guarded `finanse_restore`
  target, and ownership-aware cleanup removes its exact database and outputs
  after success or verifier failure. The installer installs the root-owned
  wrapper outside the repository and retains the empty sandbox parent.
- **Known implementation decision:** `ProtectSystem=strict` and
  `ReadWritePaths` require the live manual service run in Task 4; if Docker or
  Restic needs another write location, add only that exact location, document
  it and add a regression assertion before rerunning the service.
- **Cache hardening:** units and Make use the root-owned `0700`
  `/docker/finanse/data/restic-cache`, preserving `ProtectHome=true` and
  avoiding any cache write below `/root`.
- **Final runtime evidence:** `snapshot=deadbeef` returned code 2 with an
  invalid `PATH`, proving rejection before runner/Restic. The hardened services
  then created snapshot `11fd2129` and completed the real isolated drill with
  an empty `root:root` `0700` parent and no `finanse_restore` database.
- **Cache runtime evidence:** installer created `restic-cache` as `root:root`
  `0700`; snapshot `a6e89e9d` and the real service drill succeeded, and the
  drill journal window contained no `unable to open cache` entry.
