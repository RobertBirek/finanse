# Kontrolowana reorganizacja drzewa kategorii

Status: narzędzie operatorskie; **nie jest zgodą na produkcyjny APPLY**.
Projekt i plan: `docs/superpowers/{specs,plans}/2026-11-06-category-tree*.md`.
Zgoda na wykonanie planu obejmuje implementację, testy, próbę na kopii i odczyt
produkcji. Nie obejmuje maintenance, zatrzymania aplikacji ani zmian jej danych.

## Granica operacji

- Zachować 65 istniejących ID; dokładnie 30 minimalnych aktualizacji i 14 nowych
  kategorii expense, razem 79 (73 expense / 6 income).
- 38 zmian ścieżek nie oznacza 38 aktualizacji: osiem dzieci dziedziczy wyłącznie
  zmianę nazwy rodzica. 35 oryginalnych wierszy, w tym KEEP/HOLD, pozostaje nietknięte.
- Zero zmian typu, źródła Actual, aktywności, kwot, dat, FX, postings, kont,
  budżetów, harmonogramów, alokacji, dokumentów, reguł, zgód lub polityk.
- Przeniesienie kategorii zmienia prezentację historycznych raportów i skład grup,
  nie wartości transakcji. Nie obiecywać identycznych sum per grupa.
- Import Actual zakończony dla właściciela. Mapowania/importer zostają bez zmian;
  ponowny import dawnych grup ma bezpiecznie odmówić konfliktu.

## Prywatne wejście i runtime

1. Potwierdzić właściciela i stały `operation_id` w prywatnym zapisie. Nie wybierać
   właściciela przez „pierwszy użytkownik”, nie umieszczać UUID/nazw w Git/stdout.
2. Prywatny pakiet projektu: `/opt/finanse/webapp/category-designs/2026-11-06/`.
   Katalog 0700, pliki 0600, właściciel UID operatora. Weryfikowane SHA źródła,
   mapowania i propozycji pochodzą z zatwierdzonego planu, nie z nowego wyliczenia
   nad zmienionymi plikami. Manifest ma dokładnie pięć znanych plików.
   `prepare_design.py` jest wyłącznie hashowany — nigdy uruchamiany/importowany.
3. Odczytać `active-release.json`, obrazy/etykiety żywych kontenerów i schemat bazy;
   porównać z testowanym runtime. Nie zakładać zgodności starego helpera wdrożeniowego.
4. Przygotować osobny root-only operator bundle z **wyłącznie czterema plikami**:

   ```text
   scripts/category_tree_manifest.py
   scripts/category_tree_guard.py
   scripts/category_tree_apply.py
   scripts/category_tree.py
   ```

   Nie dodawać `scripts/__init__.py`, zależności, hostowego `/app`, portów ani
   prywatnych danych do paczki. Digest to SHA256 kanonicznego JSON
   `{filename: SHA256(bytes)}`, z sortowaniem kluczy i separatorami `,` / `:`;
   oblicza go `operator_digest()` w CLI. Zmiana jednego bajtu wymaga nowych testów,
   próby i nowej zgody/digestu. Nie jest to hash pliku tar.
5. Uruchamiać w potwierdzonym niezmiennym obrazie backendu z read-only mount
   `/release-ops` i `PYTHONPATH=/release-ops:/app`. Bez uruchamiania FastAPI lifespan,
   ARQ, crona, OCR, modeli, importerów lub reconcilerów. Przykładowy one-off ma
   entrypoint `python`, nie entrypoint aplikacji.
6. Prywatny env podaje `DATABASE_URL` i **identyczny bajtowo**
   `CATEGORY_TREE_DATABASE_URL`, oraz potwierdzone `CATEGORY_TREE_RUNTIME_REVISION`
   i `CATEGORY_TREE_RUNTIME_IMAGE`. Obrazy/revision operator potwierdza przez Docker;
   env jest atestacją operatora, nie zdalnym pomiarem. Nie drukować URL/sekretów.
   Nigdy nie kopiować produkcyjnego URL do środowiska testów pytest.

## Polecenia

Wszystkie wartości w nawiasach to prywatnie potwierdzone dane, nie wartości domyślne.
Wspólne argumenty:

```text
--bundle-dir <private-design-dir> --owner <owner-uuid>
--operation-id <stable-operation-uuid> --report-file <new-private-report.json>
--source-sha <approved-source-sha> --mapping-sha <approved-mapping-sha>
--proposal-sha <approved-proposal-sha> --actual-migration-closed
--statement-timeout-ms <configured-positive-int>
```

