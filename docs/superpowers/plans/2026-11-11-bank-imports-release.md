# Bezpieczne wydanie importerów A+B — Implementation Plan

**Wykonanie P, 2026-11-11: NO-GO.** Po osobnym „tak” Task 1 wykonano,
Task 2 zatrzymano na ingress: nowy upload 2 MiB →413 w obu wariantach slash.
Pakiet i trzy obrazy zbudowane offline; Task 3 nie rozpoczęto. Checkboxy poniżej
opisują pierwotny runbook; stan wykonania i dowody:
[`2026-11-11-bank-imports-preparation.md`](../../audits/2026-11-11-bank-imports-preparation.md).
Brak zgody D, backupu, restore, migracji lub deployu. Wznowienie wymaga osobnej
decyzji o poprawce/new SHA, a nie obejścia probe.

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Wydać odebrane lokalnie importery A+B, zachowując istniejące dane i możliwość bezpiecznego wycofania aplikacji, bez importu rzeczywistych dokumentów w ramach deployu.

**Architecture:** Wersjonowane obrazy backend/worker/frontend, istniejący Docker Compose i npmplus. Dwa addytywne upgrade’y PostgreSQL poprzedza odtworzenie backupu na własnym, izolowanym PostgreSQL. Bramka przygotowania i bramka produkcyjna są oddzielnymi zgodami; rollback zależy od rzeczywistego stanu danych, nie tylko schematu.

**Tech Stack:** Git, PostgreSQL16, Alembic, Docker Compose, Restic, istniejące `ops/prepare_release.py`, `ops/verify_release.py`, `ops/backup.sh` i Vite dist.

**Spec:** Zatwierdzone w rozmowie przygotowanie planu bez zmian produkcji; `docs/operations/backup-restore.md`, `.opencode/command/deploy.md`, `docs/operations/bank-imports.md`, `docs/superpowers/specs/2026-11-08-bank-statements-and-loan-schedule-import-design.md`. Odbiór: `docs/audits/2026-11-08-loan-schedule-import-local.md`.

## Global Constraints

- Obecne „ok, działaj” dotyczy **napisania planu**, nie wykonania jego kroków operacyjnych.
- Teraz wykonano jedynie odczyt Git, metadanych kontenerów/release’u i dwóch zapytań metadanych DB w trybie read-only. Nie wykonano backupu, klonowania, buildów obrazów, migracji, restartu, merge lub push.
- **Zgoda P** przed Task1–3: przygotowanie artefaktów, backup przez istniejący mechanizm, odtworzenie prywatnej kopii wyłącznie do własnych zasobów bez publikowania portów, testy i późniejszy cleanup tylko tych zasobów. Bez zmiany produkcyjnej aplikacji, schematu lub danych.
- **Zgoda D** przed Task4–5: dokładny runtime SHA, Git tip, UP dwóch migracji, trzy usługi, maintenance, backup w oknie i procedura awaryjna. Brak zgody oznacza STOP po przygotowaniu.
- Nie wykonuj produkcyjnego DOWN, restore DB, DROP/TRUNCATE/masowego DELETE, napraw historii, zmian Q7/Actual lub konfiguracji Velo. Potrzebna byłaby odrębna, konkretna decyzja użytkownika.
- Nie twórz użytkownika/sesji ani nie wykonuj finansowej mutacji w produkcyjnym smoke teście. Pilotaż prawdziwego pliku pozostaje osobną decyzją.
- Nie wypisuj sekretów, surowego backupu, danych klientów lub wyrenderowanego Compose. Prywatne artefakty poza Git: katalog0700, pliki0600. Publiczny raport zawiera wyniki, hashe i identyfikatory, nie treść danych.
- Nie zmieniaj uprawnień oryginalnych uploads. Normalizacja dotyczy wyłącznie kopii publicznego kodu/dist przygotowanej przez istniejące narzędzie release.
- Nie odtwarzaj ani nie podłączaj cudzych środowisk/testDB/preview. Nie stosuj `prune`, `--force`, samodzielnego bazowego Compose, `make up` lub `make restart`.
- Nowe aplikacje nie startują przed końcem migracji. PostgreSQL/Redis/Stirling, sieci, sekrety i istniejące ustawienia pozostają bez zmian.

## Review Focus

