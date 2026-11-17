# Readonly release preflight — lokalny odbiór (2026-11-17)

## Zakres i zgody

Użytkownik zaakceptował [projekt](../superpowers/specs/2026-11-16-release-preflight-design.md),
[plan](../superpowers/plans/2026-11-16-release-preflight.md) i Native, następnie
samodzielny dobór/instalację środowiska. Baza: `b5c212a`, zastany linked worktree.
Nie wykonywano push, merge, CI, deployu, prawdziwego Docker/PG, mutacji danych
ani odczytów produkcyjnych. Nie zmieniono aplikacji, migracji ani zależności.

## Co dostarczono

- Czystą politykę czterech akcji: no_rollout/app_only/migration_then_app/blocked.
- Statyczny AST kompletnego liniowego grafu, bez importu/wykonywania migracji.
- CLI `ops/release_preflight.py --check`: pełne SHA każdej usługi, inventory
  i digests, rzeczywiste odczyty usług/configu/capabilities oraz stały readonly
  odczyt schematu. Nie ma apply/repair ani automatycznego issuera inventory.
- Procedurę użycia i bramkę w `/deploy`, bez pomijania wcześniejszych kontroli.

Exit0 nie przyznaje zgody. Każdy raport ma authorized=false/production_ready=false
i jawnie nie poświadcza image-content provenance lub zewnętrznego configu.
Brak/zmiana danych blokuje; nie adoptować obserwacji, aby „naprawić” inventory.

## Środowisko i metoda

Wybrano istniejący
`/tmp/opencode/backend-test-env-20261114/run-302e8d4cb8/venv/bin/python`.
Trzy `ops/dev_environment.py --check test|lint|typecheck` przeszły, więc nie
instalowano pakietów. Stary `/opt/finanse/backend/.venv` nie spełniał pinów;
nie aktualizowano go. Frontend użył zastanych node_modules.

`/lint`, `/typecheck`, `/test`: wykonano całe niezmienione bloki Bash z odpowiednich
plików `.opencode/command/*.md` z jawnym ADVISOR_DEV_PYTHON. Bez natywnego narzędzia
wywołania slashcommand jest to wykonanie jej opublikowanego kontraktu, nie fallback
omijający preflight. Backend `/test` to **kolekcja**, nie wykonany pełny suite.

Konkretne unit tests uruchamiano przez `sudo -n unshare --net`, `setpriv` z UID/GID
wywołującego, no-new-privileges i czyste env/syntetyczne DSN127.0.0.1:9.
Wykonano tylko pliki `backend/tests/test_ops/test_release_preflight_policy.py`,
`test_release_preflight.py`, `test_release_policy.py` i `test_verify_release.py`.
Nie oznaczono ich integration, nie wydawano DBpermit i nie wykonywano fixtureDDL.

Testy CLI tworzą własny Git/tmp_path i argv-strict fake Docker w prywatnym PATH.
Uruchamiają prawdziwy CLI, także Python `-O` i bez `-B`; atrapą jest wyłącznie
zewnętrzny Docker, nie polityka/collector/CLI. Canary w odpowiedziach/config/env
nie trafia do stdout/stderr. Każda komenda spoza słownika atrapy kończy test błędem.

## Dowody przed końcowym review

| Kontrola | Wynik |
|---|---|
| Baseline Ruff/ESLint, mypy215/tsc | PASS |
| Baseline backend collection, Vitest | PASS; 707/707,55.02s |
| Policy RED→GREEN | 39 przypadków braku modułu, potem39/39PASS |
| CLI RED→GREEN | 45 przypadków braku CLI, potem45/45PASS |
| Dodatkowe edge RED→GREEN | dependencies/nested migration; bytecode bez-B |
| Nowe i powiązane offline unit | 134/134PASS,37.99s |
| Ruff/mypy nowych ops i testów | RuffPASS; mypy2modułyPASS |
| Końcowe przed review /lint /typecheck | PASS; mypy215/tsc |
| Backend `/test` | Kolekcja offline PASS, nie pełne testy DB |
| Pełny Vitest przed review | 707/707PASS,56.06s |
| Ponowienie po review | 134unitPASS37.84s; lint/types/kolekcjaPASS;707Vitest59.86s |