```text
python -m scripts.category_tree --preflight <common-arguments>
python -m scripts.category_tree --verify <common-arguments>
python -m scripts.category_tree --apply <common-arguments>
  --lock-timeout-ms <configured-positive-int>
  --expected-report <fresh-private-preflight.json>
  --approval-file <separate-scope-specific-approval.json>
  --operator-sha <tested-operator-digest>
```

Bez trybu domyślnie preflight. Tryby są wzajemnie wykluczające się. Bez zgody APPLY
lub bez zgodnego URL następuje odmowa przed połączeniem operatorskim. Nowy plik
raportu powstaje 0600/O_EXCL w katalogu 0700 — nie nadpisywać wcześniejszych dowodów.
W stdout wyłącznie statusy/kody. Szczegóły kategorii/ID/liczniki/fingerprinty pozostają
w prywatnych raportach. Nie kopiować tracebacków SQLAlchemy do publicznego zgłoszenia.

Preflight: REPEATABLE READ READ ONLY, statement timeout, zawsze rollback; nie tworzy
ustawień/zgód/audytów. Verify: READ COMMITTED READ ONLY, nieblokujące locki
`actual-import:{owner}` → `category-tree:{owner}`, dopiero potem świeży SELECT receipt.
APPLY: SERIALIZABLE, ta sama kolejność locków, blokada wierszy kategorii, ponowna
weryfikacja zamrożonego preflight, istniejące serwisy domenowe, 45 audytów i jeden
`FinanceCommandReceipt` w jednej transakcji. Commit wykonuje wyłącznie CLI.

### Odmowy i statusy

STOP przy dowolnej zmianie drzewa/ref/grantu od preflight, obcym ownerze referencji,
nowym nieobsługiwanym FK do categories, innym schemacie, niezbilansowanym ledgerze,
otwartym imporcie Actual, markerze/regułach/consent, regułach/origin/propozycjach/
produktach lub aktywnej pracy dokumentów/receipt/suggestions/rules.
Nie kasować dowodów, nie wyłączać zgód i nie naprawiać kopii tylko po to, by uzyskać PASS.

`--verify`: applied=0; not_applied=3; busy_or_conflict=4;
applied_state_changed=5; receipt_conflict/invalid input=2.
Preflight z blokerami=2. Inny błąd/interrupt/utrata odpowiedzi oznacza wynik nieznany,
nie zapewnienie rollbacku: połączenie mogło zakończyć COMMIT przed utratą odpowiedzi.
Żaden status verify nie nadaje nowej zgody APPLY.

## Format oddzielnej zgody APPLY

Zgoda jest root-only atestacją rzeczywistej decyzji człowieka i dowodów operatora,
nie podpisem kryptograficznym ani grantem aplikacji. Nie tworzyć `true` bez decyzji.
Wersja 1 wymaga dokładnie pól:

```text
version: 1
scope: category_tree_apply_v1
production_apply_approved: true
identity: <dokładna identity z aktualnego preflight + preflight_sha>
issued_at: <UTC ISO8601>
max_age_seconds: <jawnie skonfigurowany dodatni integer>
evidence:
  backup_restore: {path: <private-proof>, sha256: <sha256-bytes>}
  rehearsal: {path: <private-proof>, sha256: <sha256-bytes>}
  fence: {path: <private-proof>, sha256: <sha256-bytes>}
```

`identity`: owner, operation_id, source_sha, mapping_sha, proposal_sha,
before_fingerprint, operator_sha, runtime_revision, runtime_image, schema_revision,
target_sha, preflight_sha. `target_sha` wiąże dokładny URL i schemat (hashe są prywatne).
Każdy proof zawiera kind, passed=true, tę samą identity i issued_at; backup_restore
także snapshot_sha (pełny SHA256 snapshotu). Oryginalny raport/rehearsal snapshot jest
zachowany; proof to świeże poświadczenie jego zgodności, nie przepisanie daty próby.
Wszystkie dowody i preflight mieszczą się w jawnej świeżości; przyszła data jest błędem.
CLI odczytuje je przed engine oraz ponownie bezpośrednio przed zapisami.
`design-approval-private.json` i `execution-approval-private.json` nigdy nie wystarczają.

## Izolowana próba

1. Wykonać świeży zaszyfrowany backup i weryfikację przywrócenia według
   `backup-restore.md`. Zachować manifest/checksum/snapshot oraz active-release;
   historyczne git_sha w backupie oznacza host checkout, nie aktywny obraz.