1. Zmiana HEAD, origin/main, obrazu lub Compose między akceptacją a APPLY: wykryć drift i zatrzymać, nigdy wdrożyć „najnowszego” zamiast zaakceptowanego — Task1/2/4.
2. Frontend zatrzymany lub odtworzony bez fence: przed migracją publiczne GET mają zwracać503 także w tej sytuacji — Task4.
3. Upload/staging/receipt bez księgowania już po otwarciu: dane nadal blokują ślepy rollback do starej aplikacji, nawet przy pustej księdze importera — Task1/3/4.
4. Nowa ścieżka uploadu nie dziedziczy wyjątku body-size Nginx: sprawdź dostarczenie2MiB i odmowę ponad21MiB dla importera oraz dotychczasowych dokumentów — Task2; żadnego wnioskowania z testów samego API.
5. Backup odtworzony do złej bazy albo cleanup cudzych danych: własne ID/etykiety/mounty/sieć, brak portów i dodatnie potwierdzenie celu przed operacją — Task3/5.

## Stan sprawdzony 2026-11-11

| Element | Zaobserwowana wartość |
|---|---|
| Produkcyjne trzy aplikacje i OCI revision | `7801ba591223c213c1fcd69a0c3ace19c81ef9db` |
| Active metadata | `verified-live`, `/opt/finanse/webapp/releases/7801ba5/compose.active.yaml` |
| Produkcyjny schemat, SELECT read-only | `739144d5eaef` |
| Tabele public bez `alembic_version` | 62 |
| Kandydat runtime | `c3069487fd8e7c23b8a0423883516768b98005d4` |
| Odbiór kodu B6 | `8e779883a009df1ce58b7997d775b20b70c25aa4`; c306948 dodaje tylko dokumentacyjne zamknięcie |
| Lokalne main i ostatnio znane origin/main | `e3c906f8a31269263d9773cd76689f59cc2f3e6b`, przodek kandydata; nie wykonano fetch |
| Różnica do main | 22commity,186plików,27618dodanych/213usuniętych linii; do runtime7801 także wcześniejszy dokumentacyjny commit produkcyjny |
| Runtime dependencies i narzędzia ops | `backend/requirements.txt`, frontend package/lock i `ops/` bez zmian względem produkcji |
| UID:GID backend/worker | zaobserwowane `10001:10001`; przed wydaniem ponownie odczytać z finalnego Compose |
| Sieci | backend/worker: internal; frontend: ingress+internal; brak host mountu `/app` |
| Odbiór lokalny | 2300backend,617frontend,183E2E PASS;14standardowo excluded proxy,0backendruntime-skips,1oczekiwanydesktopskip testu mobile-only |
| Tożsamość odbioru | 747hashźródeł i15dist; ponownie sprawdzone przy pisaniu planu |

Backend/worker/frontend działają bez restartów od poprzedniego wdrożenia. Dokumentacyjny commit `61fbee1` opisuje wcześniejsze, zatwierdzone konfigurowanie karty; ten release nie wykonuje go ponownie. Zmiany roboczych audytów spoza zaakceptowanego drzewa pozostają poza wydaniem.

Obserwacja nie jest obietnicą niezmienności: Task1 musi sprawdzić stan ponownie po zgodzie P. Jeśli remote/main lub produkcja zmieniły się, odnowić porównanie i zakres akceptacji.

### Ryzyko ingress wykryte podczas planowania — bramka NO-GO do sprawdzenia

`frontend/nginx.conf` zawiera wyjątek21MiB tylko dla `/api/documents/upload/?$`,
a nowy upload `/api/finance/imports/{batch_id}/sources` trafia do zwykłego `/api/`.
Istniejący `test_documents/test_proxy_upload.py` testuje tylko starą ścieżkę;
14testówproxy było standardowo wyłączonych w pełnym odbiorze backendu.
To wskazuje ryzyko413 dla większych plików importera, ale w tej sesji nie uruchomiono
kontenera/proxyprobe i nie deklarujemy jeszcze odtworzonego błędu runtime.
Task2 ma obowiązkowo sprawdzić ten kontrakt przed zgodą D. Jeśli test zawiedzie,
**c306948 nie jest kandydatem do produkcyjnego wydania**: STOP, raport i osobna
decyzja o małej poprawce RED→GREEN, nowym SHA oraz odnowieniu freeze/bramek.
Nie zmieniaj limitu całego `/api/` i nie wdrażaj „z zastrzeżeniem”.

### Dokładne migracje

`739144d5eaef → 6bd8758ebc7d → 84fdbd10aa18`.

