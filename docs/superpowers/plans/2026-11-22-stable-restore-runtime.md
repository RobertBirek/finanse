# Stała ścieżka odtwarzania kopii — plan implementacji

> **For agentic workers:** Use `executing-plans` or `subagent-driven-development`; execute the tests and reviews before requesting production changes.

**Cel:** Jedna zmiana Makefile na stałą ścieżkę, zgodność narzędzia sprawdzana przed migracją i jedna decyzja obejmująca migrację, przełączenie narzędzia i wydanie.

**Zakres uzgodniony w rozmowie:** Cykliczne odtwarzanie ma zawsze używać konkretnej zweryfikowanej wersji, nigdy gałęzi Git ani `latest` jako wersji narzędzia. Zmiana nie dotyczy polityki wyboru *snapshotu* w harmonogramie ani sposobu wykonywania kopii. Po wycofaniu samej aplikacji narzędzie ma nadal rozpoznawać schemat pozostawiony w bazie.

**Architektura:** `/usr/local/lib/finanse/restore-runtime-current` to symlink do jednego z katalogów `restore-runtime-<prefiks SHA>` (nowe katalogi: 12 znaków; pierwszy sprawdzony katalog `restore-runtime-db062d2` zachowuje dotychczasową nazwę). Jest przełączany atomowo przez operatora pod istniejącą blokadą backup/restore, wyłącznie na sprawdzony, niezmienny katalog. Rozwiązanie linku należy do warstwy operacyjnej; `restore_runtime_preflight.py` nadal dostaje fizyczną ścieżkę i nie zaczyna akceptować dowolnych symlinków.

**Stos:** Python 3.12+, GNU Make, systemd, `flock`, istniejący checker grafu Alembic. Bez nowych zależności. Nie zakładamy niezmienności sprzętowej lub atrybutu `immutable`; używamy katalogów kontrolowanych przez roota i weryfikujemy przypięte bajty.

## Zasady wspólne

- Repozytorium nie zawiera sekretów ani prywatnego spisu produkcji.
- Nie zmieniamy backupu, harmonogramu, uwierzytelnienia DB, bramek V2 ani ich polityki dopuszczalnych plików.
- Operacje produkcyjne wymagają zatwierdzenia dokładnego pakietu, zakresu i dowodów. Preflight i raport zgodności nie oznaczają zgody.
- Jeżeli schemat się nie zmienia, wskazanie nie musi się zmieniać. Najpierw zweryfikuj istniejący pin.
- Blokada `/run/lock/finanse-backup-restore.lock` obejmuje cały odcinek od poprzedniego zatwierdzonego stanu do potwierdzonej zgodności po migracji. Nie dopuszczaj do pracy harmonogramu w stanie pośrednim.

## 1. Obsługa stałego wskazania

- [x] W `backend/tests/test_ops/test_restore_runtime_pointer.py` dodaj próby plikowe: dobry pin, brak linku, uszkodzony link, cel poza katalogiem, cel zapisywalny przez grupę, niezaufany właściciel, inny head oraz zmiana odczytanego linku przed przełączeniem. Nie używaj prawdziwego `/usr/local/lib/finanse` w testach.
- [x] W `ops/restore_runtime_pointer.py` dodaj narzędzie z odczytowym `inspect_pointer(root: Path, *, owner_uid: int = 0) -> Path`. Sprawdza stałą nazwę, bezpośredni fizyczny katalog w `root`, właściciela i brak zapisu przez grupę/innych. Nie wykonuje kodu z celu. Nazwę wersji powiąż z zatwierdzonym SHA z manifestu istniejącego checkera.
- [x] Rozdziel odczyt od `activate_pointer(root: Path, *, expected_current: Path | None, target: Path, approved_revision: str, owner_uid: int = 0) -> None`. Orkiestrator w tym samym etapie pod blokadą uruchamia istniejący checker na fizycznym celu, z dokładnymi pinami raportu, i porównuje faktyczny schemat z zatwierdzonym docelowym headem przed przełączeniem. Operacja porównuje poprzedni stan i atomowo podmienia tylko link (`os.replace` w tym samym katalogu). Nie usuwa katalogów. Symulowana awaria przed zamianą musi pozostawić poprzednie wskazanie.
- [x] Uruchom ukierunkowane testy offline i niezależny review ograniczeń ścieżek oraz warunków odmowy.

## 2. Sprawdzenie na początku wydania

- [x] W `docs/operations/backup-restore.md` i `.opencode/command/deploy.md` zaplanuj odczytowe sprawdzenie fizycznego runtime'u i grafu jak tylko znamy kandydacki head. Raport wymienia bieżący head, docelowy head i ewentualną wymaganą zmianę wskazania. Nowy runtime i próba na kopii trafiają do jednego arkusza wydania, nie do późniejszego doraźnego planu.
- [x] Przedstaw kontrolę `rehearsal` i `after_rollout` jako osobne dowody z istniejącego checkera. Przed zgodą na rollout pracujemy tylko na przypiętych bajtach oraz izolowanej kopii; sprawdzamy zgodność pinu po przełączeniu i nie ogłaszamy gotowości bez dowodu.
- [x] Regresja scenariuszy: wydanie bez migracji pozostawia wskaźnik; migracja bez zweryfikowanego nowego runtime'u kończy się `STOP`; rollback aplikacji po migracji nie cofa wskazania; trwały znacznik blokuje restore po przerwanej migracji do potwierdzenia schematu i wskazania.
- [ ] Przy aktualnym `d284e80` pierwszy krok na produkcji proponuje ustawienie linku na obecny, zweryfikowany `db062d2` i jednorazową zmianę tylko ścieżki odtwarzania w Makefile. Przełączenie na przygotowany `d284e80` jest częścią ustawionego pod blokadą wydania migracyjnego, nie osobną edycją Makefile. Nie uruchamiaj żadnej z tych zmian bez akceptacji dokładnych wejść. Jeżeli jednorazowa zmiana zmieni stan oczekiwany preflightu, zachowaj udokumentowaną różnicę i ponów wymagane bramki.

## Dowody odbioru

- Testy plikowe i checkera bez produkcyjnego I/O, `/lint`, `/typecheck`, `/test` i niezależny review. Status opisany w CHANGELOG/TASKS/JOURNAL.
- Zmiany narzędziowe są oddzielone od wydawanego kodu aplikacji; nie obchodzą istniejącej klasyfikacji V2.
- Wykonawca ponownie sprawdza dosłowny render Compose, przypięte artefakty, kopię, spójność księgi, brak niespodziewanych zapisów i zgodność rollbacku. Istniejące dowody `d284e80` zachowuje, dopóki ich wejścia są niezmienione.