2. Użyć wyłącznie własnej nowo utworzonej, pętlowej bazy z końcówką `_restore`/`_test`.
   Restore runner ma guard 127.0.0.1 i pustego private directory. Nie kierować go do
   produkcji, public-schema wspólnego finanse_test ani istniejącej cudzej kopii.
   Installed systemd drill sam usuwa finanse_restore — nie przechwytywać go w trakcie.
   Zachowaną kopię do CLI przygotować w osobnym jednoznacznie nazwanym disposable DB,
   pod tym samym backup/restore flock, po sprawdzeniu checksum i migracji/ledgeru.
3. Pasujący immutable runtime, wyłączone klucze/AI/Redis/workery, tylko CLI. Preflight
   rzeczywistym zatwierdzonym pakietem; każdy bloker przerywa próbę bez naprawy danych.
4. Tylko kopia: `scope=category_tree_rehearsal_v1`, production_apply_approved=false,
   ta sama tożsamość/dowody; kod dodatkowo wymaga loopback DB `_restore`/`_test`.
   Ten format nie zadziała na produkcyjnym adresie. Prerequisite proof może wskazywać
   wcześniejsze syntetyczne testy operatora; nie nazywać ich próbą na realnej kopii.
5. APPLY → verify → ponowienie z tym samym kluczem, bez drugich zapisów.
   Sprawdzić 65 original / 14 new / 30 updates / 79 total, wszystkie ścieżki,
   max2poziomy, niezmienione HOLD/KEEP/ref/ledger/salda/Actual i 45audits+1receipt.
   Zachować dowód wiążący backup, runtime, schemat, input i digest operatora.
6. Jeden niezależny whole-change review i pełne gate. Po zmianie operatora
   ponowić testy i próbę; nie używać starego digestu. Świeży produkcyjny preflight
   READ ONLY nie upoważnia do APPLY. Przy blokerze przekazać jego skutek zamiast
   prosić o wykonalną zgodę produkcyjną.

## Późniejsze wykonanie produkcyjne — NIE w ramach wykonania planu

1. Przedstawić dokładny operation UUID, hash wejść/operatora/runtime/schemat,
   30updates+14creates, wpływ na historyczne grupy raportów, HOLD/KEEP, zakończenie
   Actual i zakres maintenance/recovery. Uzyskać **osobną jednoznaczną zgodę**.
2. Zachować aktywne Compose base+prod+versionedoverride, config frontend/nginx,
   ID wszystkich kontenerów i obrazów. Publiczny sprawdzony fence503; żadnej
   bezpośredniej opublikowanej ścieżki backendu. Poczekać na admitted requests,
   wymagać zera aktywnej pracy DB/Redis, nie wywoływać modeli dla opróżnienia kolejek.
3. Zatrzymać backend/worker łagodnie pełną aktywną listą Compose (nie base-only).
   Recheck durable/Redis po zatrzymaniu producentów. ARQ finished-cron dedup bez
   payload/queue nie jest aktywną pracą; realna praca=STOP. Nie usuwać kluczy ani
   resetować jobów. Dispatcher-only drain wymaga jawnej bounded same-runtime procedury.
4. Pod fence: końcowe fingerprinty, świeży zaszyfrowany backup, udowodniony restore,
   checksum/schema/ledger, aktualny no-write proof i osobna zgodna zgoda. Bez zgody
   na maintenance nie wykonywać tych kroków produkcyjnych.
5. Dokładnie jeden APPLY w compatible one-off. Pre-COMMIT wyjątek=rollback;
   timeout/unknown=READ ONLY verify, nie blind retry/nowy UUID/usuwanie receipt.
6. Przed otwarciem: DB proof79paths/65IDs/35untouched/HOLD/KEEP/ref/mappings/ledger/
   45audits+1receipt. Restart oryginalnych backend/worker, te same obrazy/config,
   bez recreacji frontend. Internalhealth/logs/worker, brak niespodziewanych zadań.
   Przywrócić zapisany nginx config, nginx -t/reload, publicHTTPS200 i anonymous401.
   UI tylko prawdziwą sesją użytkownika/manualnie; bez fałszowania sesji/auth override.
7. Jeśli błąd po COMMIT: utrzymać maintenance, zachować nowe kategorie/receipt/dowody,
   eskalować do jawnego repair-forward. Zero automatycznego DELETE, cofania kategorii,
   omijania importera, downgrade lub restore produkcji. Backup nie jest domyślną
   zgodą na niszczące odzyskiwanie.
8. Prywatny wynik i docs-only handoff. To operacja danych, nie wydanie aplikacji:
   nie zmieniać active release/Compose metadata. Brak merge/push/deploy.