- `6bd8758ebc7d_bank_import_staging.py`:11tabel `bank_import_*`, owner-constraint dokumentów i rozszerzenie istniejącego checka `processing_method` o `bank_import`.
- `84fdbd10aa18_loan_schedule_revisions.py`:2tabele wersji/membership, dodatkowe klucze owner/loan oraz nullable `active_schedule_revision_id` i `superseded_by_revision_id`.
- Brak backfillu umów/rat, sald lub spłat. Po pustym upgrade oczekujemy75tabel public poza `alembic_version`,13nowych tabel pustych, obu nowych kolumnNULL i niezmienionych62starych tabel po projekcji ich dawnych kolumn.
- A odmawia downgrade po dowolnym stagingu lub dokumencie `bank_import`; B odmawia po wersji/membership lub ustawionych pointerach. Samo dodanie pliku może zamknąć bezpieczną drogę powrotu starej aplikacji, zanim powstaną postings.

## Artefakty i odpowiedzialności

Repozytorium: tylko ten plan oraz aktualizacje CHANGELOG/TASKS/JOURNAL. Nie zmieniamy aplikacji ani migracji na potrzeby tego planu.

Po zgodzie P użyj nowego prywatnego katalogu dowodów pod `/tmp/opencode/bank-imports-release-c306948-<losowy_suffix>/`, zapisz jego pełną ścieżkę jako `E`. Pakiet `R` pod `/opt/finanse/webapp/releases/bank-imports-c306948-<ten_suffix>/` musi nie istnieć przed utworzeniem. Zmienne są pełnymi ścieżkami wybranymi raz w Task1, nie globami lub aliasem `latest`.

- `E/freeze.json`: SHA aplikacji i Git tip,747sourcehash,15dist, hashe migracji/skryptów, obrazów, pełnej listy Compose; bez sekretów.
- `E/inventory.private.json`: dokładne image/containerIDs, UID:GID, mounts/sieci/env i config bazowy do porównania; nie publikować.
- `E/release_policy.py`, `E/test_release_policy.py`: małe, izolowane guardy; nie wdrażają, nie uruchamiają SQL/Dockera, nie czytają sekretów.
- `E/test_import_ingress.py`, `E/ingress-proof.json`: syntetyczny, jednorazowy proxyprobe dokładnego Nginx z pakietu, we własnym namespace bez portów hosta; localhoststub204 zamiast rzeczywistego API, żadnych danych użytkownika.
- `E/resources.private.json`: tylko nowo utworzone zasoby rehearsal/fenced, ich ID/etykiety/mounty i własne credentiale testowe. Nie kopiować produkcyjnego env do runnera.
- `E/rehearsal/`, `E/fenced/`: manifesty snapshotów, hashe danych/uploads, kontrola migracji, zgodność starego runtime i księgi. Surowe dane pozostają prywatne.
- `E/offline-import-proof.json`, `E/compose.private.json`, `E/approval-D.json`, `E/final-proof.json`: dowody dokładnego kandydata i wykonanych zgód.
- `R/release.json`, Dockerfiles, `compose.release.yaml`, `source/`, `frontend-dist/`: wyłącznie wynik `ops/prepare_release.py`.
- Produkcyjne active metadata aktualizuj atomowo dopiero po końcowej weryfikacji; nie nadpisuj starego override, obrazów lub dowodów.

---

### Task 1: Zgoda przygotowania, zamrożenie zakresu i guardy

**Files:** Create `E/{freeze.json,inventory.private.json,release_policy.py,test_release_policy.py,resources.private.json}`. Read plan, bieżące active metadata, Git, zaakceptowane archiwum odbioru. Bez zmian plików produkcyjnych.

**Interfaces:** Consumes runtime SHA c306948 i odbiór747hash. Produces `check_freeze(expected: dict[str, object], observed: dict[str, object]) -> None` (różnica/brak pola: `RuntimeError`) oraz `select_rollback(evidence: dict[str, object]) -> Literal['app_only','stop']`; `freeze.json` z polami `runtime_sha`, `git_tip`, `schema_from`, `schema_to`, `source_hashes`, `dist_hashes`, `image_ids`, `compose_hashes`, `data_container_ids`.

