# Preflight V2 — lokalny odbiór kodu

Data odbioru: 2026-11-18. Zakres: plan
`2026-11-17-preflight-trust-and-reviewed-tooling`, baza `fa7b470`.
**Review i kontrole lokalne PASS. Nie jest to odbiór produkcji.**
Dokładny zakres kodu/testów/procedury: `fa7b470..d451698`.
Końcowy commit dokumentacji nie zmienia wykonywanego kodu.

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
- Powtórzona końcowa weryfikacja po review:230offlinePASS129.74s i wszystkie
  powyższe kontrole PASS. Brak zmian wykonywanego kodu po `d451698`.
- Wszystkie testy ops offline w odciętej sieci, syntetyczne Git/pliki/procesy.
  Bez fixtureDB, realnego Dockera/PG/AI, build/deploy, migracji lub danych finansowych.

## Otwarte bramki

1. Świeży review całego slice zakończony:0Critical/0Important/0Minor,
   wszystkie5ReviewFocus i wszystkie ledger rulings ocenione, bez declined items.
   Reviewer uruchomił24syntetyczne testy:24PASS23.56s. Nie było poprawek kodu po review.
2. Osobna zgoda na publikację/merge/push i CI dla dokładnego SHA.
3. Osobny przegląd i akceptacja rzeczywistych artefaktów tooling/runtime,
   manifestu toolchain, raportu/scope proof oraz jawne piny administratora.
4. Zgoda na readonly acceptance rzeczywistego środowiska. Testy nie certyfikują
   formatu aktualnych metadanych, PG auth, obrazu ani produkcyjnego YAML.
5. Backup/restore, pełna retencja, rollback, nonroot images, dokładna migracja
   i spójny rollout/runtime nadal pozostają osobnymi bramkami.

Nie utworzono realnego inventory/receiptu zgody/pakietu produkcyjnego. Historyczny
blocked V1 pozostaje w historii; nie deklarujemy ponownego sukcesu V1.

## Decyzje wykonawcze (Rulings I made)

1. Dopuszczono root-owned sticky ancestor jak `/tmp`, nadal weryfikując
   właściciela/tryby/hashe poddrzewa i pliku. Koszt błędu: niezaufany ancestor
   podważyłby tożsamość binarium; root pozostaje granicą zaufania.
2. Przeniesiono stabilny import fixture policy do Task3, aby reload nie tworzył
   różnych klas wyjątków. Koszt: testy nie symulują niewspieranego hot reload.
3. Scratch ze znakiem `$` blokuje drugą interpolację ścieżki przez Compose.
   Koszt: operator musi wybrać inną prywatną lokalizację, bez zmiany produkcji.
4. VerifiedToolingScope zawiera candidate/niemutowalne baseline/bundlehash,
   ReleaseFacts optionalbundlehash. Koszt: adapter musi przenosić ten kontekst;
   zapobiega to ponownemu użyciu witness dla innego stanu.
5. after_sha256 treści dotyczy tylko tooling; wszystkie pozostałe ścieżki,
   mode i GitIDs pozostają w diffie. Koszt: osobna weryfikacja runtime obrazów,
   bez udawania provenance binarnych assetów.
6. Packager wymaga jawnego dodatniego max_output_bytes przed toolchainmanifest.
   Koszt: dodatkowy wymagany parametr u wywołujących, bez cichego limitu produkcji.
7. Wspólne bounded capture_process dla runnera/packagera. Koszt: nowi callers
   nadal muszą mieć własną zamkniętą gramatykę argv.
8. Pozytywny adapter ma test-only cold harness z synthetic BootstrapContext.
   Koszt: nie certyfikuje realnych uprawnień/auth; produkcyjny CLI nie ma bypassu.
9. `.dockerignore` pozostaje dawnym runtime/build scope, nie zwolnieniem tooling.
   Koszt: ewentualne always-block wymaga osobnej jawnej decyzji o polityce.

Deferred minors: brak. Integracja/publikacja pozostają decyzją użytkownika.
