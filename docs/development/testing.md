# Kontrole developerskie

`/lint`, `/typecheck` i `/test` działają w bieżącym worktree, również z jego
podkatalogu. Nie przechodzą do `/opt/finanse`. Git odczytuje root i SHA bez
odziedziczonych zmiennych Git oraz globalnego/systemowego configu.

Wskaż **bezwzględną ścieżkę** istniejącego interpretera przez
`ADVISOR_DEV_PYTHON`. Agent ma zapytać o nią, jeśli jej nie podano; nie wyszukuje
zastępstwa w PATH lub `.venv`. Komendy sprawdzają odpowiedź sondy Python 3.12+
przed preflight; sam wykonywalny plik (np. `/bin/true`) nie wystarcza.
To wykrycie pomyłki w ścieżce, nie uwierzytelnienie złośliwego programu
celowo udającego interpreter. Każdy prompt zawiera jeden kompletny blok Bash.
Nie przenoś zmiennych między osobnymi wywołaniami narzędzi.

## Preflight

`ops/dev_environment.py --root ABS_REPO_ROOT --check test|lint|typecheck`,
uruchomiony wybranym Pythonem z `-I -B`, czyta metadane z `backend/pyproject.toml`
i `backend/requirements.txt`. Porównuje wersję Pythona, bezpośrednie zależności,
piny i wymaganie wybranego narzędzia (`pytest`, `ruff`, `mypy`). Sukces to JSON
z root, python i check oraz exit 0. Nie importuje aplikacji ani `.env`, nie
instaluje pakietów i nie odpytuje usług. Nie jest resolverem zależności
przechodnich, sprawdzeniem Node/npm ani dowodem zgodności całego środowiska CI.

Obcy root, brak metadanych, brak lub stara wersja zależności oznacza STOP przed
narzędziami. Bez automatycznych aktualizacji środowiska. Minimum OpenAI SDK to
2.54.0, zgodne z istniejącym pinem, nie deklaracja pierwszej wersji Responses API.

## Co wykonują komendy

| Komenda | Backend | Frontend |
|---|---|---|
| `/lint` | Ruff: app, tests, ci_tools i helper | `npm run lint` |
| `/typecheck` | mypy: app, ci_tools i helper | `npm run typecheck` |
| `/test` | **tylko kolekcja offline**, maks. 40 s | `npm test` = `vitest run` |

Po błędzie preflight lub backendu frontend nie jest uruchamiany. Raportuj go
jako niewykonany; nie maskuj pierwotnego kodu wyjścia. Bez autofix, instalacji,
retry i zmian kodu bez zgody.

### Kolekcja nie jest wykonaniem testów

Backend `/test` używa obecnego `ci_tools.runner collect`. Prywatny katalog
`advisor-checks.*` powstaje pod `${TMPDIR:-/tmp/opencode}` (rodzic musi istnieć).
Zawiera manifest ze SHA checkoutu, `collection/process.json` i `collection/run.log`.
Pliki nie nadpisują wcześniejszego uruchomienia. SHA identyfikuje HEAD; nie
poświadcza braku lokalnych zmian.

Kolekcja importuje moduły testów i conftest, ale nie wykonuje fixture ani test
bodies. Nawet exit 0 i manifest nie oznaczają „testy backendu PASS”. Wynik testów
jednostkowych frontendu podaj osobno. E2E nie wchodzi do tej komendy.

Izolacja: nieinteraktywne `sudo -n -- unshare --net`, potem `setpriv` przywraca
UID/GID wywołującego, inicjalizuje jego grupy i włącza no-new-privileges. Odmowa
uprawnień lub brak narzędzi to STOP, nigdy fallback na sieć hosta, userns lub
zmiana polityki sudo. Gdy wywołujący jest rootem, Python też pozostaje UID 0.
To nie sandbox do uruchamiania niezaufanego kodu.

Po obniżeniu uprawnień `env -i` przekazuje kontrolowany PATH, prywatny HOME,
opcjonalny `LD_LIBRARY_PATH` wybranego środowiska i syntetyczne ustawienia.
PostgreSQL i Redis wskazują `127.0.0.1:9`, klucze dostawców są puste.
Bootstrap `-I -B` dodaje tylko jawny `ROOT/backend`, by załadować nieinstalowany
runner. Istniejący child pytest używa `-B`, nie dziedziczy flagi `-I`; chronią go
czyste env, prywatny HOME i `PYTHONNOUSERSITE=1`. Bez zmian istniejącego runnera.
To ograniczenie sieci, nie izolacja plików hosta.

Pełne testy backendu wymagają osobnej zgody oraz dowodu własności **nowej
syntetycznej bazy** przed fixture tworzącymi/usuwającymi schemat. Te prompty
nie przyznają zgody na DB, Docker, CI, push, merge, migracje lub deploy.