`select_rollback` czyta wyłącznie komplet kluczy `schema_head`, `fenced`, `writers_stopped`, `old_runtime_on_current_schema_passed`, `old_image_ids`, `import_table_counts`, `bank_import_documents`, `import_command_receipts`, `active_schedule_pointers`, `superseded_pointers`. Tablecounts muszą zawierać dokładnie11tabel A i2B wymienionych przez migracje; każda wartość to int0, nie bool/null/string. Trzy booleany muszą być `True`; `old_image_ids` zawiera dokładne trzyIDs powiązane przez `check_freeze` z inventory. Nieznane/dodatkowe stany nie rozszerzają uprawnień. Fixture `empty_schema84_evidence()` w pliku testowym tworzy jawny taki komplet dla schema84 i syntetycznychIDs, bez Dockera lub DB.

- [ ] **Step1: Zgoda P.** Pokaż użytkownikowi zakres Task1–3, w tym odczyt backupu prywatnych danych i nowe własne PG/runner bez portów. Expected: jednoznaczna zgoda; bez niej niczego nie twórz poza dokumentacją.
- [ ] **Step2: Powtórz inventory i źródła.** Fetch wyłącznie po zgodzie P; ustal aktualne main/origin/main i pełną różnicę. Zapisz docelowy `git_tip` obejmujący plan, ale runtime pakietu pozostaje przypięty do c306948. Potwierdź brak produktowych zmian między nim a tipem. Expected:747hash i15dist zgodne z dowodami; main FF-compatible; schema739. Przy innym stanie STOP i ponowne ustalenie zakresu, nie automatyczne merge/rebase.
- [ ] **Step3: RED guardów.** Testy `test_freeze_rejects_sha_image_and_compose_drift`, `test_rollback_refuses_missing_or_failed_counts`, `test_rollback_refuses_staging_upload_receipt_and_schedule_data`, `test_rollback_requires_fence_idle_and_old_runtime_proof`. Run: `python3 -B -m unittest discover -s "$E" -p 'test_release_policy.py' -v`. Expected: FAIL z powodu braku guardów, nie błędnych fixture.
- [ ] **Step4: Implementuj pure guardy.** `check_freeze` wymaga pełnych pól i dokładnej zgodności. `select_rollback` zwraca `app_only` tylko dla sprawdzonej schema84, potwierdzonych503 i bezczynności/zatrzymania writerów, znanych exactoldimageIDs, proof zgodności starego runtime z bieżącym schematem oraz kompletu zerowych13tabel, bank_importdocuments, importowychcommandreceipts i obu pointerów. Brak/nieudane zapytanie nie oznacza zera. Inny stan zwraca `stop`; żadnego DOWN/restore. Przed UP na739 nie ma rollbacku nowej aplikacji: pozostaje sprawdzony, niezmieniony oldstack.
- [ ] **Step5: GREEN i kontrakt.** Ta sama komenda, Expected: PASS; dodatkowo świadomie uszkodzony SHA w kopii freeze daje odmowę przed jakąkolwiek akcją. Zachowaj wynik i hashe guardów. To nie jest jeszcze zgoda na produkcyjny rollback.

  Minimalne asercje kontraktu (w metodach `unittest.TestCase`, fixture niezależna od implementacji guardu):

  ```python
  evidence = empty_schema84_evidence()
  self.assertEqual(select_rollback(evidence), "app_only")
  self.assertEqual(select_rollback({**evidence, "fenced": False}), "stop")
  self.assertEqual(select_rollback({**evidence, "bank_import_documents": 1}), "stop")
  self.assertEqual(select_rollback({**evidence, "import_command_receipts": 1}), "stop")
  self.assertEqual(select_rollback({**evidence, "active_schedule_pointers": 1}), "stop")
  self.assertEqual(select_rollback({**evidence, "schema_head": "6bd8758ebc7d"}), "stop")
  self.assertEqual(select_rollback({**evidence, "import_table_counts": {}}), "stop")
  self.assertEqual(select_rollback({**evidence, "import_table_counts": None}), "stop")
  ```

  Pozostałe testy zmieniają kolejno każdą tabelę, każdy wymagany klucz, proof starego runtime, flagę writerów oraz pola freeze. Expected: odmowa dla każdego pojedynczego naruszenia; fixture zawsze ma dodatni przypadek odniesienia.

### Task 2: Dokładny pakiet, runtime i offline import

**Files:** Create `R/*`, `E/{built-images.json,offline-import-proof.json,compose.private.json}`. Read istniejący aktywny pakiet7801. Nie stosuj Compose do usług.

