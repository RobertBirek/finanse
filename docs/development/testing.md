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
