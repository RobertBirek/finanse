# Worktree-local development checks Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** `/test`, `/lint` i `/typecheck` sprawdzają bieżący worktree oraz jawnie wybrany interpreter, bez fallbacku do `/opt/finanse` lub współdzielonego środowiska.

**Architecture:** Zachowujemy istniejące prompty Markdown OpenCode i dodajemy odczytowy preflight Python. Domyślny backend `/test` eksportuje tylko offline inventory istniejącym runnerem CI; nie uruchamia test bodies ani fixtures. Nie kopiujemy historii starej gałęzi.

**Tech Stack:** Python 3.12+, stdlib `importlib.metadata`/`tomllib`, istniejące `packaging`, Bash, pytest i obecny `ci_tools.runner`. Bez nowych zależności lub zmian workflow.

**Spec:** [Specyfikacja małej zmiany](#specyfikacja-małej-zmiany) w tym dokumencie. Plan zatwierdzony do lokalnej realizacji; publikacja bez zgody.

## Execution ledger — 2026-11-16

- [x] Zgoda na Native, osobny worktree `worktree-dev-checks`, baza `fccf5d1`.
- [x] Task 1: 12 RED → GREEN, lint/typecheck helpera i testu PASS, commit `5378508`.
- [x] Task 2: 25 RED → GREEN; łącznie 114 testów (37 nowych, 77 ci_tools)
  PASS, pełny lint PASS. Commit komend i dokumentacji `7e4dad8`.
- [x] Po zgodzie użytkownika na wznowienie: pełny mypy PASS (211 plików, 8.69 s),
  ponownie 114 testów PASS i pełny lint PASS. Budżet 106.25/180 s.
- [x] Task 3: kontrola zakresu 11 plików i stare worktree bez zmian; jeden review
  readonly ukończony, zgłoszenie Important poprawione testem RED→GREEN.
- [x] Final: fixed non-Python executable false-success — 6 przypadków
  `test_commands_reject_non_python_program` RED→GREEN, suite 120/120 PASS.
  Pełny lint PASS, mypy app/ci_tools/helper/test PASS (212 plików).
  Commit poprawki `f2124e5`; walidacja 127.85/180 s.
- Final: minor (deferred): kolekcja przekazuje odziedziczony `LD_LIBRARY_PATH`;
  powiązanie ścieżki bibliotek z wybranym środowiskiem nie jest walidowane.
  Bez zmiany zachowania w tej rundzie; ogranicza powtarzalność środowiska.
- Final: Ruling: Python pozostaje UID 0 dla wywołującego roota — zgodne z jawnym
  modelem uprawnień, nie obietnicą sandboxa. Koszt błędnej oceny: importowany kod
  ma uprawnienia roota; używać tylko zaufanego checkoutu i interpretera.
- Final: Ruling: importy kolekcji mogą czytać pliki hosta — netns izoluje sieć,
  nie system plików. Koszt błędnej oceny: niezaufany moduł może odczytać pliki;
  nie uruchamiać kolekcji niezaufanego kodu.
- Final: Ruling: child pytest zachowuje istniejące `-B`, bez `-I` — jawny kontrakt
  runnera, czyste env/prywatny HOME/no-user-site ograniczają ambient Python.
  Koszt błędnej oceny: kolekcja nadal używa zainstalowanych pakietów/pluginów.
- Ruling: fixture kolekcji ma 8 testów zamiast jednego — obecny runner wymaga
  niepustych wszystkich 8 grup, więc zmiana fixture zachowuje jego kontrakt.
  Koszt błędnej decyzji: niepełny dowód integracji; runner i workflow bez zmian.
- Użytkownik zatwierdził wznowienie po limicie wywołania 30 s. Bez push/CI.
- Publikacja, CI, merge i deploy nie zostały wykonane; gałąź i worktree zachowane.

## Specyfikacja małej zmiany

- Bazą realizacji jest aktualny main. W chwili planowania: `fccf5d1160f2203673f95215cb648f1e2794687e`.
- `ADVISOR_DEV_PYTHON` musi być niepustą, bezwzględną ścieżką do wykonywalnego, istniejącego interpretera. Bez niego STOP; agent pyta o ścieżkę. Bez szukania zamiennika w PATH lub `.venv`.
- `root`/`ROOT` oznacza katalog główny repozytorium, nie katalog `backend`. Helper czyta `root/backend/pyproject.toml` i `root/backend/requirements.txt`; testowe repo musi mieć ten sam układ.
- Root pochodzi z poniższego wywołania. `env -i` usuwa odziedziczone `GIT_DIR`, `GIT_WORK_TREE`, `GIT_COMMON_DIR` i `GIT_CONFIG_*`; dwie jawne zmienne dodatkowo wyłączają globalny/systemowy config. Każdy kolejny odczyt Git w blokach komend, w tym SHA, używa tego samego czystego środowiska.
  ```bash
  ROOT="$(env -i PATH=/usr/bin:/bin HOME="${TMPDIR:-/tmp/opencode}" \
    GIT_CONFIG_NOSYSTEM=1 GIT_CONFIG_GLOBAL=/dev/null \
    git rev-parse --show-toplevel)"
  ```
  Dla SHA: identyczny prefiks `env -i ... GIT_CONFIG_GLOBAL=/dev/null`, następnie `git -C "$ROOT" rev-parse HEAD`. Cytowanie obsługuje ścieżki ze spacjami i wywołanie z podkatalogu.
- Preflight porównuje wersję Pythona, zależności projektu, `requirements.txt` i wymaganie wybranego narzędzia z `optional-dependencies.dev`. Nie jest resolverem zależności przechodnich ani walidatorem Node/npm.
- Helper nie importuje aplikacji lub `.env`, nie kontaktuje się z usługami, nie instaluje pakietów i nie uruchamia narzędzi. Błąd kończy kontrolę przed backendem/frontendem.
- Minimum SDK w `pyproject.toml`: `openai>=2.54.0`, zgodnie z już istniejącym `requirements.txt` (`openai==2.54.0`). To konserwatywna sprawdzona wersja, nie twierdzenie o pierwszej wersji obsługującej Responses. Nie zmieniamy pinów.
- Komendy pozostają promptami w istniejącym `.opencode/command/`. Bez `!` shell blocks, pluginów, zmiany konfiguracji lub migracji do katalogu `commands/`.
- `/lint`: wybrany Python uruchamia Ruff dla `app tests ci_tools ../ops/dev_environment.py`, potem frontend `npm run lint`. Bez autofix.
- `/typecheck`: wybrany Python uruchamia mypy dla `app ci_tools ../ops/dev_environment.py`, potem frontend `npm run typecheck`. Bez automatycznych poprawek.
- `/test`: backend **tylko kolekcja offline**, potem frontend `npm test` (istniejący skrypt `vitest run`, bez watch). Wynik kolekcji nigdy nie jest opisany jako PASS testów backendu.
- Kolekcja używa obecnego `ci_tools.runner collect`, timeout 40 s i jawnego SHA bieżącego checkoutu. Tworzy prywatny katalog raportów przez `mktemp` w `${TMPDIR:-/tmp/opencode}`; nie nadpisuje wcześniejszych artefaktów.
- Namespace powstaje przez `sudo -n -- unshare --net`; `setpriv` przywraca UID/GID wywołującego, inicjalizuje jego grupy i ustawia `--no-new-privs` przed Pythonem. Bez userns, fallbacku z siecią hosta, zmian polityk hosta lub interaktywnego hasła.
- Bezpośrednie wywołania wybranego interpretera używają `-I -B`. Ponieważ `-I -m ci_tools.runner` nie odnajdzie nieinstalowanego pakietu z cwd, kolekcja używa krótkiego bootstrapu stdlib: dodać wyłącznie zatwierdzony `$ROOT/backend` do `sys.path`, skorygować `sys.argv`, wywołać `runpy.run_module("ci_tools.runner", run_name="__main__")`. Bez `PYTHONPATH`. Istniejący runner uruchamia child pytest z `-B`, bez `-I`; zachowuje czyste env, prywatny HOME i `PYTHONNOUSERSITE=1`. Nie zmieniamy runnera, nie twierdzimy, że propaguje flagę `-I`.
- Po obniżeniu uprawnień `env -i` przekazuje tylko PATH, prywatny HOME w katalogu artefaktów, ewentualny `LD_LIBRARY_PATH` wybranego środowiska i syntetyczne ustawienia: ENVIRONMENT=test, PYTHONDONTWRITEBYTECODE=1, PYTHONNOUSERSITE=1, klucz sesji testowej, puste OPENAI_API_KEY/LLM_API_KEY, PostgreSQL i Redis na `127.0.0.1:9`.
- UID/GID wywołującego oznacza także UID0, gdy użytkownik sam pracuje jako root. Nie podnosimy uprawnień procesu Pythona względem użytkownika, ale nie jest to sandbox do wykonywania niezaufanego kodu ani zgoda na zapis do bazy.
- Pełne testy backendu i fixture DB wymagają odrębnej zgody oraz dowodu własności nowej syntetycznej bazy. Ten zakres nie dodaje opcji automatycznie przyznającej taką zgodę.
- Każda komenda ma jeden kompletny blok Bash `set -euo pipefail`: root, interpreter, preflight, backend i frontend w jednym wywołaniu shell. Nie polega na utrwalaniu zmiennych między tool calls.

## File structure i zakres publikacji

| Plik | Odpowiedzialność |
|---|---|
| `.opencode/command/test.md` | Domyślna kolekcja offline i osobne wyniki frontendu |
| `.opencode/command/lint.md` | Root/interpreter/preflight i kontrola błędów Ruff/ESLint |
| `.opencode/command/typecheck.md` | Root/interpreter/preflight i kontrola błędów mypy/tsc |
| `ops/dev_environment.py` | Pure validation oraz odczytowe CLI preflight |
| `backend/tests/test_dependency_contract.py` | Testy SDK, preflight i rzeczywistych bloków poleceń |
| `backend/pyproject.toml` | Wyłącznie minimum OpenAI SDK |
| `docs/development/testing.md` | Uprawnienia, tryby, ograniczenia i interpretacja wyników |

To **7 plików funkcjonalnych**. Plan oraz krótkie wpisy CHANGELOG/TASKS/JOURNAL dają maksymalnie **11 plików w przyszłym PR**. Dokumentacja ma wejść do tego samego PR, bez następnego osobnego PR porządkowego.

## Global Constraints

- Nie cherry-pickować starych commitów ani kopiować całego `test_dependency_contract.py`; pominąć niezwiązane testy precyzji Decimal.
- Bez zmian `backend/app`, migracji, `requirements.txt`, frontendowych pakietów, `conftest.py`, pilota DB, A2, OCR staging, `ci_tools` lub workflow.
- Nie zmieniać `.venv`, shared env, Makefile, globalnych formatterów/LSP i konfiguracji OpenCode.
- Nie zamykać osobnego zadania Ruff DTZ007 ani podnosić wersji narzędzi.
- Planning stage: tylko ten plan i wpisy sesji, bez implementacji/testów/commitów/push/CI.
- Realizacja dopiero po zatwierdzeniu planu, na osobnej gałęzi/worktree od świeżego main; oba stare worktree i surowe notatki zachować.
- Proponowany lokalny budżet walidacji: 180 s, bez DB, Docker i pełnej suity domenowej. Brak zgodnego interpretera lub przekroczenie budżetu oznacza STOP i raport, nie automatyczny retry/instalację.
- Publikacja wyłącznie po zgodzie: jeden push, jeden draft PR i jego standardowy CI. Bez manualnego dispatch/retry, merge i deployu.

## Review Focus

1. Hostile Git env, podkatalog i spacje nie mogą skierować kontroli do innego checkoutu. Task 2: `test_git_environment_cannot_redirect_root`.
2. Brak interpretera/zależności, błąd preflight lub backendu nie może zostać przykryty sukcesem frontendu. Tasks 1–2: odmowy i marker niewykonania npm.
3. Brak sudo/netns lub odmowa uprawnień muszą zatrzymać kolekcję bez host-network fallbacku. Task 2: `test_collection_namespace_denied_stops_before_frontend`.
4. Izolowany Python musi załadować właściwy runner i SDK bez ambient PYTHONPATH/user-site; nie uruchomić fixture/test body. Task 2: rzeczywista kolekcja syntetycznego repo.
5. Grupy backend CI nie instalują Ruff/mypy. Nowe testy nie mogą wymagać tych executable lub pakietów do własnego przejścia. Task 1: pure versions map; Task 2: doubles zewnętrznych narzędzi.

---

### Task 1: Kontrakt zależności i odczytowy preflight

**Files:** create `ops/dev_environment.py`, create `backend/tests/test_dependency_contract.py`, modify wyłącznie OpenAI floor w `backend/pyproject.toml`.

**Interfaces:**
- Consumes: repo-root `root`; `root/backend/pyproject.toml` (`project.requires-python`, `project.dependencies`, wybrane dev-tool requirement) i `root/backend/requirements.txt`; `test→pytest`, `lint→ruff`, `typecheck→mypy`.
- Produces: `validate_environment(root: Path, check: str, installed: Mapping[str, str], python_version: str) -> None`, `main() -> int`.
- CLI: `python -I -B ops/dev_environment.py --root ABS_ROOT --check {test,lint,typecheck}`; sukces JSON z root/python/check i exit 0; odmowa stderr i nonzero.
- Test utilities: `load_preflight() -> ModuleType`; fixture `project(tmp_path: Path) -> Path` zwraca repo-root zawierający `backend/pyproject.toml` i `backend/requirements.txt`, bez aplikacji. Dla testów rzeczywistego CLI fixture dodatkowo tworzy `ops/dev_environment.py` oraz `frontend/package.json`, zgodnie z układem repo; nie instaluje frontendu.

- [ ] **Step 1: Testy RED.** Zdefiniować pure fixture repo-root z `backend/pyproject.toml` (`openai>=2.54.0`, Python `>=3.12`, trzy wymagania narzędzi) i `backend/requirements.txt` (`openai==2.54.0`). Sprawdzić:
  ```python
  project = tomllib.loads((ROOT / "backend/pyproject.toml").read_text())["project"]
  sdk = next(Requirement(v) for v in project["dependencies"] if Requirement(v).name == "openai")
  assert not sdk.specifier.contains("1.51.2")
  assert sdk.specifier.contains("2.54.0")
  ```
  Test metadanych odczytuje rzeczywiste pyproject i odrzuca 1.51.2; pin z requirements pozostaje akceptowany.
  `test_valid_environment`: fake versions openai2.54.0/pytest9.1.1/ruff0.17.1/mypy2.4.0 i Python3.12.3 przechodzą dla trzech checków.
  `test_environment_refuses_missing_or_stale_dependency`: brak SDK, SDK1.51.2, pytest8.3.3, Ruff0.16.2 i mypy2.3.0 podnoszą ValueError z nazwą pakietu.
  `test_environment_refuses_unknown_check_and_python`: checkdeploy/Python3.11.9 odrzucone.
- [ ] **Step 2: Uruchomić RED.** W zgodnym prywatnym interpreterze: `-I -B -m pytest -q -p no:cacheprovider tests/test_dependency_contract.py`. Oczekiwane: brak helpera i/lub metadane dopuszczające stary SDK, bez DB/fixture domenowych.
- [ ] **Step 3: Implementacja.** Zaadaptować wyłącznie pure helper ze starej gałęzi: `packaging` parsuje specyfikatory/markery, `importlib.metadata` odczytuje instalację, `__file__.resolve()` wiąże CLI z repo skryptu. Nie uruchamiać tooli lub instalacji. Zmienić tylko `openai>=1.30.0` na `openai>=2.54.0`.
- [ ] **Step 4: Dodać CLI tests.** Obcy root i niekompletny repo odrzucane przed narzędziami. Dla sukcesu rzeczywistego CLI użyć `check=test` i syntetycznego repo z pytest dostępnym w requirements CI. Pure tests pokrywają pozytywne lint/typecheck; nie wymagać ich instalacji w matrix jobach. Probe `.env`/`app` ma wykryć próbę importu, nie zawierać prawdziwych sekretów.
- [ ] **Step 5: GREEN i lokalny commit.** Wyżej wymieniony pytest oraz Ruff/mypy helpera i nowego testu muszą przejść. Oczekiwane: zero failed/error/skip, brak importu aplikacji i zmian środowiska. Commit lokalny obejmuje tylko te 3 pliki; bez push.

### Task 2: Trzy prompty worktree-local i dokumentacja użycia

**Files:** modify trzy `.opencode/command/*.md`, extend `backend/tests/test_dependency_contract.py`, create `docs/development/testing.md`.

**Interfaces:**
- Consumes: CLI i pure contract z Task 1; istniejący `ci_tools.runner collect` i skrypty npm.
- Produces: kompletne bloki Bash w promptach, funkcja testowa `command_block(check: str) -> str`, syntetyczny committed Git fixture bez aplikacji/DB.

- [ ] **Step 1: Testy RED rzeczywistych bloków.** `command_block` odczytuje jedyny blok Bash z danego promptu; fixture ma spacje w ścieżce i wywołanie z `backend/tests`. Testy:
  - `test_command_requires_absolute_explicit_python`: unset, pusta/relatywna ścieżka lub nieistniejący plik dają nonzero; marker backend/frontend nie powstaje.
  - `test_git_environment_cannot_redirect_root`: GIT_DIR/WORK_TREE/COMMON_DIR i GIT_CONFIG_COUNT wskazują obcy fixture; komenda nadal wybiera bieżący root, nie obcy. Dodatkowo kontrolowany HOME/global config zawiera `core.worktree` obcego repo; root i SHA nadal dotyczą właściwego fixture. Double Git sprawdza, że nie otrzymał tych odziedziczonych zmiennych, a otrzymał `GIT_CONFIG_NOSYSTEM=1` i `GIT_CONFIG_GLOBAL=/dev/null`.
  - `test_preflight_and_backend_failure_stop_frontend`: preflight lub backend exit17 pozostaje17; kontrolowany npm nie zostaje wywołany. Testować `/test`, `/lint`, `/typecheck`, nie tylko końcowy exit.
  - `test_local_checks_keep_ci_tools_in_scope`: doubles odczytują rzeczywiste argv i wymagają Ruff `app tests ci_tools ../ops/dev_environment.py`, mypy `app ci_tools ../ops/dev_environment.py`; brak `--fix`.
  - `test_collection_namespace_denied_stops_before_frontend`: controlled privilege boundary odmawia, brak drugiej próby lub wywołania hostowego pytest/npm.
- [ ] **Step 2: Uruchomić RED.** Nowe selektory przez pytest w prywatnym interpreterze. Oczekiwane: obecne prompty nie mają poprawnych bloków/preflight i wskazują `/opt/finanse`; żaden rzeczywisty root/dev-tool/DB nie jest uruchamiany.
- [ ] **Step 3: Zmienić prompty.** Wdrożyć specyfikację: jeden blok Bash, czysty Git root, jawny Python, preflight jako pierwszy etap, te same zmienne w całym wywołaniu, zatrzymanie na błędzie. Dokumentować ograniczenie backend `/test` do kolekcji, nie pełnych testów.
- [ ] **Step 4: Rzeczywista kolekcja syntetycznego repo.** Skopiować obecne `ci_tools` do prywatnego fixture, przygotować wymagane pytest marker/addopts i lokalny commit Git. Dodać test body oraz autouse fixture, które po uruchomieniu tworzą markery błędu. Uruchomić rzeczywisty blok `/test` z wybranym Pythonem i runnerem; zastąpić tylko granicę sudo/unshare/setpriv oraz npm kontrolowanymi doubles.
  Oczekiwane: manifest ma SHA fixture i jeden test, process exit0, brak markerów testbody/fixture, brak sekretu HOST_ONLY_SECRET, DSN na port9. Double uprawnień waliduje kolejność `sudo -n/unshare --net/setpriv/env -i` i flagi, bez rzeczywistej zmiany namespace, użytkownika lub usług. Brak dowodu fizycznej izolacji kernela w tym unit teście jest jawny; rzeczywisty model netns jest już używany przez CI.
- [ ] **Step 5: Przypadki SDK/CI.** Sprawdzić brak zależności od realnych Ruff/mypy w testach pozytywnych. Dla testów sekwencji zewnętrzne tool doubles są dozwolone; nie zastępują pure metadata tests ani rzeczywistej kolekcji. Nie przenosić starych testów Decimal.
- [ ] **Step 6: Dokumentacja i GREEN.** `docs/development/testing.md` opisuje zmienione znaczenie `/test`, JSON/manifest/process a wykonane testy, odmowę uprawnień, zgody DB, brak fallbacku/install/autofix i automatyczne przeładowanie promptów OpenCode. Uruchomić nowe contract tests razem z `tests/test_ci_tools`; Ruff `app tests ci_tools ../ops/dev_environment.py` i mypy `app ci_tools ../ops/dev_environment.py`. Oczekiwane: wszystkie wybrane testy PASS, bez skippowania nowych regresji, błędów typów/lint lub zmian pinów/fixture/workflow.
- [ ] **Step 7: Commit lokalny.** Tylko pliki Task 2. Bez push/nowej bazy.

### Task 3: Końcowa kontrola zakresu i przekazanie

**Files:** ten plan oraz krótkie wpisy `docs/CHANGELOG.md`, `docs/TASKS.md`, `docs/JOURNAL.md`. Bez kolejnego raportu z powtórzoną historią.

**Interfaces:** consumes oba commity lokalne, wyniki regresji, allowlistę 7+4; produces commit dokumentacji i jeden zrecenzowany kandydat.

- [ ] **Step 1: Sprawdzić domknięcie zakresu.** Nie więcej niż 11 wymienionych plików; backend/app, migracje, frontend, workflow, requirements, conftest i oba stare worktree bez zmian.
- [ ] **Step 2: Kontrola źródeł.** Oficjalne OpenCode Commands potwierdzają obsługę istniejącego singular `command/` i wykonywanie `!` blocks poza uprawnieniami agenta. Nie wprowadzać `!` blocks, rename lub restartu serwisu.
- [ ] **Step 3: Walidacja końcowa do 180 s.** Nowe contract tests + cała istniejąca suite `test_ci_tools`, lint i typy jak w Task 2, `git diff --check`, linki dokumentacji. Podawać rzeczywiste liczby i ostrzeżenia; nie deklarować pełnego backend PASS na podstawie kolekcji. Stop przy niezgodnym środowisku/timeout; bez retry lub instalacji.
- [ ] **Step 4: Jeden readonly review całości.** Priorytety: interpreter/root, fail-closed, env/netns/bootstrap, brak realnych tooli wymaganych w matrix testach i brak rozszerzenia zgód DB. Critical/Important poprawić testem RED→GREEN przed publikacją.
- [ ] **Step 5: Wpisy sesji i commit.** Opisać zakres, decyzje, wynik i granice. Nie aktualizować teraz starych raportów produkcyjnych lub tasku DTZ007. Jedna gałąź/PR zawiera kod i dokumentację.
- [ ] **Step 6: Handoff.** Bez zgody na publikację zatrzymać się na lokalnym kandydacie. Po jawnej zgodzie: jeden push i draft PR, jeden automatyczny CI. Ewentualne failure rozliczyć bez automatycznego retry. Merge/deploy zawsze poza tym planem.

## Self-review i przekazanie

- Pokrycie: Task 1 odpowiada za metadane/preflight, Task 2 za wykonanie promptów, Task 3 za zakres i odbiór. Pięć Review Focus ma wskazane testy.
- Zależność jest sekwencyjna: Task 2 używa CLI z Task 1 i tego samego pliku testów; nie rozdzielać implementacji między równoległych agentów.
- Proponowana realizacja: **Native**, potem jeden świeży reviewer. Nie rozpoczynać jej przed zatwierdzeniem tego planu.
- Etap planowania nie uruchomił testów lub środowiska, nie zbudował helpera i nie zmienił komend/metadanych. Plan i notatki lokalne pozostają bez commitu/push.
- Readonly przegląd wykonalności wykazał dwie niejednoznaczności: układ root/fixture oraz dokładny env wywołań Git. Doprecyzowano oba kontrakty i przypisane testy; pozostałych blockerów reviewer nie zgłosił. To nie jest wynik uruchomienia testów ani review przyszłej implementacji.

Źródła: [OpenCode Commands](https://opencode.ai/docs/commands),
[zgodność V1/V2](https://opencode.ai/docs/migrate-v1),
istniejący `.github/workflows/ci.yml` i `backend/ci_tools/runner.py`.