**Interfaces:** Consumes freeze i guardy z Task1. Produces trzy resolvedimageIDs przypięte do c306948, offline proof dla finalnych numerycznych users i zamrożony pełny Compose.

- [ ] **Step1: Zachowaj rollback7801.** Zapisz obecne trzy imageIDs i aktywny override7801. `active-release.json` wskazuje też historyczny rollback020c229: **nie jest to cel rollbacku tego wydania**. Nie uruchamiaj starego skryptu downgrade klasyfikacji kart.
- [ ] **Step2: Przygotuj pakiet istniejącym narzędziem.** Po przypięciu aktualnych lokalnych runtime tags do zapisanych IDs uruchom:

  ```bash
  python3 ops/prepare_release.py --repository "$REPO" \
    --revision c3069487fd8e7c23b8a0423883516768b98005d4 \
    --runtime-revision 7801ba591223c213c1fcd69a0c3ace19c81ef9db \
    --output "$R" --frontend-dist "$ACCEPTED_DIST" \
    --backend-runtime "$PINNED_BACKEND_RUNTIME" \
    --worker-runtime "$PINNED_WORKER_RUNTIME" \
    --frontend-runtime "$PINNED_FRONTEND_RUNTIME"
  ```

  Expected: nowy pakiet, exactc306948, zgodne requirements i15dist; żadnego apply. Zmienne runtime to jawne lokalne tagi sprawdzone względem IDs z freeze, nie `latest`.
- [ ] **Step3: Build bez sieci.** Trzy Dockerfiles, `--network=none`, dokładne tagi z `release.json`; po każdym build zapisz ID/OCIrevision. Expected: źródła zgodne, frontend sprawdza odczyt jako nginx. Zmiana dependencies lub brak bazowego obrazu oznacza STOP, nie pull lub fałszowanie runtime-revision.
- [ ] **Step4: Zamroź finalny Compose.** Obecny stack używa base+prod+active7801. Dla kandydata zachowaj te trzy warstwy i dodaj nowy `R/compose.release.yaml` na końcu; prywatny render musi dowieść, że poza zatwierdzonymi image/build wszystkie ustawienia/env/users/sekrety/zasoby/sieci/mounty są zgodne z inventory. Wykryte skutki merge `!override` oznaczają STOP i poprawkę pakietu, nie zmianę działającego stacka. Brak `/app` bind; uploads nadal ten sam, data services nietknięte.
- [ ] **Step5: Obowiązkowy verifier.** Run `python3 ops/verify_release.py --release "$R" --backend-user "$FINAL_BACKEND_UID_GID" --worker-user "$FINAL_WORKER_UID_GID" --timeout 60 > "$E/offline-import-proof.json"`. Expected: exit0/passed dla dokładnychIDs; nonroot users z finalnego renderu. Timeout/import/read-access/root oznacza STOP. Nie podłączaj produkcyjnego env/DB; verifier nie uruchamia lifespan/workera.
- [ ] **Step6: Próby odmowy i ingress.** Na kopiach metadata sprawdź guard dla zmienionego imageID, użytkownika i hasha Compose; każda musi odmówić. Nie retaguj aktywnych obrazów i nie uruchamiaj zmienionej kopii. Osobny `python3 -B -m unittest discover -s "$E" -p 'test_import_ingress.py' -v` ma używać własnego, oznaczonego Nginx/runner namespace bez sieci zewnętrznej i bez portów hosta, lokalnego już dostępnego obrazu (bezpull) oraz syntetycznego upstreamstub204. Dla starego `/api/documents/upload` i nowego `/api/finance/imports/00000000-0000-0000-0000-000000000001/sources`, z i bez slash:2MiB→204,21MiB+1→413. Sprawdź też, że zwykłe nieuploadowe `/api/` nie otrzymało szerszego limitu. To test proxy, nie parsera/auth. Dotychczasowy harness publikuje port i używa `rm -f`: nie uruchamiaj go pod zgodą „bezportów/bezforce”; nowyprobe ma cleanup po exactID i bezforce. Jeśli nowa ścieżka daje413 już przy2MiB, STOP przed Task3/D, raport niezgodności i osobna decyzja o poprawce/newSHA. Nie obchodź wyniku zmniejszeniem testowego pliku lub limitem globalnym.

### Task 3: Backup, odtworzenie i migracje wyłącznie na własnych klonach

