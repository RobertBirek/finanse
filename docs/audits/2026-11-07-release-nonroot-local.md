# Pakowanie kodu i offline import non-root — odbiór lokalny

Data:2026-11-07. Status: **odebrane lokalnie**, bez merge/push/deploy.
Zgoda: user „tak” na pełny mały zakres przedstawiony w czacie. Nie jest to zgoda na
merge/push/deploy, zmiany obecnego pakietu a68d9e4, danych, funkcji finansowych lub DB.

## Zmiana

- `ops/prepare_release.py`: wyłącznie wyekstrahowany backend ma dirs0755,
  files0644/executable0755. Umask077 nie pozostawia nieprzechodnich katalogów.
  Źródłowe archiwum/bajty/distinput i prywatny release root0700 pozostają bez zmian.
  Archive links odrzucane przed ekstrakcją/normalizacją, bez podążania chmod za linkiem.
- `ops/verify_release.py`: nowa bramka gotowych lokalnych backend/worker images.
  Numeryczne UID:GID są wymagane osobno z docelowego Compose, root/namedusers odrzucone.
  OCIrevision musi odpowiadać release.json; uruchamiane są rozpoznane niezmienne IDs.
- Kontenery próbne: unikalne nazwy, `--pull never`, `--network none`, read-only,
  cap-dropALL/no-new-privileges, bez mountów/envfile/sekretów hosta. Czyszczą inherited
  env, zmieniają cwd aby nie czytać /app/.env, używają syntetycznych settings.
  Odczyt plików aplikacji i import `app.main:app`/`app.worker.WorkerSettings` bez startupu,
  lifespan/ARQ/jobów/połączeń DB/providerów. Timeout kończy próbę i usuwa tylko własną nazwę.
- JSON sukcesu dotyczy dokładnych IDs/użytkowników. `.opencode/command/deploy.md`
  i runbook wymagają bramki po buildzie i przed Composeup oraz ponowienia po rebuild/
  retag/userchange. Błąd oznacza STOP, nigdy fallbackroot lub productioncredentials.
  To obowiązkowy krok operatora, nie mechanizm automatycznego wdrażania lub blokowania
  każdej możliwej ręcznej komendy Docker na hoście.

## Testy i dowody

- Baseline8prepareunitPASS,2proxyDeselected.
- Trzy unitRED (umask077+symlink/hardlink), po normalizacji11preparePASS.
- Verifier14RED (brak nowego narzędzia), po implementacji25combinedunitPASS;
  wszystkie ops46PASS/6proxyDeselected.
- Rzeczywisty Docker: **6PASS** — publicfrontendread good/tamperedfail oraz backend
  goodprivatepackage/nonroot UID10001 i20002, unreadablenesteddirFAIL, workerimportFAIL,
  missingentrypointFAIL. Tylko syntetyczny kod, nowe disposable tags/images usunięte.
- Pierwszy Dockerprzebieg5PASS/1FAIL: cached COPY ukrył zmianę tylko trybu katalogu.
  Diagnostyka stat w obrazie wykazała755 mimo700 input. Test buduje `--no-cache`, żeby
  sprawdzać faktycznie uszkodzone wejście. Po korekcie6PASS; wynik początkowy zachowany.
- Dodatkowo bramka na istniejących niezmiennych obrazach a68d9e4, w **nowych izolowanych
  kontenerach**, syntheticenv: main/worker importPASS, UID10001, odczyt147plików nausługę.
  Nie używano produkcyjnego Compose/envfile/mountów/DB; to nie jest ponowny deploy.
- Końcowe **931backendunit PASS**,888deselected (DB/proxy),2znanewarnings,34.98s;
  **540frontend PASS**86plików,44.72s. Ruff app/tests/ops, mypy149plików, ESLint i tsc
  PASS. To dostępny unit/static workflow, nie odbiór testów wymagających PostgreSQL.
  Oddzielne6Docker PASS71.75s obejmuje nowe zachowanie i wcześniejsze nginxregresje.
- Próba barepytest z celowo niedopuszczonym portem1:931PASS/829SKIP/45setupERROR
  istniejących owned-schema fixtures categorytreeapply/guard/entitycolors. Te fixtures
  assertują poprawny DSN, zamiast pomijać test. Nie połączono żadnej DB. To **nie jest
  pełny PASS backendu**; dla scope bez DB uruchomiono jawnie `not integration and not proxy`.
  Nie zmieniono guardów ani testów finansowych, nie użyto baz innych zadań.
- Nowy niezależny read-only review: `ses_e497f13f7ffeATXTdL0Av6fQeo`, **Approve**,
  bez Critical/Important/Minor. Brak kodowych zmian po review.
- Logi/proof/komendy: `/tmp/opencode/release-nonroot-20261107/`.
- CLI z rootUID kończy się1, pusty stdout, bez deploymentproof; pozostałe próby
  usunięte, brak kontenerów `finanse-release-probe-*` i obrazów `release-nonroot-test`.
  Sprawdzony pusty diff applicationcode/migrations/frontend względem bazowegoa1cc6b8.

## Decyzje wykonawcze i ograniczenia

- Weryfikator po buildzie, zamiast importu w Dockerfile: potrzebny jest rzeczywisty
  docelowy Compose user, a nie USER obrazu, oraz syntetyczne środowisko. Ryzyko:
  operator może ominąć obowiązkowy krok; dokumentacja wymaga STOP bez dowodu i
  porównaniaIDs. Preparer i verifier same nie przełączają usług.
- Dodatkowe odrzucenie links przed normalizacją jest ochroną przed chmod poza kopią,
  nie przebudową kontraktu finansowego. Archiwa Git projektu nie potrzebują links.
- Brak nowej testDB w zatwierdzonym zakresie: jawny unit gate zamiast udawania pełnego
  backendu. Ryzyko nieprzebadanej regresji DB ogranicza niezmieniony applicationcode;
  nowa automatyzacja ma unit i prawdziwe offlineDocker acceptance. Nie przenosić
  poprzedniego1788PASS jako świeżego wyniku tej sesji.
- Samo `not integration` nie wystarczyło:6DBcases w istniejącym `test_entity_colors.py`
  nie mają markera. Drugi run931PASS/6setupERROR; końcowy wybór jawnie deselectuje
  `test_color_services_persist_reset_and_preserve_ledger`,
  `test_color_api_is_owner_scoped_persistent_and_database_checked`,
  `test_color_migration_is_additive_and_preserves_legacy_ledger`,
  `test_color_downgrade_refuses_saved_preferences_before_dropping_any_column` (2param),
  `test_color_empty_downgrade_reupgrade_preserves_legacy_rows`. Nie naprawiano tych
  niezwiązanych testów; wszystkie początkowe nodeIDs/błędy są w `full-pytest.log`
  oraz `unit-pytest.log`, a końcowy unit run ma osobny `unit-pytest-final.log`.
- Bez zmian oryginalnych uploads/sekretów/runtimeuser/env/aktywnych images/policies.
  Produkcja pozostaje na wcześniej odebranym a68d9e4; nie sprawdzano jej ponownie.

### Granice review

Reviewer nie oceniał rzeczywistych wyników testów, finalnego rendered Compose ani
live deploy/DB/providerów. Wykonawca sprawdza zakończone logi testów; przyszły operator
ma obowiązek podać i porównać prawdziwy UID:GID/IDs przed rollout. Lokalny test
użytkowników10001/20002 nie dowodzi konfiguracji przyszłego wydania. Nie ma obietnicy
zmiany/certyfikacji obecnej produkcji, odłożonych Minor lub dodatkowych funkcji.
