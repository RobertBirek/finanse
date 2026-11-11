# Importery A+B — poprawka ingress i wznowienie P

Data: 2026-11-11. Kandydat pre-review: `e2b169b2f272b2b1c7276f905bb2042a0766ed8c`.
Po jednej poprawce z review nastąpi nowe zamrożenie SHA/obrazów.
**Status: odbiór P w toku — pełny backend, review i cleanup jeszcze nie zamknięte.**
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
| Realny verifier | Oba nonrootimportsPASS i ownID/noforcecleanup/absentPASS |
| Frontend |617PASS, lint/typecheck/buildPASS;15dist identycznych z odbiorem B6 |
| Backend static | Ruff wprost z projectpyproject i mypy193sourcesPASS w zgodnym runnerze |
| Full backend | W toku na oddzielnym własnym syntetycznym no-portPG |
| Pakiet i3obrazy | OfflinebuildPASS;775trackedsourcehash; pełnyCompose poza image/build bez zmian |
| Backup | Nowy zaszyfrowany snapshot, checksumdump/uploads i bezpieczna struktura archiwumPASS |
| Ownclone | Restore739→UP84→DOWN739→UP84; dane62starychtabel identyczne,13nowychpustych, pointeryNULL |
| Księga/oldruntime |0naruszeń; dokładny staryimage7801 czytaORM na84 w trybie read-only |
| Niezależny review |1Important: niepoprawne UUID miały wyjątek; fixpass RED3FAIL→GREEN11PASS, ops75PASS; bez re-review |
| Cleanup zasobów P | Jeszcze nie wykonany, czeka na całość dowodów/review/archiwum |

Pełny runner korzysta z obrazu `41be018…` tego samego co B6, bez pull/instalacji;
PG16 ma własny wolumen i `--network none`. Runner łączy się wyłącznie przez jego
namespace. Testy nie otrzymują produkcyjnych credentiali, danych ani oryginałów.
Snapshot źródeł full-run jest readonly. Po jego wykonaniu zmieniono tylko obsługę
lowercase błędu CLI w verifierze i3pureunitcases; świeże75focused obejmuje ten delta.
Przed końcowym odbiorem sprawdzana jest zgodność wszystkich plików aplikacji.

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
R: `/opt/finanse/webapp/releases/bank-imports-e2b169b2f272-NpudCmae/`.
Aktualne obrazy:
- Backend `sha256:cc44c0c3f7e1a053b1f593cbd75ec263270169afc62256dbb7087d948ce8faf2`.
- Worker `sha256:0aaa6ddd8fba4ca5152412c3a6aed61c57ef45cd0eaa9dd294f2615509f29755`.
- Frontend `sha256:02eb23d9a5b2baa4ce2e478fe230072ea4f3d088125e3a85bfee7a0f80abd6c6`.

Nie wykonano merge/push, maintenance, produkcyjnej migracji, deployu lub realnego
importu. Po wszystkich bramkach P potrzebna jest **osobna zgoda D** na dokładną
rewizję, FF/push, dwie migracje i trzy usługi. Fencedbackup i ponowny restore w oknie
D nie są zastąpione dzisiejszym próbnym snapshotem.