**Files:** Create `E/rehearsal/*` oraz dokładne wpisy zasobów w `E/resources.private.json`. Read `ops/backup.sh`, backup manifest i oba migrationfiles. Nie używaj zajętych cudzych testDB ani istniejącego finanse_restore.

**Interfaces:** Consumes exactimages/freeze. Produces `rehearsal/proof.json`: snapshotID/checksumy, własne resourceIDs, schema739→84, hash retencji62tabel,13nowychpustych, nowe kolumnyNULL, ledger invariants, uploadsidentity i `old_runtime_on_new_schema_passed`.

- [ ] **Step1: Świeży backup.** Uruchom istniejący, blokowany mechanizm `make -C /docker/finanse backup`, zgodnie z backup-restore.md, po zgodzie P. Expected: zaszyfrowany snapshot z dokładnymID, SHA źródła i schema739, checksumdump/uploads. Błąd backupu kończy przygotowanie; nie zastępuj go „jest plik”.
- [ ] **Step2: Własne środowisko.** Utwórz nowy PG16 `--network none`, bez portów, i runner w jego namespace. Losowe nazwy/etykiety/credentiale, własny wolumen; zapisz dokładneIDs/mounty przed użyciem. Runner nie dostaje produkcyjnego URL/env ani dostępu do oryginalnych uploads. Rozpakowanie backupu odbywa się w prywatnym obszarze, nie przez kopiowanie sekretów Restic do aplikacji.
- [ ] **Step3: Restore i baza odniesienia.** Najpierw checksumy i bezpieczne sprawdzenie archiwum, potem `pg_restore --no-owner --no-privileges` wyłącznie na nowym własnym klonie; bez `--clean` na istniejącym celu. Proof dodatnio potwierdza targetID/label, nazwęDB z `_restore`, brak portów i schemat739. Hashuj wszystkie62tabele według dawnych kolumn oraz uploads; prywatne wartości nie wychodzą do logu.
- [ ] **Step4: Próba migracji.** Na klonie exactnewimage wykonuje739→6bd→84. Expected:75tabel,13nowych pustych, pointersNULL,62legacyhashidentyczne, Actual/linki/UUID/kwoty/konta niezmienione; każdy transaction min2postings i sumabasePLN=0. Nowych kolumnNULL nie uznaj za zmianę dawnych danych. Nie uruchamiaj pełnego workera ani AI na klonie danych użytkownika.
- [ ] **Step5: Sprawdź obie drogi w izolacji.** Na pustym stagingu klonu wykonaj84→6bd→739→84 i ponownie potwierdź retencję. Następnie exactoldbackend7801 ma czytać istniejące dane na84 bez zapisu, wobec własnegoPG/klonuuploads; wynik pozostaje prywatny, raport tylkoPASS/hashes. To jest wymagany dowód dla app-onlyrollback, nie założenie o „addytywności”.
- [ ] **Step6: Granice retencji na osobnej syntetycznej DB.** Istniejące testy `test_bank_imports/test_migration.py` i `test_loan_schedule_import/test_migration.py` dowodzą odmowy DOWN po danych. Połącz je z guardem Task1: pojedynczy stagingbatch, dokumentbank_import, commandreceipt lub planpointer daje `stop`. Nie dosiewaj takich danych do klonu służącego porównaniu z produkcją.
- [ ] **Step7: Review i podsumowanie przygotowania.** Jeden świeży read-only review obejmuje zamrożone guardy operatora, pełny Compose/fence, kontrakt backup/restore/rollback i dowody dokładnych obrazów **przed** pytaniem o zgodę D. Nie zastępuje go review aplikacji B6. Uwagi Critical/Important wymagają RED→GREEN i odnowienia właściwych proofów; bez drugiego review lub automatycznego APPLY. Expected: snapshotodtworzony/retencja/oldruntimeproof/guardtests/offlineimports/ingressPASS i brak nierozwiązanych Critical/Important, bez skutków na produkcji. Zapisz ograniczenia i dokładny zakres zgody D. Niepowodzenie pozostawia NO-GO, nie „wydanie z zastrzeżeniem”.

### Task 4: Zgoda produkcyjna, fence i jednokrotny UP

**Files:** Create `E/{approval-D.json,fenced/*,migration-proof.json,applied.json}`; po sukcesie nowy activeoverride i metadata. Wykorzystaj, nie nadpisuj, zachowane artefakty7801.

**Interfaces:** Consumes Task1–3 oraz nową zgodę D. Produces działający spójny stackc306948 na84 albo maintenance+udokumentowaną bezpieczną decyzję awaryjną. Nie ma automatycznego rollbacku schematu.

