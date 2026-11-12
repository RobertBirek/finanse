# Importery A+B — poprawka ingress i wznowienie P

Sesja: 2026-11-11–12. Finalny kandydat: `5dc84febc9a22e16afa76a9641e45a5f337d76a0`.
Pre-review `e2b169b` zachowano jako wcześniejszy etap; po jednej poprawce z review
odnowiono SHA, trzy obrazy i wszystkie bramki exactimage.
**Status 2026-11-12: P odebrane lokalnie, dowody zarchiwizowane, własne zasoby usunięte.**
Nie ma zgody D. Ten raport nie upoważnia do deployu ani produkcyjnego UP.
Poprzedni pakiet c306948 pozostaje NO-GO, wraz z niezmienionymi dowodami.

## Zakres zgody i poprawki

Użytkownik zatwierdził fix Nginx z testami, uszczelnienie bramek operatora i P.
Osobno wybrał „Bez retencji (Recommended)”: nowy szyfrowany snapshot/ownclone,
bez forget/prune i bez usuwania istniejących kopii. Nie zmieniono infrastruktury,
hostowego venv, produkcyjnych skryptów lub ustawień.

- Nginx21MiB tylko dla uploadu dokumentów i `/api/finance/imports/{id}/sources`,
  oba slash. ZwykłeAPI nadal odrzuca2MiB. Bez globalnego rozszerzenia limitu.
- Verifier: create/label→kontrola exactID/image/user/network/mounts→start;
  cleanup stop→inspectstopped→rmbezforce→absent. Nieznany stan blokuje PASS.
- Rollback wymaga trustedfreeze, zgodnej aktualnej obserwacji i powiązanych
  oldimageIDs. Sama poprawna postać ID lub komplet pustych tabel nie wystarcza.
  `select_rollback` bez obu freeze zwracaSTOP.
- Modele, serwisy finansowe, parsery, UI React i migracje bez zmian w tej poprawce.

## Wykonane bramki

| Bramka | Faktyczny wynik |
|---|---|
| Proxy regression | RED2FAIL/4PASS→GREEN6PASS; po review RED3FAIL/8PASS→GREEN11PASS |
| Operator unit tests |75PASS,6standardowychproxy deselected |
| Verifier CLI-case | Dodatkowy RED1FAIL/20PASS→GREEN21PASS |
| Realny verifier | Finalne5dc: oba nonrootimportsPASS i ownID/noforcecleanup/absentPASS |
| Frontend |617PASS, lint/typecheck/buildPASS;15dist identycznych z odbiorem B6 |
| Backend static | Ruff wprost z projectpyproject i mypy193sourcesPASS w zgodnym runnerze |
| Full backend |2329PASS/23standarddeselected,0failure/error/runtime-skips;8622.78s |
| Pakiet i3obrazy | OfflinebuildPASS;775trackedsourcehash; pełnyCompose poza image/build bez zmian |
| Backup | Nowy zaszyfrowany snapshot, checksumdump/uploads i bezpieczna struktura archiwumPASS |
| Ownclone | Restore739→UP84→DOWN739→UP84; dane62starychtabel identyczne,13nowychpustych, pointeryNULL |
| Księga/oldruntime |0naruszeń; dokładny staryimage7801 czytaORM na84 w trybie read-only |
| Niezależny review |1Important: niepoprawne UUID miały wyjątek; fixpass RED3FAIL→GREEN11PASS, ops75PASS; bez re-review |
| Cleanup zasobów P |13własnychkontenerów i2własnewolumeny usunięte po kontroli ID/label/mounts/idle; bezforce/prune |