Końcowe hashe kodu (wszystkie4pliki również w zachowanym `sources.sha256`):
- CLI: `d3b892bedf37626c4dc69971a1652a0edabc7ad5cf04c9111475a1044e8bb00a`.
- Policy: `6961b1e92784ae4283765467ad962f17b69995fcfe72b38b82f63a87646942ed`.

Pierwsze wspólne wywołanie trzech komend przerwał timeout120s narzędzia przed
wynikiem Vitest. Log nie pokazywał błędu testu; brak pozostawionych procesów.
Nie zmieniano timeoutów/asercji/testów. Sam niezmieniony `/test`, uruchomiony
z większym limitem narzędzia, zakończył się PASS. Pierwszy przebieg nie jest dowodemPASS.

## Decyzje wykonawcze i koszt błędnej decyzji

1. Dobór zgodnego istniejącego interpretera po jawnej zgodzie, bez instalacji.
   Jeśli błędny: lokalne wyniki nieważne, wymagane ponowienie preflight/kontroli.
2. Wykonanie opublikowanych bloków slashcommand, bo katalog narzędzi nie udostępnia
   ich natywnego wywołania. Jeśli format się zmieni: zatrzymać zamiast obejść bramki.
3. Osobny `/test` po timeout całego wielokomendowego narzędzia, z niezmienionym
   kontraktem. Jeśli przyczyna inna: pierwszy przebieg nadal nie stanowi dowoduPASS.
4. Nagłówki Task1→Task 1 dla parsera helpera task-start, bez zmiany zakresu.
   Jeśli błędne: brak ekstrakcji briefu, nie niejawne pominięcie zadania.
5. V1 odrzuca nonnull branch_labels/depends_on i nested versions Python, zamiast
   udawać kompletny liniowy graf. Jeśli nadmiernie restrykcyjne: potrzebny nowy
   jawny kontrakt, kosztem ręcznej kwalifikacji, nie fałszywego GO.
6. CLI wyłącza source-tree bytecode przed lokalnym importem policy, także bez-B.
   Koszt jeśli błędne: pomijalny narzut CPU bez użycia cache.
7. Realny Docker/PG, adapter active metadata i deploy pozostają poza tym odbiorem.
   Koszt pominięcia przyszłego odbioru: brak dowodu integracji; wymagany osobno.
8. Provenance, konfiguracja/mounty/ingress, health, backup/restore i rollback
   pozostają osobnymi bramkami, nie funkcją V1. Koszt ich pominięcia: niewykryte
   problemy runtime/danych; raport narzędzia nigdy ich nie poświadcza.
9. Złośliwy root/sameUID, PATH executable lub zmiana zatwierdzonego inventory
   pozostają poza modelem zagrożeń. Koszt naruszenia założenia: fałszywe obserwacje;
   narzędzie wymaga zaufanego operatora i niezależnej akceptacji.
10. Reviewer nie powtarzał testów w swojej readonly roli; opieramy wykonanie na
    świeżych logach implementera. Koszt błędnego raportu: brak niezależnej
    reprodukcji; zachowane logi i źródła umożliwiają ponowienie.
11. Nie audytowano obcej historii worktree ani prywatnych metadanych produkcji.
    Koszt jeśli są rozbieżności: potrzebna osobna kwalifikacja integracji/runtime,
    bez niejawnego merge lub adopcji celu.

## Granice dowodu i następny krok

Logi lokalnych kontroli zachowano poza tymczasowym ledgerem w prywatnym
`/tmp/opencode/release-preflight-local-20261117.QQeVlHP2/`.

Jeden świeży readonly review całości: **bez Critical, Important lub Minor**;
ocena „Ready to merge: Yes”. Przejrzano zakres od `b5c212a` wraz z working overlay
Task3. Bez drugiego review; nie było findingów wymagających fixpass. Nie jest to
zgoda na merge, push, produkcyjny odczyt lub deploy. Brak odroczonych minorów.

Format rzeczywistego active metadata, PG w docelowym kontenerze, rzeczywisty Compose,
image provenance/config/health/cookies/retention **nie są tu zweryfikowane**.
Realne użycie wymaga osobnej zgody i zatwierdzonego inventory. Ops/workflow diff
zostaje blocked/manual review — nie dodawać wyjątku dla własnej zmiany, aby uzyskać GO.