- [ ] **Step1: Pokaż zgodę D i czekaj.** Musi zawierać runtimeSHA c306948, dokładny Git tip do FF/push,739→6bd→84, trzy usługi, maintenance, backup w oknie, app-onlyrollback wyłącznie przy dodatnim guardzie, brak DOWN/restore/importu. Bez tej zgody nie aktualizuj main/remote ani produkcji.
- [ ] **Step2: Git i ostatni freeze.** Po zgodzie D odśwież refs; FF/push tylko zaakceptowanego tipa, bez rebase/force. Przy driftźródeł/obrazów/env/Compose/schema/HEAD STOP; nie przenoś starego proof na zmienione artefakty. Publiczny render nadal ten sam, a meta7801 nie nadpisane.
- [ ] **Step3: Fence, także dla zatrzymanego frontendu.** Udowodnij503 na publicznych wejściach, potem czekaj na bezczynność i łagodnie zatrzymaj oldbackend/worker. Przed migracją próba wariantu „frontend był zatrzymany” musi przejść w izolacji: uruchomiony właściwy frontend z maintenance, a nie pominięty fence. Nie wymuszaj zakończenia aktywnych zadań; przy przekroczeniu jawnie zatwierdzonego budżetu drenażu STOP.
- [ ] **Step4: Świeży fencedbackup i druga próba.** Dopiero po503 i zatrzymaniu writerów nowy backup. Odtwórz do drugiego własnegoPG, porównaj ze zamrożonym źródłem/plikami i powtórz Task3kontrole. Nie używaj jako fencedproof wcześniejszego snapshotu wykonanego przy działającym workerze. Expected: danezgodne, źródłoschema739, oldruntimecompatPASS, brak driftu.
- [ ] **Step5: Migracja produkcyjna.** Dokładny zaakceptowany imageID/user/env/mounty z finalnegoCompose; osobny deterministycznie nazwany kontener, nie `--rm`, nie startupnowegoworkera. Jedno `alembic upgrade 84fdbd10aa18` przez zatwierdzony workflow `/migrate`, nie niejawny skrypt na starcie. ZapiszID/command/exit/state i potwierdź zatrzymanie migratora. Expected:84,13nowychpustych,62legacyhash/ledger/uploads bez zmian. Brakzgodności: utrzymaj503, nie uruchamiaj aplikacji.
- [ ] **Step6: Spójne trzy aplikacje za fence.** Pełna zamrożona lista Compose z Task2; `up -d --no-deps --no-build` tylko backend/worker/frontend. Żadnego odtwarzania PG/Redis/Stirling. Expected: dokładneimageIDs/c306948, numeryczneusers backend/worker, zachowaneenv/sieci/mounty/dane, brakhostbind/app, healthwewnętrznePASS; worker zna importercron, tabelejużistnieją.
- [ ] **Step7: Gałąź awaryjna jest warunkowa.** Przed każdą próbą cofnięcia zachowaj503, zatrzymaj writerów, wykonaj aktualny snapshot i odczyt guardów. Gdy pełnydowód daje `app_only`, przywróć dokładne7801images+zachowanyoverride, zachowując schema84 i wszystkie bieżące dane; sprawdź przed otwarciem. Gdy istnieje staging/importdocument/receipt/plan albo proof jest niepełny, pozostaw503 i uzgodnij fix-forward. Nie uruchamiaj historycznego rollback020c229, DOWN lub restoreprodukcji. Przy schema6bd po niepełnej operacji także STOP, dopóki nie ma osobnego dowodu/zgody.

### Task 5: Otworzenie, obserwacja, raport i cleanup

**Files:** Create `E/{public-smoke.json,observation.json,final-proof.json,cleanup-proof.json}`; Modify `docs/CHANGELOG.md`, `docs/TASKS.md`, `docs/JOURNAL.md`; Create `docs/audits/2026-11-11-bank-imports-production.md` dopiero po wykonaniu wydania.

**Interfaces:** Consumes pozytywne Task4proofy; produces verified-live albo jawną odmowę otwarcia. Zatwierdzone ważne parametry obserwacji zapisz w approvalD: rekomendowane300s/co10s, HTTPtimeout5s; dostosowanie wymaga jawnego zapisu, nie zmiany aplikacyjnych limitów.