Pełny runner korzysta z obrazu `41be018…` tego samego co B6, bez pull/instalacji;
PG16 ma własny wolumen i `--network none`. Runner łączy się wyłącznie przez jego
namespace. Testy nie otrzymują produkcyjnych credentiali, danych ani oryginałów.
Finalny snapshot źródeł full-run jest readonly i zawiera końcowy kod operatora
oraz testy UUID. Końcowy check potwierdził191plików aplikacji,775trackedsourcehash
i15plików dist. Brak delty kodu między finalnym pełnym przebiegiem a kandydatem.
Pierwszy pełny przebieg dał2320PASS/2FAIL/4ERROR/18deselected,0runtime-skips;
nie jest uznany za zielony odbiór. Przyczyny były w przygotowaniu własnego runnera:
brak `.git` w kopii źródeł i niezgodna nazwa roli, której słusznie odmówił guard.
Nie zmieniono guardów ani aplikacji. Dodano metadane Git do własnej kopii i nową
wyłączną rolę `bank_import_task_*` wyłącznie we własnym syntetycznym PG.
Wszystkie objęte regresją testy wraz z całymops: **80PASS/6deselected**.
Statyka finalnego snapshotu:193sourcesPASS. Drugi pełny przebieg zakończył się
2329PASS, bez błędów lub runtime-skipów; nie zastąpiono go sumą fragmentów.
Domyślny pytest wyłączył23testyproxy. Oddzielnie wykonano11testów ingress;
pozostałych12niezmienionych standardowych testówproxy nie uruchamiano w tej sesji.

Odrzucone testy pierwszego przebiegu (oryginalne XML/log zachowane):
- `test_backup_mocked_commands_run_in_snapshot_order_without_secrets` — brakGit.
- `test_failed_pg_restore_removes_only_created_uploads` — przerwane przez brakGit.
- `test_real_upgrade_preserves_rows_and_downgrade_refuses_import_data` — roleguard.
- `test_migration_preserves_old_rows_without_backfill` — roleguard.
- `test_loan_migration_preserves_old_records` — roleguard.
- `test_real_roundtrip_has_no_backfill_or_legacy_mutation` — roleguard.

### Backup i próba restore

Snapshot: `ff643adb7d18b9b2552d85082fd9fdbad3325a7ec3ef197a464dff22d3f63898`.
Schemat źródła739144d5eaef, manifestgit e2b169b. Wariant istniejącego backupu różni
się tylko jawną ścieżką repo (kopia skryptu poza Git) i pominięciem retencji.
Pozostają wspólny flock, serializable-deferrable dump, uploadflock, checksumy,
manifest i szyfrowanie Restic. Oryginalny backup.sh oraz Makefile nietknięte.

Restore wykonano do nowego własnego PG, bez portów hosta, z własną bazą
`bank_imports_restore`, losowymi credentialami i oznaczonym wolumenem.
Nie użyto `--clean`, nie zastąpiono istniejącej DB, nie odtwarzano produkcji.
Próby UP/DOWN/UP wykonał exactnewbackendimage; stary backend czytał bez lifespan,
workera, OCR/AI, HTTP-session creation lub zapisów. Hash62tabel liczy stare kolumny,
aby dodanie dwóch nullable pól nie udawało zmiany danych.

### Nieudane próby — nie pominięto ich w odbiorze

- Hostowy `.venv` okazał się niezgodny:75collectionerrors, m.in. brak
  `openai.types.responses`. Hostowe implicitruff wskazało3DTZ007 w niezmienionych
  parserach. Nie „naprawiano” parserów/venv; użyto zgodnego wcześniejszego runnera
  i jawnej konfiguracji projektu. Pierwsza próba cache na RO źródle odmówiła;
  cache przekierowano do własnego `/tmp` runnera.
- Docker CLI zwraca lowercase `no such object`; pierwsza realna próba verifiera
  odmawiała PASS już po usunięciu kontenera. Osobna regresja RED→GREEN obsługuje
  case, lecz permission/daemon error nie oznacza „absent”.
- Pierwszy oldreader z `python -I` nie miał `/app` w sys.path. Próba została
  zachowana jako FAIL; po dodaniu jawnej ścieżki powtórzono tylko readonlyreader
  na tym samym obrazie/klonie. Nie powtarzano backupu, restore lub migracji.