## Utrzymanie

Testy kontraktu w `backend/tests/test_dependency_contract.py` sprawdzają
rzeczywiste bloki promptów, czysty Git, odmowy i kod wyjścia. Używają doubles
Ruff/mypy/npm/granicy sudo, więc nie wymagają Ruff/mypy w matrix jobach.
Syntetyczne repo wykonuje prawdziwą kolekcję runnera. Test nie dowodzi fizycznej
izolacji kernela; model netns stosuje istniejący workflow CI.

Istniejący katalog `.opencode/command/` jest obsługiwany w OpenCode V2.
Prompty przeładowują się automatycznie; bez restartu serwisu i bez shell
substitution omijającego kontrolę uprawnień agenta.
Źródło: [OpenCode Commands](https://opencode.ai/docs/commands).

## Pozwolenie na lifecycle DB testów

Sama nazwa `finanse_test`, localhost i prawidłowy port **nie są pozwoleniem**
na tworzenie lub usuwanie schematu. Mutujące fixture wymagają
`ADVISOR_TEST_DB_PERMIT`; brak/obcy/uszkodzony permit to błąd przed utworzeniem
fixture engine, połączeniem DB lub subprocess Alembic, a nie SKIP.

Dotyczy to globalnej fixture, nadpisania fixture kategorii, niezależnej fixture
kolorów oraz migracji. Sam filtr `-m "not integration"` nie gwarantuje braku DB:
część testów kolorów ma własną fixture bez tego markera. Do kontroli offline
wybieraj konkretne pliki/przypadki jednostkowe; `/test` nadal robi kolekcję.
Importy aplikacji mogą tworzyć leniwe obiekty engine; to nie połączenie DB
ani przyznanie pozwolenia dla wybranego celu fixture.

### Kto wydaje pozwolenie

W tym zakresie tylko zaufany job `backend_tests` w istniejącym GitHub Actions:
ma nowy ephemeral PostgreSQL dla swojej grupy. Po dotychczasowym preflight
weryfikuje pusty public i tożsamość bazy, ustawia losowy znacznik w komentarzu
`finanse_test`, następnie publikuje dokładnie jeden prywatny plik0600 w nowym
katalogu0700 pod `$RUNNER_TEMP`. Eksportuje jego absolutną ścieżkę oraz SHA
checkoutu dopiero po sukcesie. Nie nadpisuje istniejącego permitu.
Tryb0600 jest wymuszany na otwartym deskryptorze niezależnie od umask runnera.

Pozwolenie zawiera ścisły cel (driver/host/port/database/role), OID, właściciela,
system_identifier klastra, znacznik oraz run/attempt/job/group/commit. Nie zawiera
hasła DB lub danych użytkownika. To przejściowy artefakt operacyjny, nie źródło
prawdy aplikacji. Fakty PostgreSQL są odczytywane przed DDL/cleanup; niezgodność
lub brak praw do odczytu oznacza odmowę. Znacznik komentarza jest publicznie
odczytywalny, nie jest tajnym credentialem.

Migracje zachowują istniejącą zgodę runnera i nową UUID scratch DB. Sprawdzają
jej zapamiętany OID/rolę/klaster przed każdym subprocess migracji i ponawiają
kontrolę parent przed usunięciem scratch. Sesje/Alembic osobno sprawdzają cel
i tożsamość przez krótkie połączenie tylko do odczytu przed uruchomieniem procesu.

### Lokalnie: odmowa, nie obejście

Nie ma lokalnego issuera/provisionera w tej zmianie. Nie twórz ręcznie permitu
z istniejącej bazy, nie kopiuj go z poprzedniego joba, nie ustawiaj `CI=true`
lub `GITHUB_ACTIONS=true` jako obejścia. Lokalny prawdziwy pilot nowej syntetycznej
bazy wymaga osobnego planu i zgody. Bazy produkcyjne i zachowane klony nigdy nie
są automatycznie adoptowane jako fixture.

Po odmowie nie uruchamiaj cleanup „ręcznie”. Przy zmianie tożsamości guard
zostawia schemat zamiast usuwać obcy cel. Brak współbieżności xdist/reuse jest
zamierzony. Ochrona dotyczy pomyłki operatora w zaufanym runnerze, nie złośliwego
kodu tego samego UID lub administratora PostgreSQL podmieniającego zasoby.

### Zakres lokalnego dowodu

Regresje używają fake DB/engine i prawdziwych generatorów fixture. Pozwalają
sprawdzić odmowę przed I/O, kolejność identity/DDL, sprzątanie zasobów i redakcję
błędów, ale **nie poświadczają działania na realnym PostgreSQL**.
Po osobnej zgodzie standardowe CI musi potwierdzić pozytywną ścieżkę na swoich
nowych serwisach i pełne grupy bez skipów; lokalne wyniki nie zastępują tego gate.