- [ ] **Step1: Przed otwarciem.** Backend/worker zdrowe, obaAPIentrypointy poprawne, finalschema84, brak zmian istniejących danych, dataIDs zgodne, offlinetestIDs=deployedIDs. Expected: wszystkie kontrolePASS; dopiero wtedy zdejmij503.
- [ ] **Step2: Publiczny smoke tylko GET.** HTTPS `/api/health`200, login/statyki200 i zgodne bajtydist, anonimowe `/api/finance/imports` oraz historia wersji401, nie404/500. Browser375/1440: nowe trasy chronione loginem, brak błędówJS/overflow/obcego ruchu. Nie twórz sesji, nie uploaduj, nie aktywuj i nie księguj. Autoryzowane przepływy mają lokalne E2E; nie ogłaszaj smoke jako testu prawdziwego importu.
- [ ] **Step3: Obserwacja.** Całe zatwierdzone okno: właściweimages, zero nowychrestartów/5xx/błędówDB, niezmienione dataIDs i zdrowyRedis. Awaria lub naruszenie księgi oznacza503 i Task4Step7, nie ślepy oldimage/DOWN. Osobno sprawdź następnego dnia status/operatorlogs bez mutacji.
- [ ] **Step4: Końcowy zapis.** Dopiero poPASS atomowe active metadata z runtimec306948, schemą84, Git tip, exactIDs i warunkowym rollbackcontract. Raport i docs zawierają faktyczne wyniki, także failedattempts i wszystkie nieprzeprowadzone kontrole. Zachowaj prywatne dowody w chronionym katalogu release, bez envsond/sekretów w publicznym archiwum.
- [ ] **Step5: Cleanup tylko własnych zasobów.** Po zakończeniu wszystkich testów i archiwizacji sprawdź pełneID/nazwy/etykiety/mounty/brakportów/brakaktywnychsesji, usuń tylko rehearsal/fencedPG+runner+ichwolumeny. Nie usuńrollbackimages/backups/aktywnego migratora-dowodu/cudzychtestDB. Gałąź i host-managedworktree zostają do osobnej decyzji.

## Macierz rollbacku

| Stan | Dopuszczone działanie w tym planie |
|---|---|
| Przed produkcyjnym UP | Przywróć dostęp do niezmienionych7801 po potwierdzeniu stanu; żadnegoDBrollback |
| Schema84, kompletzerowychimportguardów, stare7801 zgodne z84 | App-onlyrollback do7801 za fence; schema84 pozostaje |
| Upload/staging/receipt/documentbank_import/wersja/pointer istnieją | Maintenance i fix-forward; brak automatycznego oldapp/DOWN/restore |
| Nieznany stan, schema6bd, brak zapytania/proof lub drift | STOP/maintenance i decyzja operatora; brak wnioskowania „pusto” |
| Potrzeba przywrócenia backupu produkcyjnego | Poza zgodą D; osobna decyzja uwzględniająca utratę nowszych zapisów |

## Self-review planu — wykonany przy pisaniu, nie wyniki wdrożenia

- Zakres obejmuje cały diff do produkcji, oba schematy i wszystkie trzy aplikacje; nie tylko ekran harmonogramów.
- Zgody P/D są jawne. Obecna zgoda obejmuje plan, nie tworzenie backupów/klonów lub APPLY.
- Interfejs freeze łączy Task1→2→3→4; proofklonu zasila `select_rollback`; ten sam imageID/user/Compose musi przetrwać build→verify→apply.
- Każdy ReviewFocus ma test/probe i STOP w przypisanym tasku. Guardy wymagają RED→GREEN; operacje mają dodatni wynik lub odmowę, nie tylko opis oczekiwań.
- Ryzyko ingress jest jawne; sam plan nie jest werdyktem „gotowe do deployu”. Przejście2300testów bez14proxy nie dowodzi limitów nowej ścieżki. Ewentualny fix wymaga osobnego ustalenia SHA/bramek.
- Dowody2300/617/183 i747hash są sprawdzone, nie ponownie uruchamiane w sesji planowania. Odnowienie kodu/runtime lub wykrytydrift unieważnia ich przeniesienie bez dodatkowej weryfikacji.
- Rollback nie omija ochrony danych i nie używa poprzedniego020c229. Pilotaż pliku, produkcyjnyDOWN i DBrestore pozostają poza planem.
- Żaden checkbox wykonania nie jest oznaczony jako zakończony. Nie wykonano kroków operacyjnych tego planu.