## Dowody i następna granica

E: `/tmp/opencode/bank-imports-repair-NpudCmae/` (prywatne).
R: `/opt/finanse/webapp/releases/bank-imports-5dc84febc9a2-NpudCmae/`.
Aktualne obrazy:
- Backend `sha256:6df59809faa44d1602cc2e1eff6b6ad0a7b955358985437a60dae66dbb65062b`.
- Worker `sha256:65bb7df0cff9e5b13e3b7ce26586435864eaaa7b2089bcf0150d2b61d7c4e5d9`.
- Frontend `sha256:9a64f0415c20985b79dda04e343d6c9b573cf4f6c6e93e734fe20cffbb165711`.

Na tym samym własnym klonie ponowiono UP/DOWN/UP dokładnego finalnego backendu
oraz stary readonlyreader;62hashy,13pustych i księgaPASS. Snapshot ff643adb pozostał
tym samym wejściem P (app/migrations między e2 i5dc są identyczne); nie wykonywano
dodatkowego backupu produkcji. To nadal nie zastępuje fencedbackup w D.

Nie wykonano merge/push, maintenance, produkcyjnej migracji, deployu lub realnego
importu. Po wszystkich bramkach P potrzebna jest **osobna zgoda D** na dokładną
rewizję, FF/push, dwie migracje i trzy usługi. Fencedbackup i ponowny restore w oknie
D nie są zastąpione dzisiejszym próbnym snapshotem.

## Zamknięcie P, 2026-11-12

- Końcowy read-only check potwierdził produkcję7801ba5/schema739144d5eaef oraz
  niezmienione ID, obrazy, Config/HostConfig, starttime i restarty6usług. Osobna
  kontrola po cleanup potwierdziła także ich mounty i sieci. Active metadata bez zmian.
- Po weryfikacji idle DB, exactID/label/image/network/volume usunięto13własnych
  kontenerów i2własnewolumeny. Usunięto plaintext kopię backupu i credentiale własnych
  baz. Offsite snapshot, obrazy rollbacku, pakiety i cudze zasoby pozostały.
- Archiwum54sanityzowanych dowodów: `R/evidence/preparation-final.tar.gz`, SHA-256
  `0056abc5bd95ef8676c13852d0aea20ae17b157b669412b3a41f9ddf541ce59a`.
  Manifest/checksumy i skan rzeczywistych wartości sekretówPASS. Surowe inventory,
  Compose/env, DB dump i uploads pozostają poza archiwum i Git.
- Osobny końcowy proof: `R/evidence/last-inventory-proof.json`, SHA-256
  `3fe6c61e0031b8646367b37298a6d77b08970391793ecedd2a039b16ece77842`.
- Wcześniejsze odrzucone przebiegi i przyczyny zachowano w dowodach. Nie ma
  nierozwiązanych Critical/Important ani odłożonych Minor po jednym fix pass review.

### Decyzje proceduralne i ograniczenia

Zachowano istniejący worktree i niezwiązane audyty. Ujednolicono nagłówki Task 1
dla harnessu bez zmiany zakresu. Początkowe reuse hashów wcześniejszego odbioru
zastąpił finalny pełny rerun; zmiana źródeł unieważnia stare dowody.

Ingress sprawdzono przed dawnym verifierem ze względu na zakazforce, a następnie
odnowiono obie bramki po poprawce. Początkową uwagę o niepowiązanych oldimageIDs
zamknięto trwałym trustedfreeze guardem; starego select_rollback nie używano.

Ten sam snapshot służył próbom po fixie UUID, ponieważ app/migrations są identyczne;
ponowiono exactimageUP/DOWN/UP. Przy D potrzebny jest nowy fencedbackup i restore.
Braki Git/roli poprawiono we własnym runnerze zamiast osłabiać guardy. P nie upoważnia
do D, produkcyjnego DOWN/restore lub pilotażu rzeczywistego dokumentu.
