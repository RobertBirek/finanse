# Preflight V2 — lokalny odbiór kodu

Data odbioru: 2026-11-18. Zakres: plan
`2026-11-17-preflight-trust-and-reviewed-tooling`, baza `fa7b470`.
**W toku: końcowy review. Kontrole Task6 PASS. Nie jest to odbiór produkcji.**

## Zrealizowane granice

- Root-owned przypięte Git/Docker/bezpośredni ComposeV2, czyste środowisko,
  zamknięta gramatyka argv,10s timeout i wspólny limit stdout/stderr.
- Snapshot zatwierdzonych bajtów Compose/env, tokenowe przepięcie env_file,
  zachowanie project_directory/merge/tagów/aliasów, odmowa obcych czytników.
  Drift/cleanup failure blokuje wynik; nie obiecujemy secure erase.
- PG: konkretny container/image, nonroot OS UID:GID oddzielny od roli DB,
  env-i/Unix socket/port/no rc/no password i jeden literalny readonly SELECT.
- Zewnętrzny launcher stdlib weryfikuje runtime/members/receipt i osobne piny;
  checker nie importuje kandydata ani nie wystawia bypassu. Packager nie instaluje,
  nie wydaje zgód i nie pobiera źródeł. Zmiana narzędzi wymaga osobnej akceptacji.
- Scope review wiąże wszystkie baseline, candidate, bundle i dokładne Git
  mode/blob/content. Nie usuwa ścieżek z diffu; obce ops/CI nadal blokują.
  `.dockerignore` zachowuje dawną ocenę runtime/build, nie zwolnienie tooling.
- RaportV2 zawsze unauthorized/not-production-ready; blocked usuwa fakty.

## Testy i źródła dowodów

- Baseline91preflightPASS; Task1 26RED→GREEN, Task2 18RED→GREEN,
  Task3 30regresji, Task4 29regresji. Poszczególne commity:
  `47ec38e`, `415a420`, `ea39eee`, `e987067`.
- Trzy pierwotne problemy mają konkretne regresje:
  `test_inherited_path_cannot_substitute_git_or_docker`,
  `test_mutation_after_hash_never_changes_consumed_bytes`,
  `test_pg_endpoint_is_explicit_and_inherited_libpq_is_erased`.
- Task5 `550a84f`:217offlinePASS82.01s, launcher23PASS w tym subprocess `-O`.
  Kanoniczne lint/types, mypy220 aplikacji,719Vitest i Ruff/mypy8opsPASS.
  Backend komenda projektu to **kolekcja**, nie wykonanie wszystkich test bodies.
- Task6 obejmuje syntetyczny exact proof + różne baseline + prawdziwe czytanie
  snapshotów przez fake tools + jedno PGexec + cleanup + raport, także schema już
  zmigrowany po rollbacku aplikacji. Failures mutation/timeout/cleanup bez sukcesu
  i bez canary w raporcie. Pierwsze3FAIL były błędnymi założeniami nowych testów,
  nie poprawkami produkcyjnego kodu;12PASS po dopasowaniu do istniejących gates.
- Końcowy zestaw offline Task6: **230PASS124.48s** (dodano również wariant
  już zmigrowanego schematu po rollbacku aplikacji z dokładnym tooling proof).
- Kanoniczne lint/types/kolekcja backendu/719Vitest oraz Ruff/mypy8ops i
  `git diff --check` PASS. Brak deklaracji pełnego CI lub testów backendDB.
- Wszystkie testy ops offline w odciętej sieci, syntetyczne Git/pliki/procesy.
  Bez fixtureDB, realnego Dockera/PG/AI, build/deploy, migracji lub danych finansowych.

## Otwarte bramki

1. Końcowy świeży review całego slice i weryfikacja jego ustaleń.
2. Osobna zgoda na publikację/merge/push i CI dla dokładnego SHA.
3. Osobny przegląd i akceptacja rzeczywistych artefaktów tooling/runtime,
   manifestu toolchain, raportu/scope proof oraz jawne piny administratora.
4. Zgoda na readonly acceptance rzeczywistego środowiska. Testy nie certyfikują
   formatu aktualnych metadanych, PG auth, obrazu ani produkcyjnego YAML.
5. Backup/restore, pełna retencja, rollback, nonroot images, dokładna migracja
   i spójny rollout/runtime nadal pozostają osobnymi bramkami.

Nie utworzono realnego inventory/receiptu zgody/pakietu produkcyjnego. Historyczny
blocked V1 pozostaje w historii; nie deklarujemy ponownego sukcesu V1.
