# Journal

Techniczny dziennik sesji. Kontekst dla agentów w nowych sesjach.

## 2026-10-23 — Webapp testing po wdrożeniu UI

- Na prośbę użytkownika: Python Playwright/system Chrome, produkcja w320/375/768/
  1440px, cztery ścieżki wymagające auth/logowania. Redirect/native validation,
  lokalne fonty, brak overflow/pageerrors/external requests PASS; API health200,
  documents/finance/accounts/work/tasks/advisor/conversations401.
- Nie wysyłano login POST ani mutacji; nie zgadywano haseł. Brak autoryzowanej
  sesji wyklucza potwierdzenie produkcyjnych operacji zalogowanego użytkownika.
- Axe na login375/1440: zero naruszeń wybranych reguł WCAG A/AA. Kontenery aplikacji
  działają bez restartów/OOM. Nie jest to certyfikacja pełnej dostępności/stabilności.
- Pełny E2E na dokładnym release8a7cda5/frontend-dist:29 PASS +1celowy mobile-only
  skip. Hash JS/CSS/fontów równy produkcji. Vitest194, ESLint/tsc PASS.
- Raport docs/audits/2026-10-23-webapp-test.md; prywatne screenshoty/logi w
  /tmp/opencode/webapp-test-8a7cda5. Bez zmian kodu, konfiguracji i deployu.

## 2026-10-23 — UI8a7cda5 frontend-only wdrożone

- Osobna zgoda użytkownika; zastosowano pełny stack base/prod/6811809-active/new
  release, --no-deps --no-build --pull never tylko frontend. Backup/restore cfc7102f
  potwierdzone success/0 przed przełączeniem.
- HTTPS/health200, anonymous documents401; hashe JS/CSS/obu fontów zgodne z pakietem.
  Chromium375px: redirect do login, fonty loaded, brak JS errors. Brak restartów/OOM
  i błędów startu frontend. Zalogowane UI zweryfikowane wcześniej na fixtures,
  nie deklarujemy uploadu/logowania kontem użytkownika na produkcji.
- Backend/worker pozostają6811809 i zachowały IDs, tak samo Stirling/PostgreSQL/Redis.
  Refaktor finansów e5eeb2a nadal poza produkcją. Brak migracji/ACL/resetu retry.
- Skonsolidowany active override zgodny z rendered runtime; active-release.json
  zaktualizowany po weryfikacji. Rollback8a7cda5/rollback.sh przywraca tylko frontend.

## 2026-10-23 — Audyt i poprawki UI/UX, bez wdrożenia

- Po osobnej zgodzie scalono i wypchnięto 8a7cda5 do main. Release frontend-only
  przygotowany pod /opt/finanse/webapp/releases/8a7cda5, bez przełączenia produkcji.
  Backend/worker pozostają6811809; nie dołączono automatycznie refaktoru e5eeb2a.
- Backup/restore cfc7102f success/0. Ponowione lint/tsc/build,194 Vitest i29 E2E PASS
  (+1 mobile-only skip). Frontend image sha256:9776414c003c2afe0f29462fbae6a3a2b1da0168c78ddd59e1075c3c8cb380d8;
  fonty/assets zweryfikowane hashami w kontenerze network-none/read-only/cap-drop.
- Rendered Compose zmienia wyłącznie image/build frontend; wszystkie inne definicje
  usług i hardening bez zmian. Rollback aplikacji ograniczony do frontendu6811809.
  Generatorowi usunięto backend/worker Dockerfiles i override entries w prywatnym
  pakiecie, aby nie można było przypadkiem wdrożyć szerszego zakresu. Active metadata
  i działające kontenery bez zmian; deploy wymaga osobnego zatwierdzenia.

- Użytkownik zatwierdził zakres oraz paletę/typografię po audycie 4 ekranów x2
  viewporty na syntetycznych fixtures. Screenshots: /tmp/opencode/uiux-audit.
- Naprawiono znikającą nazwę konta (konkurencja flex z akcjami), zawijanie nazw
  kont/kategorii, przyciski44px, błędy z retry i tekstowe loading states.
- Dzisiaj: kolejność DOM zgodna z wizualną, plan sortowany po początku, „Teraz”
  wyłącznie gdy start<=now<end. Agenda mobilna zwarta, wszystkie wpisy zachowane.
- Paleta ink/surface/muted, lokalne fonty z OFL i hashami w public/fonts/README.md;
  brak zewnętrznych żądań fontów. Koszt ok.756KB TTF, WOFF2 odłożone do backlogu.
- RED: konta/touch/agenda/retry; osobny test DOM wykrył problem CSS-only reordering.
  Axe wykrył kontrast btn-danger4.37:1; rozjaśniono tekst do red300, nie wyłączano axe.
  Próg szerokości nazwy zastąpiono rzeczywistą kontrolą clippingu, bo nowy font jest węższy.
- Backend642 PASS (8 proxy deselected), frontend194 PASS, lint/typecheck/build PASS.
  Końcowe E2E i niezależny review w toku; screenshoty po zmianach potwierdzają
  czytelne nazwy kont, 7 dni agendy na ekranie375px i załadowane lokalnie fonty.
  Brak backend/API/migracji/zmian danych użytkownika i brak deployu.
- Finalny gate: E2E29 PASS +1 celowe pominięcie desktop dla mobile-only agendy,
  frontend194/backend642 PASS, lint/types/build/diff PASS. Axe cztery ekrany x2
  viewport bez naruszeń wybranych reguł WCAG A/AA (nie pełna certyfikacja).
- Review bez blokad. Po sugestiach dodano test kolejności niesortowanych bloków
  i granicy start<=now<end oraz assertClean po retry. Dodatkowe testy trzech
  retry w przeglądzie finansów odłożone do backlogu, podobnie jak WOFF2.

## 2026-10-23 — Refaktor finansów, bez wdrożenia

- Po audycie użytkownik zatwierdził podział finance.service (983 linie, 27 zmian
  w historii) jako ograniczony refaktor. Plan: docs/superpowers/plans/
  2026-10-23-finance-service-refactor.md; baza 11a331a, istniejący linked worktree.
- Publiczna fasada 63 linie; implementacje transactions/reporting/budgets/cashflow,
  wspólne helpers dates. Leaf modules nie zależą od facade. Kontrakty importów
  i sygnatur zachowane; prywatne monkeypatch targets przeniesione do właścicieli.
- Ruling: atomowe przełączenie fasady zamiast czterech commitów pośrednich
  z powieloną logiką — jeden większy commit mechanicznego przeniesienia, bez deployu.
- Baseline 207 finance/integrity PASS. Nowe testy brakujących modułów RED (5),
  po ekstrakcji 15 jednostkowych PASS; Ruff/mypy PASS. AST: 27 funkcji identycznych,
  get_budget_status ma jedynie wydzielone descendants, przetestowane branch/cycle.
- Frontend 194 PASS i ESLint/tsc PASS. Pełny backend i świeży review w toku.
  Bez zmian query count/SQL, pending, księgi, migracji, zależności i produkcji.
- Końcowy backend 642 PASS, 8 testów proxy deselected, Ruff/mypy PASS; dwa
  istniejące warningi crypt/argon2. Pozostał wynik niezależnego review przed commitem.
- Finalny review: bez ustaleń blokujących, niezależne potwierdzenie zgodności AST,
  importów publicznych, kierunku zależności, SQL i blokad. Odłożone drobiazgi:
  dodatkowe asercje starych aliasów query/entities oraz dokumentacja prywatnych
  helperów dla potencjalnych zewnętrznych testów/pluginów (brak konsumentów w repo).
  Zakres lokalny zakończony; scalenie/wypchnięcie i deploy wymagają osobnej decyzji.

## 2026-10-23 — Produkcja 6811809 wdrożona

- Osobna zgoda użytkownika na backend/worker/frontend. Backup da7eb2d7 i izolowany
  restore success/0 przed przełączeniem. Początkowy start-limit-hit systemd
  usunięto reset-failed; nie był to błąd wykonania skryptu backupu.
- Stirling gotowy, queue 0; zatrzymano aplikację i wymieniono tylko trzy obrazy.
  Bez migracji, zmian ACL, restartu Stirling lub resetowania dokumentów/retry.
- HTTPS/health/assets PASS, anonymous documents 401. Rewizje, effective UID10001,
  read-only/cap-drop/no-new-privileges, limity, brak host /app i logi PASS.
  PostgreSQL/Redis/Stirling zachowały container IDs; brak restartów/OOM aplikacji.
- Skonsolidowany compose.active.yaml ma identyczny rendered runtime z zatwierdzonym
  stackiem (bez metadanych build). Metadane aktywne wskazują 6811809, rollback
  do c765ea9 zachowuje zabezpieczenia. Smoke bez mutacji danych użytkownika.

## 2026-10-23 — OCR szerokich obrazów: implementacja bez wdrożenia

- Release 6811809 przygotowany w /opt/finanse/webapp/releases/6811809;
  lokalny i zdalny main wskazują 681180991f5478b2cf7699635924d9d8e6ff0399.
  Ponowiony gate integracji: backend 636 PASS, frontend 194 PASS,
  Ruff/mypy/ESLint/tsc/build PASS. Backup 23bcbccb i restore drill success/0.
- Obrazy backend/worker/frontend zbudowane, finalne digesty przypięte w Compose;
  hashe kodu i requirements w runtime sprawdzone. BuildKit nie rozwiązywał lokalnych
  baz po digest: użyto dedykowanych tagów z kontrolą ID przed/po buildzie.
- Forward wymaga base + prod + c765ea9/compose.active.yaml + nowy compose.release.yaml.
  Render różni się tylko obrazami/metadanymi build aplikacji; hardening i Stirling
  zachowane. Rollback do c765ea9 przygotowany. Wdrożenie niezatwierdzone/niewykonane;
  active-release.json pozostaje c765ea9, bez migracji, zmian ACL i resetowania retry.

- Użytkownik zatwierdził małą zmianę w konwersji: zachowanie proporcji i dobór
  orientacji strony. Praca w istniejącym izolowanym worktree, baza 94e1b5e.
- Źródła Stirling v2.14.3 potwierdzają fillPage jako default oraz obsługę
  maintainAspectRatio/autoRotate. Wybrano dopasowanie do A4 bez przycinania;
  fitDocumentToImage odrzucone (rozmiar strony zależny od liczby pikseli).
- RED: cztery przypadki HTTP multipart nie zawierają fitOption; staging przez
  rzeczywisty helper workera wykazuje skale 0,3307 i 1,2027 dla obrazu 1800x700.
- GREEN unit: po dodaniu pól maintainAspectRatio i autoRotate=true 12 testów
  workera PASS; Ruff/mypy PASS. Staging sprawdza macierz obrazu, orientację,
  granice strony, polski tekst oraz hashe syntetycznych plików na dysku.
- Pełny gate i niezależny review trwają. Produkcja, oryginały użytkownika, stare
  błędy/statusy i retry bez zmian. Nie dodano migracji, zależności ani nowego obrazu.
- Review nie wykazał regresji implementacji; wskazał możliwość rozszerzenia stagingu
  o helpery OCR/ekstrakcji tekstu. Decyzja: odłożone jako ulepszenie pokrycia,
  nie blokada tej poprawki — zmieniany helper konwersji jest wywoływany realnie,
  OCR/tekst pozostają niezmienione i mają testy parametrów, limitów i kompresji.
  Koszt: staging nadal nie jest pełnym testem całego pipeline aplikacyjnego.
- Staging GREEN: 1 test z pięcioma przypadkami (szerokie PNG/JPEG, pionowe PNG/JPEG,
  skan PDF) PASS w 160,40 s; polski tekst, geometria, hashe, non-root/read-only
  i zamknięcie PASS, /pipeline 16 KiB. Frontend 194 PASS, ESLint/tsc PASS.
- Finalny gate: backend 636 PASS, 8 proxy deselected (OCR staging uruchomiony
  osobno: 1 PASS); frontend 194 PASS; Ruff/mypy/ESLint/tsc/diff PASS. Dwa istniejące
  warningi crypt/argon2. Powyższe wpisy „w toku” są historią etapów, nie blokadą.
  Implementacja i review zakończone, deploy wymaga osobnej zgody.

## 2026-10-23 — Produkcja c765ea9 wdrożona

- Follow-up na zgodę „ok, działaj”: kontrola wyłącznie odczytowa ok. 12:31 CEST,
  po 9–11 minutach pracy usług. Brak restartów/OOM/nowych błędów; Stirling healthy,
  HTTPS/health 200 i anonymous documents 401. Queue 0, dokumenty nadal 1 done/2 error.
  Próbka RAM: backend 82,88 MiB/2 GiB, worker 61,05 MiB/1 GiB, frontend 9,05 MiB,
  Stirling 1,09 GiB/2 GiB; CPU wszystkich usług poniżej 1% w tej próbce.
- Pierwszy filtr logów błędnie uznał flagę JVM `ExitOnOutOfMemoryError` za awarię;
  potwierdzono, że to wydruk konfiguracji startowej, nie wyjątek ani OOM kill.
  Ponowna kontrola wzorca błędu wykazała tylko znany komunikat optional templates.
- Brak zmian aplikacji/konfiguracji produkcyjnej w follow-up. To krótki przegląd
  stabilności bez obciążenia; naprawa szerokich obrazów wymaga osobnego planu.
- Gate przed commitem dokumentacji: backend 632 PASS, 8 testów proxy deselected
  (nie uruchamiano ponownie stagingu); frontend 194 PASS, Ruff/mypy/ESLint/tsc PASS.
  Dwa istniejące warningi deprecacji crypt/argon2. Testy na izolowanej bazie testowej,
  nie na produkcji; diff check PASS.

- Użytkownik zatwierdził dokładny zakres przez „dokończ”. Zatrzymano aplikację
  i Stirling; świeży backup e45cdc85 oraz restore drill success/0.
- ACL helper z przypiętego obrazu: snapshot przed/po, brak default ACL, niezmienione
  owners/inodes/bytes; non-root read i lock PASS. POSIX mask zmienia grupowe bity stat.
- Skopiowano komplet 11 plików zatrzymanego Stirling do prywatnego katalogu release;
  stare katalogi bez zmian. Migracja c7f8c620460d: head, 3 kolumny, indeks PASS.
- Stirling HTTP health i walidator uprawnień PASS przed uruchomieniem workera.
  Wszystkie obrazy przypięte; effective UID, read-only, cap-drop, limity i sieci PASS.
- HTTPS/health/zasoby 200, anonymous documents 401; brak restartów/OOM i błędów
  backend/worker/frontend. Data IDs bez zmian, hashe oryginałów zachowane;
  dokumenty 1 done/2 error, queue 0. Nie wykonano mutujących smoke testów.
- active-release.json wskazuje compose.active.yaml: potwierdzona identyczność
  rendered runtime z czteroplikowym stackiem (bez metadanych build).
  Rollback: releases/c765ea9/rollback.sh; zachować ACL i nowe kolumny po ruchu.
- Pozostaje znany komunikat Stirling o read-only optional templates, problem
  szerokich obrazów fillPage i brak certyfikacji worst-case capacity.

---

## 2026-10-23 — Runtime non-root: lokalny zakres zakończony, bez wdrożenia

- Końcowy gate po poprawkach review: backend 632 PASS, osobno 8 testów
  proxy/kontener/ACL/OCR PASS (bez skipów w tej grupie), frontend 194 PASS;
  Ruff/mypy/ESLint/tsc/build/diff check PASS. Dwa istniejące warningi deprecacji
  crypt/argon2 nie blokują testów. Produkcyjna integracja Compose, ACL,
  nowy backup/restore, rollback i zatwierdzenie dokładnego release'u pozostają.
- Po zatwierdzonym rozszerzeniu patcha: staging OCR PASS (PNG/JPEG/skan PDF,
  także tekst z polskimi znakami). Potwierdzono effective UID/GID PID1/Java,
  read-only, /pipeline mode0700 i zużycie 16 KiB, poprawne zamknięcie bez OOM.
  Przetestowany obraz: `sha256:e0d315bd87b07b0ee411ea4a42a08e52c4a9267de4b69c552718eb400df8a9e5`.
- Niezależny review wskazał braki reprodukowalności helpera ACL i testów rollbacku,
  restore oraz effective UID. Poprawiono je: helper przeniesiony z ignorowanego
  ops/uploads do ops/upload-permissions, przypięta baza, etykiety i hashe kodu;
  pięć regresji odrzucania zmienionego inventory, test writer/lock po restore,
  odczyt tożsamości procesów. Testy ACL Docker 2 PASS, jednostkowe 6 PASS.
- Pusty OCR na szerokim obrazie odtworzony niezależnie od runtime: Tesseract
  czyta oryginał, ale nie obraz rozciągnięty przez domyślne fillPage do A4.
  Pozostaje osobnym defektem produktu; acceptance runtime obejmuje skany A4,
  bez deklaracji naprawy szerokich obrazów. Końcowy pełny gate po review w toku.
- Poniższe blokady dokumentują etapy diagnozy, nie aktualny wynik stagingu:
- Aktualna bramka BLOCKED: po poprawieniu połączenia health PASS, lecz runtime
  zmienia mode /pipeline z 0700 na 0755. Odczyt vendor init linie 887–914
  potwierdza bezwarunkowy `chmod -R 755` i fallback `chmod -R o+rwX/a+rwX`.
  Oryginalna hipoteza minimalnego patcha aliasów nie zapewnia zadeklarowanych
  uprawnień. Nie zmieniono oczekiwań testu. Potrzebna decyzja o rozszerzeniu
  patcha na root-oriented sekcję naprawy uprawnień i zastąpieniu jej ścisłą
  walidacją jawnie przygotowanych writable paths; reszta vendor startup bez zmian.
  OCR PDF/PNG/JPEG nadal NIE przeszedł bramki, produkcja nietknięta.
- Gałąź `fix/stirling-nonroot-runtime`, baza `962de8a`; zatwierdzony plan i brak
  default ACL. Produkcyjne Compose, uprawnienia i dane bez zmian.
- Dodano hash-guarded patch vendor init i Dockerfile z niezmienionym entrypointem,
  modelem pol przypiętym do commita i SHA-256. Unit RED→GREEN 4/4.
- Staging ujawnił bezwarunkowy zapis Java do /pipeline; po analizie źródeł
  i niezależnym review dopuszczono tmpfs 16 MiB UID1001 noexec/nosuid.
- Health wewnątrz kontenera zwraca 200. Docker nie przydzielił portu publikowanego
  na sieci internal (port 0); test używa teraz prywatnego IP bridge, bez publikacji.
  Pełny przebieg OCR jeszcze niepotwierdzony.
- Nowy runtime backendu: pip check/importy OK; 16 testów parsera UID10001,
  read-only/cap-drop PASS. Pytest uruchamiany z kopii testów w /tmp, aby uniknąć
  kolizji nazw pakietu /app/__init__.py z /app/app.
- ACL na syntetycznych plikach: 2 PASS (stare odczyty, atomic write, wspólny lock,
  rollback ACL, restore/reapply, brak dziedziczenia). Jawne UID:GID w testach.
- Ostatni pełny gate: backend 622 PASS, frontend 194 PASS; lint/typecheck/build OK.
  Kosztowne testy stagingowe uruchamiane osobno; review końcowy pozostaje otwarty.

---

## 2026-10-23 — Push main i zablokowany preflight wdrożenia

- Follow-up zatwierdzony do analizy/planu: potwierdzono ciągłe odtwarzanie
  aliasów przez vendor init (samo utworzenie symlinków w buildzie nie wystarcza)
  i brak modelu `pol` w obrazie. Przygotowano spec/plan
  `docs/superpowers/plans/2026-10-23-stirling-nonroot.md`; builder-check zakończony,
  doprecyzowano staging-only, manifest/rollback ACL, stały inode locka oraz
  przypięty model pol z SHA-256. Do potwierdzenia polityka bez default ACL.
  Propozycja: minimalny hash-guarded patch init, model pol w obrazie oraz
  test nazwanych ACL wyłącznie na kopii uploads, bez chown produkcji.
- Użytkownik zatwierdził push oraz release `f256a10` (backend/worker/frontend),
  migrację `c7f8c620460d` i hardening wyłącznie po stagingu, backupie i rollbacku.
- Push fast-forward do GitHub `main` potwierdzony: `f256a1067f674b3cf8a6c93315a018ac02d8967b`.
  Powtórzony gate: 617 backend, 5 proxy/container, 194 frontend PASS;
  Ruff/mypy/ESLint/tsc/build PASS.
- Wdrożenie ZABLOKOWANE. Izolowany test dokładnego obrazu Stirling 2.14.3
  `frooodle/s-pdf@sha256:3b3670fce70b396ec56ba380a3cc7858e0abf83fe13f31c88f7737847763a396`
  jako `1001:1001`, read-only/cap-drop/no-new-privileges, network none,
  z tymczasowymi mountami zakończył się exit 1 przed startem API:
  `ln: failed to create symbolic link '/usr/local/bin/diagnostics': Read-only file system`.
  Testów OCR nie wykonano, bo aplikacja nie wystartowała. Produkcyjnych mountów
  ani kontenerów nie zmieniano.
- Dodatkowe bramki: zmienione requirements wymagają nowego runtime backendu;
  uploads `root:root 0755` wymaga zatwierdzonego rozwiązania zapisu non-root,
  bez automatycznego rekurencyjnego chown oryginałów.
- Następny krok: uzgodnić kompatybilny, przypięty digestem runtime/entrypoint
  Stirling i jawne writable paths; ponowić staging PDF/PNG/JPEG i test uprawnień
  na kopii uploads. Nie wyłączać read-only ani nie wracać do roota jako obejścia.
- Nie wykonano deployu, migracji produkcyjnej ani zmiany aktywnego release'u.
  Backup/restore i przygotowanie rollbacku pozostają wymagane przed przyszłym deployem.

---

## 2026-10-23 — Implementacja pakietu 1 (bez wdrożenia)

- Gałąź `fix/document-safety-package-1`, bazowa rewizja `7cde5ac`, istniejący
  izolowany worktree. Zgoda na wykonanie inline, bez deployu i zmian produkcyjnych.
- Zaimplementowano parser subprocess/rlimits, body/quota/disk admission,
  bounded OCR, savepoint zachowujący lock przy błędzie i trwałe metadata retry,
  UI oraz kandydacki profil Compose.
- Retry 3 kontrolowanych wyników; crash recovery bez trwałego licznika uruchomień
  pozostaje jak poprzednio. Kompresję odpowiedzi OCR odrzucamy przed dekodowaniem
  dla ochrony pamięci; wymaga sprawdzenia identity w staging.
- Autogenerate wykazało niepowiązany drift indeksów schedulera; usunięto go z
  nowej migracji. Migracja obejmuje wyłącznie dokumenty.
- Utworzono tymczasowy kontener `finanse-document-safety-testdb`, loopback 5432,
  tmpfs, z bazami testowymi; nie używano istniejącej produkcyjnej/testowej instancji.
- Zależności Python wykorzystane bez zmian z istniejącego venv; przeglądarka
  Playwright pobrana do ignorowanego workspace planu, bez instalacji pakietów systemowych.
- Kontrole: backend pełny przebieg 617 PASS (przed ostatnim rozszerzeniem schematu
  odpowiedzi, sprawdzonym dodatkową regresją), frontend 194 PASS, Playwright 18 PASS.
  Pierwszy lokalny E2E nie wystartował z powodu brakującej przeglądarki; po lokalnym
  pobraniu przeszedł. Pierwszy pełny pytest wymagał jawnego TEST_DATABASE_URL dla
  istniejącego testu migracji sesji; poprawiony przebieg bez błędów.
- Końcowy gate: backend 617 PASS, osobno 4 testy proxy/container PASS;
  frontend 194 PASS, Playwright 18 PASS; Ruff/mypy/ESLint/tsc/build/diff check PASS.
- Niezależny review zakończony: brak blockerów według reviewera; P2 — limit
  Nginx nie obejmuje uploadu z końcowym `/` (potwierdzono w konfiguracji).
  Po zgodzie użytkownika dodano regresję obu ścieżek: przed poprawką wariant
  z `/` zwracał 413 dla 2 MiB. Dopasowanie Nginx ograniczono do obu dokładnych
  wariantów; ponowny gate: 617 backend i 5 proxy/container PASS, Ruff/mypy PASS,
  194 frontend PASS, ESLint/tsc/diff check PASS. Follow-up review bez uwag.
  Lokalny zakres Task 5 zakończony; P3 traversal PDF pozostawiono w backlogu,
  a realny staging profilu pozostaje bramką przed wdrożeniem.
  P3 — reviewer wskazał pełne flatten drzewa stron przez pypdf przed limitem;
  limity procesu pozostają zabezpieczeniem. Staging rzeczywistego Compose/Stirling
  nadal wymagany; test syntetyczny nie potwierdza bezpieczeństwa odziedziczonych mountów.
- Bez pusha, merge, zmiany /opt/finanse,
  poświadczeń, webapp i działających kontenerów aplikacji.

---

## 2026-10-22 — Plan pakietu bezpieczeństwa dokumentów

- Użytkownik zaakceptował rozpoczęcie pakietu 1 po audycie.
- Przygotowano `docs/superpowers/plans/2026-10-22-document-safety-package-1.md`:
  proces walidacji z limitami, upload/body/storage admission, bounded OCR,
  trwały harmonogram retry, komunikaty UI i profil hardeningu do staging.
- Parametry limitów i liczby prób są propozycją wymagającą potwierdzenia;
  migrację retry można przygotować/testować izolowanie, nie wykonywać na produkcji.
- Nie zmieniono kodu aplikacji ani infrastruktury. Nie wykonano deployu,
  migracji, commitu ani pusha. Następny krok: zatwierdzenie planu i wykonanie TDD.

---

## 2026-10-22 — Audyt przekrojowy przed dalszym rozwojem

### Zakres i wynik
- Audyt kodu `7cde5ac`, cztery niezależne przeglądy obszarów, ponowna weryfikacja
  kluczowych ścieżek i osobna kontrola trafności końcowego raportu.
- Raport: `docs/audits/2026-10-22-audit.md`; 14 ustaleń funkcjonalnych/kontrolnych
  i 5 grup ryzyk. Priorytet: zasoby parserów, limit uploadu, retry OCR;
  następnie kontrakty finansów/UI i egzekwowanie polityk AI.
- Małe próby lokalne potwierdziły brak granic BIGINT/rozmiaru wiadomości AI,
  odrzucanie statusu blocked i niedopasowanie wzorca polityki create_transaction.

### Dowody operacyjne
- CI 39840942742 dla `7cde5ac`: 582 backend bez skipów, 189 Vitest,
  18 Playwright; lint/typecheck/build PASS. Nie powtarzano pełnego zestawu lokalnie.
- Produkcja: backend/worker `827c263`, frontend `b0912f8`; zmiany kodu nie są
  jeszcze wdrożone. GET strony/health 200; nie jest to pełny test gotowości.
- Timery active, ostatni backup success 22.10; świeżego restore drill nie udało
  się potwierdzić dostępnym journalem. Szczegóły i ograniczenia w raporcie.

### Bezpieczeństwo i następny krok
- Tylko dokumentacja i odczyty/proby bez mutacji; bez deployu, migracji,
  dostępu do webapp, poświadczeń czy danych produkcyjnych użytkownika.
- Raport i backlog lokalne, bez commitu/pusha w tej sesji audytu.
- Użytkownik wybiera zakres implementacji; nie naprawiać automatycznie,
  nie kasować oryginałów przy projektowaniu GC bez zatwierdzonej retencji.

---

## 2026-10-22 — Zabezpieczenie ingestii dokumentów

### Cel sesji
Zamknąć ustalenia przeglądu kodu dotyczące zaufania do MIME i integralności
plików przed wysłaniem ich do Stirling OCR.

### Co zrobiono
- Serwis weryfikuje pełny dokument przed zapisem: `pypdf` parsuje PDF, Pillow
  weryfikuje i dekoduje PNG/JPEG; błędne pliki lub MIME mismatch są odrzucane
  przed utrwaleniem danych i enqueue.
- Worker odczytuje dokument raz, porównuje jego SHA-256 z rekordem PostgreSQL,
  a następnie przekazuje do OCR te same zweryfikowane bajty. Przy mismatch OCR
  się nie uruchamia, a dokument otrzymuje status `error`.
- Dodano testy prawidłowych/uszkodzonych i uciętych formatów, mismatch MIME,
  integralności, braku wywołań OCR przy mismatch oraz przekazania zweryfikowanych
  bajtów. Poprawiono także dwa EOF whitespace i opis aktywnego workflow CI.

### Weryfikacja
- Focused: `25 passed, 12 skipped`; backend pytest: `400 passed, 182 skipped`.
- Ruff, mypy i `git diff --check` PASS. Pominięte testy wymagające DB pozostają
  objęte zakończonym sukcesem workflow GitHub Actions z izolowanym PostgreSQL.
- Nie wykonano migracji, deployu ani zmian poświadczeń.

### Ograniczenia
- Parsery i kontrole końcowych markerów odrzucają znane przypadki ucięć, ale nie
  zastępują sandboxingu Stirling ani pełnej kontroli bezpieczeństwa PDF.

### Następny krok
Niezależny review poprawki, potem push i weryfikacja nowego CI.

---

## 2026-10-22 — Synchronizacja repozytoriów

### Cel sesji
Ujednolicić kod VPS i GitHuba, włączając komplet zmian z gałęzi
`genspark_ai_developer`, bez publikowania danych operacyjnych.

### Co zrobiono
- Potwierdzono, że `origin/main` jest przodkiem `origin/genspark_ai_developer`;
  gałąź agenta wnosi 14 commitów, kończąc na `a115afc`.
- W odizolowanym worktree utworzono fast-forward merge od najnowszego `main`.
- Nieśledzone `webapp/` na VPS zawiera runtime/release artifacts, backupy i
  materiały poufne; pozostawiono ten katalog poza zmianami Git.

### Weryfikacja
- Backend pytest: `381 passed, 182 skipped` (pominięto integracyjne wymagające
  bazy; działał już testowy kontener PostgreSQL współdzielony na VPS).
- Frontend: `189 passed`; ESLint, TypeScript i Vite production build PASS.
- Backend Ruff/mypy i `git diff --check` PASS.
- Nie wykonano migracji ani deployu produkcyjnego.

### Następny krok
Synchronizacja zakończona: `origin/main` i checkout `/opt/finanse` wskazywały
na ten sam commit `9cb6101`; `webapp/` pozostał nietknięty.

---

## 2026-08-20 — Sesja 35: Automatyczny backup i restore drill

### Cel sesji
Wdrożyć i udowodnić automatyczne backupy oraz miesięczny izolowany restore drill
na VPS.

### Co zrobiono
- Zainstalowano oba timery systemd i rootowy wrapper
  `/usr/local/lib/finanse/run-restore-drill.sh`. Installer utrzymuje wymagany
  przez sandbox pusty parent `/docker/finanse/data/restore-drill` jako
  `root:root` `0700`.
- Wrapper tworzy guarded `finanse_restore` przed `pg_restore`; ownership-aware
  cleanup usuwa bazę i output także po błędzie, zachowując tylko pusty parent.
- Ręczny backup utworzył snapshot `015211bb` o
  `2026-08-20T14:37:50.478731048+02:00`. Rzeczywisty restore drill przeszedł
  checksumy, migracje i invariant ledgeru; po nim baza nie istnieje, a parent
  pozostał pusty.

### Weryfikacja
- `make test`: backend `198 passed, 125 skipped`; frontend `129 passed`.
  `make lint`, `make typecheck` i `git diff --check` przeszły.
- `finanse-backup.timer` i `finanse-restore-verify.timer` są enabled; kolejne
  uruchomienia to odpowiednio 02:30 dziennie i 04:30 w pierwszą niedzielę,
  `Europe/Warsaw`.
- Backup i restore service zakończyły się `status=0/SUCCESS`. Statusy i journal
  nie zawierały sekretów. Wdrożenie timerów nie spowodowało downtime aplikacji
  webowej.
- Finalny lifecycle: `RESTORE_SNAPSHOT_ID` jest jedynym selektorem snapshotu;
  legacy `snapshot=` fail-closed kończy się przed runnerem/Restic. Wspólny lock
  obejmuje usługi oraz ręczne targety Makefile. Po błędzie service retry po
  15 minutach, maksymalnie 3 starty w 3 godziny.
- Finalny deployment proof: `make test` dał backend `201 passed, 125 skipped`
  i frontend `129 passed`; lint, typecheck i `git diff --check` przeszły.
  `snapshot=deadbeef` został odrzucony kodem 2 z celowo niepoprawnym `PATH`,
  zanim uruchomił się runner lub Restic. Backup utworzył `11fd2129` o
  `2026-08-20T21:30:56.257585672+02:00`; restore service zwrócił
  `status=0/SUCCESS`. Po cleanupie parent jest pusty `root:root` `0700`,
  `finanse_restore` nie istnieje, a status i journal nie zawierały sekretów.
- Cache fix: cache Restic działa pod `/docker/finanse/data/restic-cache`
  (`root:root`, `0700`) przez unit i Make, bez osłabiania `ProtectHome`.
  Produkcyjny restore drill pozostaje wyłącznie operacją
  `finanse-restore-verify.service`; Make jest wewnętrzną zależnością wrappera.
- Cache runtime proof: świeże `make test` dało backend `201 passed, 125
  skipped` i frontend `129 passed`; lint, typecheck i `git diff --check`
  przeszły. Installer potwierdził cache `root:root` `0700`; backup utworzył
  `a6e89e9d` o `2026-08-20T22:22:38.447541219+02:00`, a realny drill zwrócił
  `status=0/SUCCESS`. Bieżące okno journala ma 0 wpisów `unable to open cache`.
  Parent restore jest pusty `root:root` `0700`, `finanse_restore` nie istnieje,
  a status i journal nie zawierały sekretów.

---

## 2026-08-20 — Sesja 34: Deploy security baseline

### Cel sesji
Skonfigurować Contabo S3, wykonać rzeczywisty backup/restore drill i wdrożyć
security baseline wraz z izolacją ingress.

### Co zrobiono
- Utworzono szyfrowane repozytorium Restic Contabo S3. Snapshot `922d1aba`
  został odtworzony do izolowanej bazy `finanse_restore`; checksumy,
  migracja i kontrola ledgeru przeszły. Snapshot po deployu: `63145774`.
  Tymczasowa baza i kopia uploadów zostały po drillu usunięte.
- Zastosowano migrację `c9d8e7f6a5b4`; stare cookie JWT są celowo
  unieważnione i wymagają ponownego logowania.
- Wdrożono dedykowaną sieć `finanse_ingress` (`172.24.0.0/24`) między npmplus
  (`172.24.0.2`) i frontendem. Backend jest tylko na `finanse_internal`.
- Dodano PostgreSQL loopback `127.0.0.1:55431` wyłącznie dla hostowego restore
  drillu; worker dostał komplet ustawień wymaganych przez fail-fast config.

### Weryfikacja
- Backend `192 passed, 125 skipped`; integracyjne `125 passed`; frontend
  `129 passed`; lint/typecheck/build PASS.
- Wszystkie usługi działają, rewizja bazy to `c9d8e7f6a5b4 (head)`; health i
  frontend zwracają 200. Rejestracja zwraca 404, login z Origin 401 dla
  błędnego hasła, a bez Origin 403.

### Otwarte działania
- Właściciel potwierdził rotację zewnętrznych kluczy LLM i Contabo S3 po
  stronie providerów; nowych wartości nie wklejono do rozmowy.

---

## 2026-08-20 -- Sesja 33: Isolacja ingress dla finanse

### Co zrobiono
- Utworzono pustą sieć `finanse_ingress` (`172.24.0.0/24`) po kontroli kolizji.
- Przygotowano oba Compose: npmplus dostaje `172.24.0.2`, frontend ingress+internal,
  backend tylko internal. Nie dołączono ani nie odtworzono kontenerów.
- Nginx ufa tylko statycznemu adresowi npmplus; repo zawiera kontrakt topology i
  testy niezależne od zewnętrznych ścieżek Compose.

### Weryfikacja
- Focused security `11 passed, 6 skipped`; frontend build, `nginx -t`, oba Compose
  config i `docker network inspect finanse_ingress` PASS. Runtime pozostaje bez zmian.

---

## 2026-08-20 -- Sesja 32: Task 5 forwarded-IP re-review fix

### Cel sesji
Usunąć możliwość wyboru lewego elementu łańcucha `X-Forwarded-For` przez backend.

### Co zrobiono
- Nginx frontendu ufa wyłącznie subnetowi npmplus `172.22.0.0/16`, rekurencyjnie
  normalizuje adres klienta i przekazuje backendowi tylko `$remote_addr` jako
  `X-Forwarded-For` oraz `X-Real-IP`.
- Backend przyjmuje od zaufanego frontendu wyłącznie pojedynczy literal IP bez
  przecinka ani whitespace; każdy łańcuch lub błędna wartość wraca do peera.
- Statyczny test zabezpiecza kolejność/opcje realip i nagłówki proxy; test backendu
  obejmuje pojedynczy adres i odrzucony łańcuch.

### Weryfikacja
- TDD RED: 2 testy ujawniły akceptację łańcucha i brak konfiguracji realip;
  focused rate tests PASS. Frontend build i obraz Docker PASS; `nginx -t` PASS z
  mapowaniem Compose-only upstream `backend`. Backend Ruff/mypy i Compose config PASS.
- Nie wykonano deployu ani uruchomienia produkcyjnych usług.

### Następna sesja
Deploy pozostaje osobno autoryzowaną operacją.

---

## 2026-08-20 -- Sesja 31: Security Baseline Task 5 review fixes

### Cel sesji
Usunąć trzy ustalenia przeglądu Task 5: zaufanie do adresu klienta za npmplus,
duplikację limiterów w routerach oraz braki pokrycia tras/audytu.

### Co zrobiono
- `get_client_ip` rozwiązuje wyłącznie skonfigurowane hosty proxy (`frontend`),
  honoruje pierwszy poprawny adres `X-Forwarded-For` tylko dla zaufanego peera i
  odrzuca błędne łańcuchy do adresu peera.
- Limity loginu, Advisora i uploadu są zależnościami FastAPI z jednym flow 429/503
  oraz zredagowanym audytem; testy obejmują rzeczywiste trasy Advisora/uploadu i
  odrzuconą sesję.
- Backend usunięto z sieci `proxy`; frontend ma `proxy` i `internal` także po
  połączeniu override produkcyjnego. Nie zmieniono nginx, ponieważ używa już
  `$proxy_add_x_forwarded_for`.

### Weryfikacja
- TDD RED: brak resolvera zaufanego proxy i `limit_login`; GREEN: focused security
  `16 passed`.
- Backend unit: `187 passed, 125 skipped`; integration: `125 passed, 187 deselected`.
  Ruff i mypy PASS; merged Compose config PASS bez wypisywania sekretów.
- Nie wykonano deployu, migracji ani operacji na produkcji; kontener testowy usunięty.

### Następna sesja
Wdrożenie tej zmiany pozostaje osobno autoryzowaną operacją.

---

## 2026-08-19 -- Sesja 30: Security Baseline Task 1

### Cel sesji
Zrealizować wyłącznie pierwszy zatwierdzony krok Security Baseline: wersjonowane
backupy Restic oraz izolowaną weryfikację odtworzenia, bez credentiali i bez
operacji na produkcji.

### Co zrobiono
- Dodano `ops/backup.sh`: prywatny katalog tymczasowy, custom `pg_dump`,
  deterministyczne archiwum uploads, manifest SHA-256/Git/Alembic oraz Restic
  backup i retencję 7 dziennych, 4 tygodniowych i 6 miesięcznych snapshotów.
- Dodano `ops/restore-verify.sh`: bezwzględny guard hosta loopback i nazwy bazy
  `_restore`/`_test`, checksumy przed zmianą uploads/DB, migracje i SQL fail-closed
  dla invariantów postings.
- Dodano dokumentację operacyjną, testy TDD statycznie sprawdzające guardy,
  komendy, manifest, retencję i tryb wykonywalny oraz targety w
  `/docker/finanse/Makefile`.

### Weryfikacja
- RED: `6 failed` z powodu brakujących skryptów i poprzednich targetów Makefile.
- GREEN: focused `test_backup_scripts.py` -- `6 passed`; pełny backend:
  `132 passed, 109 skipped, 3 warnings`; Ruff i `bash -n` PASS.
- ShellCheck nie jest zainstalowany. Nie skonfigurowano Restic, nie wykonano
  backupu, restore, migracji ani deployu produkcyjnego.

### Decyzje techniczne
1. Snapshot zawiera manifest w tym samym prywatnym katalogu, a katalog jest
   usuwany trapem po każdej ścieżce wyjścia.
2. Weryfikacja odmawia ekstrakcji do istniejącego `RESTORE_DIR/uploads`, aby nie
   nadpisywać istniejących dokumentów.

### Następna sesja
Kolejne zatwierdzone zadanie Security Baseline, jeśli zostanie zlecone osobno.

---

## 2026-08-19 — Sesja 29: Deploy CRUD kont i kategorii

### Cel sesji
Domknąć wdrożenie CRUD kont i kategorii: quality gate, migrację produkcyjną,
deploy oraz smoke test.

### Co zrobiono
- Uruchomiono pełny quality gate: backend `126 passed, 109 skipped`, frontend
  `106 passed`; integracyjne `109 passed`; Ruff, mypy, ESLint, TypeScript i
  Vite build przeszły.
- Zastosowano na produkcji migrację `1dbfe88dfb1b` (`categories.is_active`) i
  przebudowano/usługowo uruchomiono backend, frontend oraz worker.
- Dodano override produkcyjny workera w `/docker/finanse/compose.prod.yaml`:
  `arq app.worker.WorkerSettings` bez niepoprawnego `--watch`; worker wrócił do
  stanu `Up` i przetwarza funkcję `process_document`.
- Smoke test `https://finanse.birek.online/api/health` zwrócił HTTP 200.
- Konfiguracja projektu OpenCode korzysta z modeli OpenAI: główny
  `gpt-5.6-sol`, implementacja/ogólne zadania `gpt-5.6-terra`, lekkie role
  `gpt-5.6-luna`.

### Decyzje techniczne
1. Lista zarządzania na `/finances/accounts` celowo pozostaje pełna, a filtry
   nieaktywnych encji działają wyłącznie w operacyjnych widokach i formularzach.
2. Worker produkcyjny nie używa trybu watch; jest przeznaczony do stabilnego
   przetwarzania zadań ARQ.

### Następna sesja
Brak otwartych działań dla CRUD kont i kategorii.

---

## 2026-08-19 — Sesja 28: Operacyjne listy bez nieaktywnych encji

### Cel sesji
Zrealizować autoryzowane Zadanie 4: ukryć nieaktywne konta i kategorie z
operacyjnych list/selectów bez zmiany strony zarządzania ani API.

### Co zrobiono
- `TransactionForm` filtruje aktywne konta i kategorie, zachowując filtr typu
  oraz obsługę kont walutowych dla przewalutowania.
- `ScheduledItemForm` pokazuje aktywne konta budżetowe PLN i aktywne kategorie.
- `FinanceBudgets` pokazuje aktywne kategorie wydatkowe.
- `Finances` oraz `AccountTransactions` ukrywają nieaktywne konta. Nawigacja
  zachowuje konto, jeśli było już wybrane przed dezaktywacją.
- Dodano testy regresyjne dla TransactionForm, ScheduledItemForm,
  FinanceBudgets, Finances i AccountTransactions. Warunek `!== false` zachowuje
  kompatybilność z mockami bez pola `is_active`.

### Weryfikacja
- TDD: testy RED wykazały 5 braków, następnie focused GREEN: `5 plików,
  29 testów`.
- Pełny frontend: `npm run test` — `16 plików, 106 passed`.
- `npm run lint`, `npm run typecheck`, `npm run build` — PASS.

### Decyzje techniczne
1. Filtrowanie pozostaje lokalne w komponentach korzystających z list; API i
   `FinanceAccounts` nadal zwracają/pokazują pełny zbiór encji.

### Następna sesja
Brak dalszych działań dla tego zakresu.

---

## 2026-08-17 — Sesja 27: Refresh konta po aktualizacji

### Cel sesji
Naprawić latentny MissingGreenlet w `PATCH /accounts/{id}` — ten sam problem,
który Sesja 26 naprawiła dla kategorii.

### Co zrobiono
- `update_account_endpoint` dostaje `db.refresh(account)` przed returnem;
  wcześniej walidacja `AccountResponse.updated_at` po flush UPDATE kończyła się
  `ResponseValidationError` (MissingGreenlet).
- TDD: nowy test API PATCH konta (`is_active=False`, asercja `updated_at`)
  najpierw odtworzył błąd, potem przeszedł.

### Weryfikacja
- Focused `test_entities_crud.py`: `18 passed`; pełny `test_finance`: `156 passed`;
  ruff/mypy `app/finance` PASS. Kontener testowy usunięty.

### Następna sesja
Frontend dezaktywacji kategorii, `closed_at` przy dezaktywacji konta.

---

## 2026-08-17 — Sesja 26: Usuwanie i dezaktywacja kont i kategorii

### Cel sesji
Domknąć cykl życia encji finansowych: usuwanie kont i kategorii (gdy brak
powiązań) oraz dezaktywacja kategorii, z ochroną rekordów księgi.

### Co zrobiono
- Backend: kolumna `categories.is_active` + migracja `1dbfe88dfb1b`.
- Serwis: `delete_account`/`delete_category` zwracają False dla brakującej/cudzej
  encji i ValueError przy powiązanych rekordach (postingi, pozycje schedulera,
  budżety, kategorie-dzieci); nieaktywne konta/kategorie są odrzucane w
  `_validate_transaction_postings`, `_validate_scheduled_item_links` i
  `_require_expense_category`.
- API: `DELETE /accounts/{id}`, `DELETE /categories/{id}` (204/404/409),
  `is_active` w `PATCH /categories/{id}`; dodano `db.refresh` w PATCH kategorii
  (naprawa MissingGreenlet na `updated_at` po flush UPDATE).

### Weryfikacja
- TDD: RED (ImportError brakującego `delete_account`) → GREEN po implementacji.
- Focused `test_entities_crud.py`: `17 passed`; pełny `test_finance`: `155 passed`;
  backend unit: `126 passed, 108 skipped`; ruff/mypy PASS.
- Migracja zweryfikowana upgrade/downgrade/upgrade na izolowanej bazie
  `127.0.0.1:55432`; kontener testowy usunięty.

### Decyzje techniczne
1. Usuwanie encji z historią jest blokowane (409 z sugestią dezaktywacji),
   zgodnie z niezmiennością księgi — kasowanie czystych encji pozostaje jawne.
2. `PATCH /accounts/{id}` ma ten sam latentny problem `updated_at`
   (MissingGreenlet) co naprawiona kategoria — poza zakresem zadania.

### Następna sesja
Ewentualna naprawa PATCH kont/transakcji (`db.refresh`), frontend dezaktywacji
kategorii, `closed_at` przy dezaktywacji konta.

---

## 2026-08-15 — Sesja 25: Budżety w prognozie płynności

### Cel sesji
Pokazać w prognozie płynności podsumowanie budżetów bieżącego miesiąca i
ostrzegać, gdy pozostałe budżety przekraczają prognozowane saldo przed wypłatą.

### Co zrobiono
- Backend: `CashflowBudgetSummary` + pole `budgets` w `CashflowForecastResponse`,
  liczone z `get_budget_status` (sumy limitów, wydatków, pozostałości; zera przy
  braku budżetów).
- Frontend: typ i karta „Budżety w tym miesiącu" w widoku cashflow (pasek
  postępu, limit/wydano/pozostało) oraz ostrzeżenie, gdy `remaining_pln >
  projected_balance_before_next_payday_pln`. Guard `budgetProgress` dla
  zerowego limitu.

### Weryfikacja
- TDD per zadanie z dwustopniowym przeglądem (spec + jakość).
- Backend: Ruff/mypy PASS; `133 unit`; integracyjne `91 passed`.
- Frontend: `80 passed` (15 plików), ESLint, TypeScript, Vite build PASS.

### Decyzje techniczne
1. Porównanie pozostałych budżetów z prognozowanym saldem to miękki sygnał
   dyscypliny (budżety to limity, nie zobowiązania), nie twardy zakaz.
2. Integracja ograniczona do podsumowania; oś dzienna prognozy pozostaje
   niezależna od limitów.

### Następna sesja
Opcjonalnie: przewalutowania krzyżowe EUR↔USD, nadpisania budżetów per miesiąc,
integracja limitów z osią prognozy.

---
## 2026-08-15 — Sesja 24: Przewalutowanie PLN↔EUR/USD

### Cel sesji
Dodać ręczne przewalutowanie między kontem PLN a EUR/USD z kursem NBP lub ręcznym.

### Co zrobiono
- Backend: `create_exchange_transaction` — waliduje konta (własność, aktywne,
  różne, różne waluty, dokładnie jedno PLN), rozwiązuje kurs (ręczny `manual`
  albo `NbpRateProvider`), liczy `base` i `to_amount` (obie nogi z tym samym
  `base_amount_pln`), buduje postings debit/credit i deleguje do `create_transaction`.
- Backend: `POST /finance/transactions/exchange` (201; ValueError→422), zarejestrowany
  przed trasą dynamiczną.
- Frontend: hook `useCreateExchange` i czwarty typ „Przewalutowanie" w
  `TransactionForm` (dwa konta wszystkich walut, opcjonalny kurs ręczny, brak
  kategorii, walidacja pary).

### Weryfikacja
- TDD per zadanie z dwustopniowym przeglądem (spec + jakość).
- Backend: Ruff/mypy PASS; `130 unit`; integracyjne `89 passed`.
- Frontend: `76 passed` (14 plików), ESLint, TypeScript, Vite build PASS.

### Decyzje techniczne
1. Przewalutowania krzyżowe EUR↔USD poza zakresem (wymagają kursu krzyżowego).
2. Kurs jest zawsze PLN-per-jednostkę waluty obcej; noga PLN ma `fx_rate=1.0`.
3. Prowizja nie jest częścią exchange — to osobny koszt.

### Następna sesja
Integracja budżetów z prognozą płynności; przewalutowania krzyżowe.

---
## 2026-08-15 — Sesja 23: Edycja i usuwanie transakcji

### Cel sesji
Dodać korektę i usuwanie transakcji z listy, domykając cykl życia transakcji.

### Co zrobiono
- Backend: `delete_transaction` (właściciel, `db.delete` + flush; postingi usuwane
  kaskadowo przez relację + `ondelete=CASCADE`) oraz `DELETE /transactions/{id}`
  (204, brak/cudza → 404).
- Frontend: hooki `useUpdateTransaction` (PATCH opis/data) i `useDeleteTransaction`
  (DELETE) z centralną invalidacją `invalidateFinanceLedger`.
- Frontend: w liście transakcji per wiersz akcje „Edytuj"/„Usuń"; edycja inline
  opisu i daty (jeden wiersz naraz, Zapisz/Anuluj, pending-disable, błąd inline);
  usunięcie z `window.confirm`.

### Weryfikacja
- TDD per zadanie z dwustopniowym przeglądem (spec + jakość).
- Backend: Ruff/mypy PASS; `128 passed, 79 skipped`; integracyjne `81 passed`.
- Frontend: `70 passed` (14 plików), ESLint, TypeScript, Vite build PASS.

### Decyzje techniczne
1. Edycja obejmuje opis i datę; zmiana kwoty/konta/kategorii to usuń + dodaj
   ponownie (postingi nie są edytowane w miejscu).
2. Edycja opisu transakcji z Actual usuwa znacznik `[actual:{uuid}]` idempotentności
   re-importu — udokumentowane, nie blokowane.

### Następna sesja
Przewalutowanie (exchange) z kursem NBP i obsługa EUR/USD.

---
## 2026-08-15 — Sesja 22: Ręczne księgowanie transakcji

### Cel sesji
Dodać ręczne wprowadzanie transakcji (przychód, wydatek, transfer) na stronie
Transakcje, bez nowych modeli ani migracji.

### Co zrobiono
- Frontend: helper `buildTransactionPostings` kodujący konwencję
  `balance = credit − debit` (przychód konto credit/kategoria debit; wydatek
  odwrotnie; transfer źródło debit/cel credit), pokryty testami sumy zero.
- Frontend: komponent `TransactionForm` z selektorem typu, kontami (aktywne PLN),
  kategoriami filtrowanymi po typie, kwotą (parsePlnToGrosze), datą (domyślnie
  dziś lokalnie) i opisem; walidacja, błąd inline, reset po sukcesie.
- Frontend: montaż formularza na `/finances/transactions` nad listą transakcji.
- Naprawiono kontrakt daty: `useCreateTransaction` wysyłał `date`, backend
  oczekiwał `transaction_date` (Pydantic cicho odrzucał datę) — teraz data
  wybrana przez użytkownika jest zapisywana.

### Weryfikacja
- TDD per zadanie z dwustopniowym przeglądem (spec + jakość) i re-review.
- Frontend: `63 passed` (14 plików), ESLint, TypeScript, Vite build PASS.
- Backend bez zmian: Ruff/mypy PASS, `125 passed, 79 skipped`, integracyjne
  `79 passed`.

### Decyzje techniczne
1. Kierunki postingów buduje wyłącznie helper frontendowy, zgodny z konwencją
   księgi; serwis `create_transaction` pozostaje autorytatywny dla invariantu.
2. Zakres PLN-only (jak scheduler) — EUR/USD i przewalutowanie wymagają FX.

### Następna sesja
Edycja/usuwanie transakcji, przewalutowanie (exchange) z kursem NBP, ew. korekta
odwróconego mapowania kierunków w narzędziu Doradcy (`advisor/tools/registry.py`).

---
## 2026-08-15 — Sesja 21: Miesięczne budżety z limitami

### Cel sesji
Dodać kontrolę wydatków przez miesięczne limity na kategorie wydatkowe i
porównanie planu z wykonaniem na stronie `/finances/budgets`.

### Co zrobiono
- Backend: model `CategoryBudget` (user_id, category_id FK RESTRICT, amount_pln
  BIGINT > 0, unikalny (user, category)) + migracja `4340d1460982`.
- Backend: serwis CRUD z walidacją własności i typu `expense`; `get_budget_status`
  liczy wydane (roll-up potomków dla grup, własna kategoria zawsze wliczona) i
  zwraca kategorie z limitem i zerowymi wydatkami.
- Backend: endpointy `GET/POST /budgets`, `PATCH/DELETE /budgets/{id}`,
  `GET /budget-status`; duplikat kategorii → 422 (IntegrityError złapany).
- Frontend: typy/hooki budżetów, helper `budgetProgress`; strona budżetów z
  listą, edycją inline limitu, formularzem dodawania (expense minus zbudżetowane),
  usuwaniem z potwierdzeniem i sekcją „Wydatki bez budżetu".

### Weryfikacja
- TDD per zadanie z dwustopniowym przeglądem (spec + jakość) i re-review.
- Backend: Ruff i mypy PASS; `make test` `125 passed, 79 skipped`;
  `make test-integration` `79 passed, 125 deselected` (migracja zastosowana).
- Frontend: `55 passed` (13 plików), ESLint, TypeScript i Vite build PASS.

### Decyzje techniczne
1. Budżet jest cykliczny miesięcznie (brak kolumny miesiąca) — domyślny limit;
   nadpisania per miesiąc odroczone.
2. Limit dotyczy wyłącznie kategorii `expense`; grupy sumują wydatki potomków
   (rekurencyjnie), a własna kategoria jest zawsze wliczona do scope'u.
3. Znane ograniczenie: drzewo „Wydatki bez budżetu" nie odejmuje kwot
   kategorii-dzieci, gdy zbudżetowane jest tylko dziecko (możliwe podwójne
   pokazanie na granicy grup) — zostawione świadomie.

### Następna sesja
Ręczne księgowanie transakcji (formularz przychodu/wydatku/transferu) jako krok
do uczynienia PA główną księgą; ewentualnie integracja limitów z prognozą
płynności.

---
## 2026-08-15 — Sesja 20: Podstrony finansowe i zarządzanie płynnością

### Cel sesji
Rozdzielić finanse na użyteczne podstrony oraz dodać kontrolowany przez
użytkownika interfejs cyklu wynagrodzenia: ustawienia, harmonogram, prognozę i
zatwierdzanie sugestii bez automatycznego księgowania.

### Co zrobiono
- Backend: raporty `summary` i `category-summary` przyjmują `month`/`year`;
  helper `_month_bounds` daje zamknięty wybrany okres z zachowaniem bieżących
  sald kont.
- Backend: `delete_scheduled_item` (właściciel + flush) oraz
  `confirm_scheduled_item` z blokadą wiersza, ponownym przeliczeniem prognozy i
  walidacją powiązanego konta/kategorii. Potwierdzenie tworzy wyłącznie przez
  `create_transaction` zbilansowaną transakcję `source="scheduled_confirmation"`;
  odrzuca non-PLN, przyszłe, `overdue_uncertain`, `amount_unknown` i ponowne.
- Frontend: typy/hooki (`FinanceSettings`, mutacje schedulera, potwierdzenie,
  `parsePlnToGrosze`, `canConfirmSuggestion`) oraz centralna invalidacja cache.
- Frontend: trasy `/finances`, `/finances/transactions`, `/finances/cashflow`,
  `/finances/budgets`, `/finances/reports`; współdzielone komponenty
  (`MonthPicker`, `CategorySpendTree`, `AccountTransactions`, `formatPLN`,
  `SummaryCard`); strona cashflow z formularzami, prognozą i dialogiem.

### Weryfikacja
- TDD per zadanie: RED przed implementacją w każdej warstwie; poprawki po
  dwustopniowym przeglądzie (spec + jakość) z re-review.
- Backend: Ruff i mypy PASS; `make test` `123 passed, 61 skipped, 3 warnings`;
  `make test-integration` `61 passed, 123 deselected, 11 warnings`.
- Frontend: `41 passed` (13 plików), ESLint, TypeScript i Vite build PASS.

### Decyzje techniczne
1. Potwierdzenie przyjmuje wyłącznie `due`/`overdue` i nie akceptuje od klienta
   kwoty/konta/kategorii/daty; dane pochodzą z ponownie wyliczonej sugestii.
2. Scheduler obsługuje na razie wyłącznie PLN (kwota zawsze `fixed_amount_pln`);
   konta walutowe wymagają najpierw wsparcia FX w confirm.
3. Wydzielono współdzielone komponenty i helpery finansowe, aby uniknąć
   duplikacji `formatPLN`/kart w pięciu plikach.

### Następna sesja
Limity budżetowe pozostają poza zakresem; ewentualne wsparcie kont walutowych w
schedulerze wymaga rozszerzenia confirm o rzeczywisty kurs FX.

---
## 2026-08-15 — Sesja 19: Poprawki znaku, invalidacji i non-PLN schedulera

### Cel sesji
Wprowadzić trzy poprawki z finalnego przeglądu frontendu: odwrócony znak
transakcji per konto, zakres invalidacji cashflow oraz selektor konta schedulera
dopuszczający niepotwierdzalne konta non-PLN.

### Co zrobiono
- `AccountTransactions` rozpoznaje przychód po `direction === "credit"` (zamiast
  `debit`), zgodnie z konwencją `balance = credit − debit`; wydatek pozostaje
  `debit`. Dodano test regresyjny renderujący transakcje income/expense z
  rzeczywistymi postingami i asercją znaku oraz klasy koloru.
- Zweryfikowano zakres invalidacji cashflow zamiast zgadywać: w TanStack Query
  v5 `invalidateQueries({ queryKey: ["finance","accounts"] })` używa domyślnego
  prefix-match (`exact: false`), więc obejmuje również transakcje per-konto
  (`["finance","accounts", id, "transactions", ...]`). Centralna invalidacja
  `invalidateCashflowMutationQueries` jest kompletna — bez zmiany kodu. Dodano
  test dokumentujący to zachowanie na realnym `QueryClient`.
- `ScheduledItemForm` filtruje konta do `is_budget_account && is_active &&
  currency === "PLN"`, a pole waluty jest zablokowane na „PLN" (hardcoded w
  payload i polu). Dodano test: konto EUR nie pojawia się w selektorze.

### Weryfikacja
- TDD: testy znaku, selektora konta i waluty najpierw failowały (income jako
  „−", EUR w selektorze, pusta waluta), potem przeszły po minimalnej zmianie.
- `npm test`: `13` plików, `41 passed`. `npm run lint`, `npm run typecheck`,
  `npm run build`: PASS.

### Decyzje techniczne
1. Punkt 2 (invalidacja) nie wymagał zmiany kodu — TanStack Query v5 domyślnie
   dopasowuje klucze po prefiksie, więc `["finance","accounts"]` pokrywa
   poddrzewo transakcji per-konto. Dodano test zabezpieczający przed regresją
   przy ewentualnej zmianie wersji biblioteki.
2. Waluta schedulera jest jawnie „PLN" zamiast wartości z konta — zapobiega to
   pozycjom non-PLN, które backend confirm odrzuca.

### Następna sesja
Ewentualne rozszerzenie schedulera o konta walutowe wymaga najpierw wsparcia
non-PLN po stronie confirm w backendzie.

---
## 2026-08-14 — Sesja 18: Kontekstowy sidebar

### Cel sesji
Zastąpić płaską nawigację kontekstowym sidebarem bez zmiany aktualnych tras,
autoryzacji, topbara, treści widoków ani ciemnej palety aplikacji.

### Co zrobiono
- Powstała jedna typowana konfiguracja siedmiu obszarów: `today`,
  `organization`, `finance`, `advisor`, `knowledge`, `automation` i `system`.
  Zachowuje obecne trasy, w tym `/finances`; moduły przyszłe nie mają `to` ani
  route'ów i pokazują „Wkrótce”.
- Dodano desktopowy `IconRail` z natywnymi tooltipami oraz
  `ContextualSidebar` ze stałym nagłówkiem, menu aktualnego obszaru i dolnym
  `UserPanel`. Mobilny drawer używa tego samego menu i zamyka się po nawigacji.
- `Layout` ograniczono do kompozycji nowych komponentów. Obszar aktywny jest
  wyliczany z `location.pathname` przez najdłuższy pasujący prefiks, bez local
  state; nested `/projects/:id` zachowuje kontekst organizacji.

### Weryfikacja
- TDD: test konfiguracji najpierw nie rozwiązał nieistniejącego modułu, test
  komponentów najpierw nie znalazł raila, a następnie oba przeszły po minimalnej
  implementacji.
- `npm run test`: `3` pliki, `12 passed`. Testy React Router zgłaszają wyłącznie
  istniejące ostrzeżenia o przyszłych flagach v7.
- `npm run lint`, `npm run typecheck` i `npm run build`: PASS.
- Playwright smoke test na Vite z zamockowanym `GET /api/auth/me`: desktopowy
  rail, menu Finanse, zablokowany Budżet i tooltip Automatyzacji są widoczne na
  `/finances`.

### Decyzje techniczne
1. Kontekst jest funkcją URL, a nie lokalnego stanu, dzięki czemu direct linki i
   trasy zagnieżdżone nie rozchodzą się z widocznym menu.
2. Ikony pozostają lokalnymi SVG; wydzielono je do pliku eksportującego wyłącznie
   komponenty, zgodnie z regułą Fast Refresh ESLint.

### Następna sesja
Po dodaniu przyszłego modułu trzeba dopisać trasę i element konfiguracji, zamiast
tworzyć osobny model nawigacji.

---
## 2026-08-14 — Sesja 17: Prognoza płynności cyklu wypłaty

### Cel sesji
Zrealizować pierwszy pionowy slice prognozy finansowej: ustawienia cyklu,
miesięczne przychody i wydatki, forecast do kolejnej wypłaty oraz sugestie bez
automatycznego księgowania.

### Co zrobiono
- Dodano migrację `8a6d0c1e2b3f`, modele `FinanceSettings` i
  `ScheduledFinanceItem`, walidację własności konta/kategorii, konta budżetowego
  i zgodności waluty.
- Dodano API ustawień, pozycji harmonogramu i prognozy. Pozycja obsługuje kwotę
  `fixed` w groszach PLN albo `last_actual` z ostatniej zgodnej transakcji.
- Forecast liczy wyłącznie aktywne konta budżetowe, rozpoznaje transakcję
  rzeczywistą po koncie, kategorii, typie, kwocie i oknie dat ±3 dni, pokazuje
  saldo przed następną wypłatą, limit dzienny i najniższe saldo.
- Nieznana pozycja po trzech dniach ma `overdue_uncertain` i jest wykluczona z
  projekcji. Odczyt forecastu nie zapisuje ustawień, transakcji ani postings.
- Strona Finanse ma kartę płynności i listę harmonogramu; nie dodano kontroli
  tworzącej wpis księgi.

### Weryfikacja
- TDD objęło walidację kwoty stałej, konto pozabudżetowe, niepewność po trzech
  dniach, dopasowanie realnej transakcji bez mutacji księgi, `last_actual`,
  granicę 30 dni i API.
- Alembic z `DATABASE_URL` wskazującym izolowaną bazę `finanse_test` na
  `127.0.0.1:55432` zastosował wszystkie migracje do `8a6d0c1e2b3f`.
- Lint i typecheck: PASS. `make test`: backend `123 passed, 47 skipped,
  3 warnings`, frontend `7 passed`. `make test-integration`: `47 passed,
  123 deselected, 11 warnings`. Build Vite: PASS.

### Decyzje techniczne
1. Pierwszy slice używa wyłącznie cyklu miesięcznego i dnia 1-28, aby uniknąć
   niejednoznaczności końca miesiąca.
2. Sugestie są wyliczane dynamicznie z istniejącej księgi; nie powstał model
   oczekującej transakcji i endpoint forecastu nie ma ścieżki zapisu.

### Następna sesja
Opcjonalnie dodać formularze zarządzania ustawieniami i pozycjami oraz osobny,
zatwierdzany przez użytkownika workflow przekształcania sugestii w transakcję.

---
## 2026-08-14 — Sesja 16: Legacy bilanse otwarcia w preflight korekty

### Cel sesji
Odblokować wyłącznie historyczne, syntetyczne bilanse otwarcia w preflight
`--replace-legacy-actual`, bez poszerzania wyjątku na ręczne lub niepewne dane.

### Co zrobiono
- Dodano ścisłe rozpoznanie BO: `source='actual'`, prefiks `[BO] Bilans otwarcia`,
  dokładnie dwie nogi, wspólne niepuste konto, brak kategorii oraz równe wartości
  bazowe po stronach debit/credit.
- Normalne dopasowanie `[actual:<id>]` pozostaje pierwsze; tylko niepasujący
  rekord o powyższym kształcie jest dopuszczany do usunięcia. Każdy lookalike,
  rekord ręczny, niezbilansowany lub skategoryzowany BO nadal jest odrzucony.
- Testy TDD najpierw zakończyły się błędem braku predykatu, następnie objęły
  dozwolony BO i przypadki odrzucone.

### Weryfikacja
- Focused pytest: `6 passed` dla predykatu BO; pełny `test_actual_import.py`:
  `38 passed, 11 skipped`.
- Quality gate: lint i typecheck przeszły; `make test`: backend `122 passed,
  41 skipped`, frontend Vitest `6 passed`; izolowane `make test-integration`:
  `41 passed, 121 deselected`.
- Nie uruchomiono polecenia produkcyjnej korekty ani polecenia
  `--replace-legacy-actual` przeciwko produkcyjnej bazie.

### Następna sesja
Po wdrożeniu kodu decyzja o produkcyjnej korekcie pozostaje osobnym, ręcznie
zatwierdzanym krokiem z wymaganym backupem i raportem uzgodnienia równym zero.

---
## 2026-08-14 — Sesja 15: Kontrolowana korekta legacy Actual

### Cel sesji
Usunąć ostatnie blokady uzgodnienia oraz przygotować korektę legacy Actual bez uruchamiania jej na produkcji.

### Co zrobiono
- Oczekiwane wartości kategorii są liczone bezpośrednio z nóg parsera Actual i zweryfikowanych kursów; raport zawiera też agregaty grup kategorii i fail-closed obejmuje wszystkie trzy poziomy.
- Dodano trwałe `source` dla `Account` i `Category` (`manual` domyślnie, `actual` tylko dla importera) oraz migrację `f2c8d4e6a1b9`.
- Tryb `--replace-legacy-actual` wymaga `--execute --require-reconciled --backup-path`; wykonuje i weryfikuje backup `pg_dump` przed sesją zapisu. W transakcji odrzuca rekord Actual niepasujący do przekazanego blobu i każdy kandydat z referencją ręczną.

### Weryfikacja
- Backend: Ruff, mypy i testy kategorii/importu `47 passed, 11 skipped`.
- Pełny zestaw: backend/frontend `make test` `116 passed, 41 skipped`; integracyjne `41 passed, 116 deselected`; frontend lint/typecheck/build przeszły; `git diff --check` bez błędów.
- Nie wykonano migracji ani polecenia korekty na produkcji.

### Następna sesja
Po deployu migracji i kodu wykonać wyłącznie zatwierdzone polecenie produkcyjne z nową ścieżką backupu, sprawdzić `reconciliation.json`, a w razie niezerowego raportu nie wykonywać żadnego dalszego zapisu.

---

## 2026-08-14 — Sesja 14: Weekendowe kursy NBP i domknięcie Task 7

### Cel sesji
Naprawić blokadę Task 7 powodowaną przez brak kursu NBP Table A w sobotę/niedzielę, bez dostępu do produkcyjnego PA lub API zapisu Actual.

### Co zrobiono
- Potwierdzono zachowanie API NBP: żądanie kursu USD dla 2026-05-30 zwraca HTTP 404, a zakres kończący się 2026-05-30 zwraca kurs z 2026-05-29; identyczny wzorzec dotyczy niedziel.
- Dodano `NbpRate` z kursem, datą efektywną i źródłem; provider cache'uje kompletny quote pod żądaną datą. Fallback działa wyłącznie po 404 w sobotę/niedzielę, pobiera ograniczony zakres siedmiu dni i akceptuje tylko kurs opublikowany przed datą transakcji.
- Importer przenosi quote do postingów. Kursy z fallbacku są zapisane jako `fx_rate_source='nbp_previous_business_day'`; brak poprawnego kursu nadal powoduje `ImportValidationError`.
- Testy TDD objęły sobotę, niedzielę, cache metadanych, brak kursu w fallback range oraz provenance postingu.

### Weryfikacja
- Ruff dla zmienionych plików i mypy dla providera/importera: PASS.
- `pytest tests/test_finance/test_actual_import.py -v`: `33 passed, 10 skipped`.
- Izolowany import DOM blobu do `finanse_test` na `127.0.0.1:55432`: `--execute --require-reconciled` zakończył się kodem 0; 15 kont, 46 kategorii, 800 transakcji i 0 błędów.
- `/tmp/actual_migration/reconciliation.json`: `is_reconciled=true`; `Revolut USD` ma `Actual 290`, `PA 290`, `diff 0`.
- Cztery historyczne wydatki USD są zapisane z `nbp_previous_business_day`: 519 USD przy 3.6395 (2026-05-30), dwa razy 1077 USD przy 3.6697 (2026-06-14) oraz 1077 USD przy 3.7162 (2026-06-21). Zmiany i import nie dotknęły produkcyjnego PA ani Actual.

### Następna sesja
Przekazać wynik testowego uzgodnienia finalnemu kontrolerowi; ewentualna decyzja o produkcji pozostaje poza tym worktree i tą sesją.

---
## 2026-08-14 — Sesja 13: Task 7, próbne uzgodnienie Actual

### Cel sesji
Wykonać pełną weryfikację kodu oraz import DOM blobu Actual do izolowanej bazy z `--execute --require-reconciled`, bez dostępu do produkcyjnych API zapisu Actual i bez zmiany produkcyjnego PA.

### Co zrobiono
- W worktree `actual-reconciliation` przeszły Ruff, ESLint, mypy, TypeScript, backend pytest (`110 passed, 40 skipped, 5 warnings`), frontend Vitest (`6 tests`) oraz Vite production build.
- Uruchomiono `postgres-test` na `127.0.0.1:55432`, zastosowano migracje do `e7a4b2c6d8f0` i utworzono testowego użytkownika `d34b6ca0-61be-453d-9818-81528de99e81` wyłącznie w `finanse_test`.
- Importer DOM blobu uruchomiony z testowym `DATABASE_URL`, `--execute` i `--require-reconciled` zapisał raporty, zwrócił `ReconciliationError` i wykonał rollback przed commitem.

### Wynik uzgodnienia
- `/tmp/actual_migration/reconciliation.json` ma `is_reconciled=false`; `/tmp/actual_migration/reconciliation_report.txt` wskazuje tylko `Revolut USD`: Actual `290`, PA `4040`, `diff -3750`. Pozostałe 14 kont i wszystkie kategorie mają różnicę zero.
- Cztery odrzucone wydatki USD są przyczyną różnicy: `-519` z 2026-05-30 oraz po `-1077` z 2026-06-14, 2026-06-14 i 2026-06-21. Ich suma wynosi `-3750`; importer odrzucił je, ponieważ NBP nie podał kursu USD dla tych dat.
- Niezależne zapytanie SQL po rollbacku zwróciło zero postingów oraz zero transakcji `source='actual'` dla testowego użytkownika.

### Decyzje techniczne
1. Wynik nie kwalifikuje się do żadnej operacji na produkcyjnym PA. Nie użyto produkcyjnego DSN ani Actual write API.
2. Przy odrzuceniu przez `--require-reconciled` raporty uzgodnienia są zapisane przed wyjątkiem; `migration_report.txt` nie jest w tym przebiegu odświeżany i nie jest źródłem wyniku.

### Następna sesja
Ustalić zweryfikowane kursy lub zatwierdzoną obsługę czterech historycznych wydatków USD, ponowić pełny import testowy i przekazać ewentualną komendę produkcyjną wyłącznie finalnemu kontrolerowi po raporcie zerowym.

---
## 2026-08-13 — Sesja 12: Merge i deploy produkcyjny

### Cel sesji
Scalić `quality-advisor` do `main` i wdrożyć zweryfikowaną wersję na produkcję.

### Co zrobiono
- Zacommitowano specyfikację i plan jakości Advisora na `main`.
- Scalono `quality-advisor` do `main` bez konfliktów (`4d7c7c4`).
- Zbudowano i uruchomiono obrazy backendu oraz frontendu przez Docker Compose.
- Nie wykonywano migracji bazy ani zmian schematu.

### Weryfikacja produkcji
- Backend i frontend: kontenery `finanse-backend` oraz `finanse-frontend` działają.
- `GET https://finanse.birek.online/api/health` — HTTP 200, `status=ok`, `environment=production`.
- `HEAD https://finanse.birek.online/` — HTTP 200.
- Logi backendu: aplikacja wystartowała poprawnie; frontend: nginx gotowy do obsługi żądań.

### Znane problemy
- Testy emitują ostrzeżenia zależności/runtime opisane w poprzednich wpisach.

### Następna sesja
Obserwacja produkcji i wybór Iteracji 3 na podstawie realnego użycia.

---
## 2026-08-13 — Sesja 11: Korekta zakresu migracji i wyników testów

### Cel sesji
Usunąć z końcowej korekty niezwiązane porządkowanie migracji oraz odświeżyć dokumentację wyłącznie na podstawie świeżej weryfikacji.

### Co zrobiono
- Przywrócono `backend/migrations/env.py` oraz dwie wersje migracji dokładnie do `f90a4d6`; nie zmieniono schematu.
- Zaktualizowano CHANGELOG, TASKS i JOURNAL o bieżące, zweryfikowane wyniki.

### Weryfikacja
- `/opt/finanse/backend/.venv/bin/pytest -v` (w `backend`) — PASS: `89 passed, 23 skipped, 5 warnings`.
- `make VENV=/opt/finanse/backend/.venv/bin test-integration` — PASS: `23 passed, 89 deselected, 11 warnings`; użyto izolowanego PostgreSQL, a kontener i sieć zostały usunięte przez trap Makefile.
- `git diff --check` — PASS.

### Decyzje techniczne
1. Zmiany w migracjach były wyłącznie porządkowaniem formatowania, importów i typów, więc nie należą do zakresu tej pracy i zostały wycofane bez modyfikacji schematu.
2. Nie wykonano migracji ani deployu produkcyjnego.

### Znane problemy
- Ostrzeżenia testowe i zależności pozostają opisane w najnowszych ograniczeniach CHANGELOG.

### Następna sesja
Brak dalszych działań dla tego zakresu.

---
## 2026-08-13 — Sesja 10: Domknięcie walidacji i historii narzędzi

### Cel sesji
Naprawić końcowe ustalenia przeglądu jakości bez wdrażania ani migracji produkcyjnych.

### Co zrobiono
- Odtwarzanie komunikatów `tool` z `ToolExecution` przy kolejnych turach Doradcy, z zachowaniem wyników, błędów i oczekujących potwierdzeń.
- Walidacja finansowa na granicy serwisu: własność kont i kategorii, dodatnie kwoty, obsługiwane waluty oraz zgodność waluty konta z postingiem.
- Salda `balance_pln` w Finances są oznaczone `PLN`.
- `DB_SCHEMA.md` opisuje rzeczywiste statusy `ToolExecution`.
- Fixture testowej bazy wiąże aplikacyjny session factory z izolowanym silnikiem per test.

### Decyzje techniczne
1. Wyniki narzędzi są rekonstruowane z identyfikatorów assistant tool calls i pasujących `ToolExecution`; dane wewnętrzne bazy nie trafiają do LLM.
2. Walidacja finansowa pozostaje w serwisie domenowym, aby Advisor i wywołania HTTP korzystały z tej samej granicy autoryzacji.

### Znane problemy
- Testy generują 14 istniejących ostrzeżeń zależności/runtime (m.in. `datetime.utcnow`, passlib/argon2 i AsyncMock w testach NBP); nie blokują wyniku.

### Następna sesja
Brak dalszych działań dla tego zakresu.

---
## 2026-08-12 — Sesja 9: Końcowa jakość projektu

### Cel sesji
Zamknąć dokumentację po implementacji poprawek jakościowych Advisora, testów oraz konfiguracji frontendu. Nie zmieniać kodu i nie deklarować deployu produkcyjnego.

### Co zrobiono
- Zweryfikowano 27 commitów `f90a4d6..ab344ad`; wcześniejsza dokumentacja podawała nieaktualną liczbę 17 commitów. Dwa późniejsze corrective docs commits pozostają poza zakresem sesji.
- Potwierdzono atomiczność potwierdzania mutacji Advisora: blokada wiersza chroni przed równoległym wykonaniem, savepoint wycofuje częściowe zapisy executora, a błąd audit logu nie zostawia mutacji.
- Potwierdzono bezpieczną walidację `create_transaction`: jawne `account_name`, dodatnia kwota całkowita, zgodna waluta konta oraz odrzucenie niezweryfikowanego FX.
- Dodano i uruchomiono testy tool-calling loop, błędnych argumentów, nieznanych narzędzi, błędów executorów, limitu iteracji, potwierdzeń Level 2 i rollbacku.
- Zweryfikowano izolowaną bazę PostgreSQL na `127.0.0.1:55432`; fixture ogranicza operacje schematu do lokalnej bazy `finanse_test`, a `make test-integration` usuwa kontener i sieć po zakończeniu.
- Potwierdzono polling Advisora co 2 sekundy tylko dla `pending_confirmation` oraz poprawkę lokalnego harmonogramu uwzględniającą granice dnia i DST.
- Udokumentowano poprawkę `7cc1973`, która przywróciła lokalną semantykę daty transakcji: brak jawnej daty używa bieżącego dnia użytkownika zamiast daty UTC.
- Dodano konfigurację ESLint 8 i usunięto 7 błędów lintowania frontendu.

### Weryfikacja
- `/opt/finanse/backend/.venv/bin/ruff check app/ tests/` — PASS: bez błędów.
- `/opt/finanse/backend/.venv/bin/mypy app/` — PASS: 46 plików źródłowych, bez błędów; narzędzie wypisało 2 noty o niejawnie typowanych funkcjach.
- `/opt/finanse/backend/.venv/bin/pytest -v` — PASS: `87 passed, 16 skipped, 6 warnings`; testy wymagające niedostępnej bazy zostały pominięte.
- `make VENV=/opt/finanse/backend/.venv/bin test-integration` — PASS: `16 passed, 87 deselected, 12 warnings`; kontener i sieć zostały usunięte przez trap Makefile.
- `npm run lint` — PASS.
- `npm run typecheck` — PASS.
- `npm run test` — PASS: 1 plik, 4 testy.
- `npm run build` — PASS: Vite wygenerował production build.

### Decyzje techniczne
1. Dokumentacja rozróżnia świeży wynik `16 passed` od wcześniejszego, wymaganego do zachowania w historii wyniku `15 passed`; dodatkowy test zwiększył aktualny zestaw integracyjny.
2. Niedostępna baza w zwykłym pytest pozostaje ostrzeżeniem środowiskowym, nie powodem do użycia produkcyjnego DSN. Pełny zakres integracyjny uruchomiono wyłącznie na izolowanym PostgreSQL.

### Znane problemy
- Testy emitują ostrzeżenia o domyślnym scope event loop w `pytest-asyncio`, deprecacjach `crypt`/Argon2 i `datetime.utcnow` w zależnościach oraz `RuntimeWarning` w mocku NBP.
- Trzy daty USD bez kursu NBP (`2026-05-30`, `2026-06-14`, `2026-06-21`) nadal wymagają ręcznej korekty.
- Parser split transactions nie został sprawdzony na rzeczywistych danych użytkownika.
- Polling obsługuje oczekujące potwierdzenia; aplikacja nie ma SSE/streamingu dla pozostałych zmian.
- Nie wykonano migracji ani deployu produkcyjnego.

### Następna sesja
1. Osobno uporządkować ostrzeżenia testowe i zależności.
2. Zweryfikować split transactions na reprezentatywnych danych.
3. Zaplanować SSE, jeśli aplikacja będzie wymagać aktualizacji bez pollingu.

---
## 2026-08-12 — Sesja 8: Konfiguracja ESLint frontendu

### Cel sesji
Uzupełnić brakującą konfigurację ESLint i domknąć frontendowy quality gate w worktree `quality-advisor`.

### Co zrobiono
- Potwierdzono ESLint `8.57.1`, `@typescript-eslint` `7.18.0`, `eslint-plugin-react-hooks` `4.6.2` oraz `eslint-plugin-react-refresh` `0.4.x`.
- Dodano `frontend/.eslintrc.cjs` w formacie legacy z parserem TypeScript, regułami React Hooks/Refresh oraz env browser/ES2022.
- Usunięto 7 błędów lintowych ujawnionych przez konfigurację: nieużywane deklaracje/importy oraz dwa niejawne `any`, bez szerokich wyłączeń reguł.
- Nie zmieniono zachowania aplikacji ani nie dodano testów, ponieważ zadanie dotyczyło wyłącznie konfiguracji jakościowej.

### Weryfikacja
- `cd frontend && npm run lint` — PASS.
- `cd frontend && npm run typecheck` — PASS.
- `cd frontend && npm run test` — PASS: 1 plik, 4 testy.
- `cd frontend && npm run build` — PASS: Vite production build.

### Decyzje techniczne
- Wybrano `.eslintrc.cjs`, ponieważ projekt używa ESLint 8 i nie wymaga migracji do flat config.
- Pozostawiono `--report-unused-disable-directives` i `--max-warnings 0` ze skryptu npm; nie dodano globalnych disable.

### Znane problemy
- Backendowy dług Ruff/mypy z poprzedniej sesji został spłacony; pozostały ostrzeżenia testowe i zależności opisane w Sesji 9.

---
## 2026-08-12 — Sesja 7: Task 6 — weryfikacja jakościowa

### Cel sesji
Przejrzeć historię Task 1-5, wykonać pełną dostępną weryfikację i udokumentować rzeczywisty stan bez zmian w kodzie, deployu ani migracji produkcyjnej.

### Co zrobiono
- Przejrzano 17 commitów `origin/main..HEAD` w worktree `quality-advisor` oraz aktualne dokumenty projektu. Liczba była poprawna dla tego wcześniejszego punktu historii; końcowy zakres sesji wyniósł 27 commitów od `f90a4d6` do `ab344ad`.
- Uruchomiono izolowany PostgreSQL z `/docker/finanse/compose.test.yaml` na `127.0.0.1:55432`; testowy kontener został posprzątany przez `make test-integration`.
- Pełny backend pytest: `81 passed, 15 warnings`.
- Backend testy integracyjne: `15 passed, 66 deselected, 12 warnings` w ówczesnym uruchomieniu; późniejszy test zwiększył świeży wynik do 16.
- Frontend Vitest: `1 test file passed, 4 tests passed`; `npm run typecheck` zakończył się kodem 0; `npm run build` zakończył się kodem 0.
- Nie zmieniono kodu, nie uruchomiono migracji ani deployu produkcyjnego.

### Komendy i wyniki
- `make lint` — FAIL, kod 127: brak `backend/.venv/bin/ruff`.
- `make typecheck` — FAIL, kod 127: brak `backend/.venv/bin/mypy`.
- `make test` — FAIL, kod 127: brak `backend/.venv/bin/pytest`.
- `make test-integration` — FAIL, kod 127 bez override `VENV`; baza wystartowała, ale brak lokalnego pytest.
- `TEST_DATABASE_URL=postgresql+asyncpg://<user>@127.0.0.1:55432/finanse_test /opt/finanse/backend/.venv/bin/pytest -v` (w `backend`) — PASS: `81 passed, 15 warnings`. Historyczne polecenie używało hasła osadzonego w URI; wartość została zredagowana z dokumentacji.
- `make VENV=/opt/finanse/backend/.venv/bin test` — PASS: backend `66 passed, 15 skipped`; frontend `4 passed` (uruchomienie równoległe z integracją zatrzymało bazę po zakończeniu integracji).
- `make VENV=/opt/finanse/backend/.venv/bin test-integration` — PASS: `15 passed, 66 deselected`.
- `make VENV=/opt/finanse/backend/.venv/bin lint` — FAIL w ówczesnym uruchomieniu: ruff zgłaszał 20 błędów; późniejsze commity spłaciły ten dług.
- `make VENV=/opt/finanse/backend/.venv/bin typecheck` — FAIL w ówczesnym uruchomieniu: mypy zgłaszał 9 błędów; późniejsze commity spłaciły ten dług.
- `npm run test` (w `frontend`) — PASS: `1 test file passed, 4 tests passed`.
- `npm run lint` (w `frontend`) — FAIL w ówczesnym uruchomieniu: brak konfiguracji ESLint, mimo zainstalowanych zależności; konfigurację dodano w Sesji 8.
- `npm run typecheck` (w `frontend`) — PASS.
- `npm run build` (w `frontend`) — PASS: Vite wygenerował `dist`.

### Decyzje techniczne
1. Nie kopiowano ani nie tworzono `backend/.venv` w worktree; użyto istniejącego venv poza repo wyłącznie do weryfikacji, aby nie modyfikować kodu i zachować reprodukowalność znanego ograniczenia.
2. Nie naprawiano lint/typecheck: nie było jasnej regresji z Task 1-5 blokującej testy, a polecenie sesji wymagało pozostawienia kodu bez zmian.

### Znane problemy
- Ruff: 20 błędów w ówczesnym punkcie historii, później usuniętych.
- Mypy: 9 błędów w ówczesnym punkcie historii, później usuniętych.
- Frontend ESLint: brak pliku konfiguracyjnego w ówczesnym punkcie historii; konfigurację dodano w Sesji 8.
- Pytest: ostrzeżenia dotyczą m.in. scope fixture `pytest-asyncio`, `passlib`/`argon2`, `python-jose`, a także nieoczekiwanego `RuntimeWarning` w teście NBP.

### Następna sesja
1. Uzupełnić konfigurację ESLint i zależności/typy wymagane przez mypy.
2. Usunąć 20 błędów ruff po osobnym przeglądzie semantycznym.
3. Uporządkować ostrzeżenia testowe, zwłaszcza konfigurację event loop i mock NBP.

---
## 2026-08-12 — Sesja 6: Odświeżanie statusów narzędzi Doradcy

### Cel sesji
Zrealizować Task 5: odświeżać statusy narzędzi oczekujących na potwierdzenie bez SSE.

### Co zrobiono
- Dodano polling wiadomości aktywnej rozmowy co 2 sekundy wyłącznie dla `pending_confirmation`.
- Zatrzymano polling dla statusów rozstrzygniętych i braku aktywnej rozmowy; odświeżanie w tle jest wyłączone.
- Confirm/deny mają typowane wyniki i unieważniają tylko aktywną rozmowę oraz listę rozmów.
- Banner przekazuje `conversationId`, blokuje oba przyciski podczas mutacji i pokazuje zwięzły błąd bez usuwania bannera.
- Dodano testy helpera `hasPendingConfirmation` i decyzji o interwale.

### Decyzje techniczne
1. Użyto `refetchInterval` callbacku TanStack Query v5 oraz `refetchIntervalInBackground: false`; opcja v5 nie nazywa się `refetchInBackground`.

### Znane problemy
- `npm run lint` nie uruchamia się, ponieważ frontend nie ma konfiguracji ESLint.

---

## 2026-08-12 — Sesja 5: Konfiguracja opencode pod projekt

### Cel sesji
Doposażyć opencode w narzędzia pracy: LSP, MCP EXA, komendy, formatter, skill — oraz naprawić narzędzia dev (lint/typecheck/testy).

### Co zrobiono

**LSP:**
- `lsp: true` w opencode.json (w opencode 1.18.16 LSP jest domyślnie wyłączony!)
- Zainstalowano `pyright` 1.1.411 + `typescript-language-server` 5.3.0 (npm global)
- TypeScript LSP nie startował automatycznie — brak `package.json` w root `/opt/finanse` (built-in wymaga "typescript dependency in project"). Rozwiązanie: jawny override `lsp.typescript.command` — wymaga restartu

**MCP EXA:**
- Remote endpoint `https://mcp.exa.ai/mcp`, `oauth: false`, header `x-api-key: {env:EXA_API_KEY}` (interpolacja z env, sekret NIE w repo)
- `EXA_API_KEY` w `~/.bashrc`; zweryfikowano `web_search_exa` end-to-end

**7 komend opencode (`.opencode/command/`):**
- `/test` (pytest+vitet), `/lint` (ruff+eslint), `/typecheck` (mypy+tsc)
- `/migrate`, `/migration "opis"` (alembic), `/deploy` (docker), `/docs` (aktualizacja docs)

**Narzędzia dev (naprawa):**
- `ruff` 0.16.2 + `mypy` 2.3.0 w `backend/.venv` (Makefile lint/typecheck nie działały — narzędzi brakowało)
- `pyproject.toml`: `[tool.ruff]` (line-length 100), `[tool.mypy]` (explicit_package_bases — błąd "source file found twice"), `[tool.pytest.ini_options]` (pythonpath — `ModuleNotFoundError: app`)
- Makefile: jawne ścieżki `.venv/bin/` (wcześniej wymagał aktywowanego venv)

**Formatter:** custom ruff (`$FILE`) + prettier (extensions ograniczone do kodu, `.md` wyłączone — chroni docs przed churnem)

**Inne:** references (docs, infra), watcher ignore, permissions (lsp/webfetch/websearch/gh), skill `session-workflow`, agent file zsynchronizowany

### Decyzje techniczne

1. **`lsp: true` w opencode.json** — w 1.18.16 LSP wyłączony domyślnie; `true` włącza wszystkie built-iny, object override dla konkretnych serwerów.
2. **MCP EXA remote zamiast local npx** — oficjalne zalecenie Exa dla OpenCode; `{env:EXA_API_KEY}` w headers = brak sekretu w repo; `oauth: false` zapobiega auto-detekcji OAuth.
3. **Custom formatter z jawnymi ścieżkami** — PEP 668 blokuje globalny pip; ścieżki do venv/node_modules zamiast `--break-system-packages`.
4. **TypeScript LSP wymaga root package.json** — opencode sprawdza zależności w root projektu, nie w podkatalogach; jawny command omija to sprawdzenie.

### Znane problemy

- **TypeScript LSP**: config dodany, wymaga restartu opencode, żeby wystartował.
- **Dług lintowy**: 210 błędów ruff (projekt nigdy nie był lintowany; 87 auto-fixowalnych).
- **Błędy typów**: 25 w mypy (7 plików), m.in. "Too few arguments" w `advisor/router.py:106` i `advisor/service.py:197` — możliwe realne bugi.
- **Testy integracyjne**: wymagają PostgreSQL na `localhost:5432`, a postgres jest tylko na wewnętrznej sieci Docker (port niezpublished) — 10 testów pada, 35 przechodzi.

### Następna sesja
1. Spłata długu lintowego (ruff --fix) + błędy mypy
2. Testy tool calling loop (Level 0 + Level 2 z potwierdzeniem)
3. Dokumentacja testów integracyjnych (DB w Docker)

---

## 2026-08-11/12 — Sesja 4: Dokumenty, ekstrakcja, Level 2, kalendarz, finanse

### Cel sesji
Dokończyć Iterację 2 (Stirling OCR + ekstrakcja danych), rozszerzyć Doradcę o narzędzia mutujące (Level 2), ulepszyć kalendarz i finanse.

### Co zrobiono

**Stirling PDF + OCR pipeline:**
- Worker async (Redis + ARQ): upload → SHA-256 → Stirling → OCR → tekst
- Pipeline dwustopniowy: najpierw OCR dokumentu (poprawka po tym, że jednorazowe OCR nie działało), potem ekstrakcja tekstu
- `documents/` — service, router, ARQ worker; frontend Dokumenty (upload, lista, podgląd)

**Ekstrakcja danych finansowych (`documents/extractor.py`, 94 linie):**
- OCR text → LLM (DeepSeek/OpenAI) → structured JSON: `type` (expense/income), `amount` w groszach, `currency`, `description`, `date`, `category_suggestion`
- `detected=false` gdy dokument nie zawiera danych finansowych; tekst ucinany do 8000 znaków
- Wynik → inbox item z sugerowaną transakcją → zatwierdzenie w Inbox

**Doradca Level 2 — mutacje z potwierdzeniem:**
- `registry.py`: `_execute_create_task`, `_execute_create_time_block`, `_execute_create_transaction` (167 linii)
- Endpointy `POST /tool-executions/{id}/confirm` i `/deny`: status `pending_confirmation` → `completed`/`denied`, `policy_check_passed=true`, audit log (`performed_by=human`)
- Frontend: przyciski potwierdzenia/odrzucenia w czacie

**Kalendarz (`Calendar.tsx`, +263/-74):**
- Widok miesiąca, taski z due dates, filtrowanie po zakresie dat, kolorowane bloki czasowe

**Finanse:**
- `actual_parser.py`: payee resolution z fallbackiem na kategorię
- `migrate_actual.py` (+76): opening balances
- Endpoint transakcji per konto (`/api/finance/accounts/{id}/transactions`)
- Redesign `Finances.tsx`: 470 → 86 linii (salde, wybór konta, transakcje)

### Decyzje techniczne

1. **Level 2 = poziom autonomii 2** (zatwierdzenie) — mutacje NIE wykonują się bez potwierdzenia człowieka; spełnia policy engine z AGENTS.md.
2. **Ekstrakcja przez LLM to sugestia, nie źródło prawdy** — LLM zwraca JSON, użytkownik zatwierdza w Inbox; kwoty w groszach (BIGINT).
3. **Two-step OCR** — oddzielny krok OCR + ekstrakcja tekstu (jedno przejście Stirling zwracało binarny PDF bez tekstu).

### Znane problemy

- Tool call bannery nie mają streamingu SSE; oczekujące potwierdzenia odświeża polling.
- Testy tool-calling loop dodano w późniejszej części sesji jakościowych.
- 3 daty USD bez kursu NBP (niedziele: 2026-05-30, 2026-06-14, 2026-06-21) — `base_amount_pln = source_amount`, do ręcznej korekty.

### Następna sesja
1. Konfiguracja opencode (LSP, MCP EXA, komendy) — patrz Sesja 5
2. Spłata długu: lint, typecheck, testy integracyjne

---

## 2026-08-12 — Sesja 3: Doradca z narzędziami

### Cel sesji
Podłączyć istniejące narzędzia (finanse, work) do Doradcy przez OpenAI function calling.

### Co zrobiono

**Tool Registry (`advisor/tools/registry.py`):**
- 6 narzędzi tylko-do-odczytu (autonomy level 0)
- Każde z OpenAI function schema + async executor
- Narzędzia: get_accounts, get_financial_summary, get_transactions, get_today_schedule, get_tasks, get_projects

**Tool Calling Loop (`advisor/service.py`):**
- Przepisane `send_message` — pętla tool calling (max 3 iteracje)
- LLM → tool_call → execute → result → LLM → odpowiedź
- Tool executions zapisywane w DB (model ToolExecution)
- System prompt zawiera opisy narzędzi

**Frontend (`Advisor.tsx`):**
- ToolCallBanner — expandable bannery między wiadomościami
- Pokazuje nazwę narzędzia, status (✓/✗), wynik (JSON)

### Decyzje techniczne

1. **Tylko poziom 0** — narzędzia obserwacyjne. Mutacje (create_transaction, create_task) na później.
2. **Tool registry jako osobny moduł** — czyste oddzielenie definicji narzędzi od pętli wywołań.
3. **Eager loading tool_executions** — selectinload w obu endpointach (send_message + list_messages) dla poprawnego zwracania relacji.

### Znane problemy

- ~~Frontend nie ładuje danych z API~~ — NAPRAWIONE. Wszystkie strony (Today, Inbox, Projects, Calendar, Finances, Advisor, Documents, Settings) używają TanStack Query i ładują dane poprawnie.
- Brak testów jednostkowych dla tool calling loop (trudne do mockowania DeepSeek API)
- Tool call bannery nie miały wówczas odświeżania w czasie rzeczywistym; późniejszy polling obejmuje oczekujące potwierdzenia.

---

## 2026-08-11 — Sesja 2: Import z Actual + Stirling OCR

### Cel sesji
Zaimplementować skrypt migracyjny Actual Budget → Personal Advisor i wykonać migrację produkcyjną.

### Co zrobiono

**ActualParser (`backend/app/finance/actual_parser.py`, 321 linii):**
- Odczyt kont (z filtrem tombstone/closed, detekcja waluty po nazwie)
- Odczyt kategorii (is_income → income/expense)
- Rekonstrukcja transakcji: simple (expense/income), transfery (self-join po transfer_id), splity (parent/child)
- Adaptacja do rzeczywistego schematu Actual: `v_transactions` (widok) vs `transactions` (tabela)
- Transfery: Actual używa wzajemnych referencji (A.transfer_id → B.id, B.transfer_id → A.id), nie wspólnego link ID

**NbpRateProvider (`backend/app/finance/nbp_rates.py`, 52 linie):**
- Async HTTP do NBP API (tabela A: EUR, USD)
- Cache per (waluta, data)
- Błędy NIE cache'owane (retry przy ponownej próbie)
- `calculate_base_amount()`: source_amount × fx_rate → zaokrąglone do groszy

**Skrypt CLI (`backend/scripts/migrate_actual.py`, 325 linii):**
- 4 fazy: extract SQLite → parse → resolve IDs → write
- Idempotentność: `description LIKE '[actual:{uuid}]%'`
- `--dry-run` / `--execute`
- Raport + log JSON

**Migracja produkcyjna:**
- 15 kont, 46 kategorii, 800 transakcji (734 simple + 66 transferów)
- 0 błędów, 1600 postingów (2 na transakcję, double-entry invariant zachowany)
- 8 ostrzeżeń NBP: USD w weekendy (niedziele: 2026-05-30, 2026-06-14, 2026-06-21)
- 0 split transactions w danych Actual

### Decyzje techniczne

1. **v_transactions zamiast transactions** — Actual używa widoku który już rozwiązuje payee i używa innych nazw kolumn (`account`, `transfer_id`). Parser wykrywa dostępność widoku i adaptuje zapytania.

2. **Transfery przez self-join** — W `v_transactions`, `transfer_id` wskazuje na ID drugiej transakcji (mutual reference), nie wspólny identyfikator. Rozwiązanie: `JOIN v_transactions t2 ON t1.transfer_id = t2.id WHERE t1.id < t2.id`.

3. **Ekstrakcja ZIP do /tmp** — Wolumen Actual montowany jako read-only, więc ekstrakcja ZIP musi iść do tymczasowego katalogu (`tempfile.mkdtemp`).

4. **NBP błędy niecache'owane** — Przy 404 (weekend/holiday) rate = 0.0 ale nie zapisujemy w cache, więc ponowna próba może zadziałać.

### Znane problemy

- **3 daty USD bez kursu NBP**: 2026-05-30, 2026-06-14, 2026-06-21 (niedziele). Transakcje z Revolut USD w te dni mają `base_amount_pln = source_amount`, `fx_rate_source = 'nbp_error'`. Do ręcznej korekty po migracji.

- **Split transactions nie występują** w danych Actual użytkownika. Kod parsera jest gotowy ale nieprzetestowany na rzeczywistych danych.

### Następna sesja
1. Stirling PDF + OCR pipeline (Iteracja 2)
2. Worker async (Redis + ARQ)

---

## 2026-08-10 — Sesja 1: Fundament + Deployment

### Cel sesji
Zbudować fundament Personal Advisor i wdrożyć na produkcję.

### Co zrobiono

**Architektura i projekt:**
- Wybrano podejście C: Hybrid (minimalny fundament + szybki vertical slice)
- Zatwierdzono strukturę: modularny monolit, 7 domen, double-entry ledger
- Utworzono 9 ADR-ów dokumentujących kluczowe decyzje

**Backend (FastAPI + SQLAlchemy):**
- 7 domen: identity, finance, work, inbox, advisor, documents, audit
- 16 tabel PostgreSQL przez Alembic auto-generate
- Auth: Argon2id + JWT HttpOnly cookies, Secure=True w produkcji
- Double-entry: transakcje + postings, invariant suma=0

**Frontend (React + Vite + Tailwind):**
- 9 stron z nawigacją, dark theme
- Auth flow: login → cookie → redirect /today
- TanStack Query hooks dla wszystkich domen API

**Infrastruktura:**
- `/docker/finanse/compose.yaml` — 5 serwisów
- npmplus: Actual → finanse.vps.birek.online, PA → finanse.birek.online
- SSL: Let's Encrypt (ważny do 2026-11-08)

**Workflow:**
- Dedykowany agent OpenCode: `.opencode/agent/personal-advisor.md`
- CHANGELOG.md, JOURNAL.md, TASKS.md

### Decyzje techniczne

1. **CORS_ORIGINS jako string zamiast List[str]** — pydantic-settings próbuje parsować JSON z env vars przed walidatorem. Rozwiązanie: pole jako `str` + property `cors_origins_list` z parsowaniem JSON/comma-separated.

2. **Cookie 7-dniowe, token 7-dniowy** — dla personal app (single user, nie bank), wygoda > restrykcyjne bezpieczeństwo. `ACCESS_TOKEN_EXPIRE_MINUTES=10080`.

3. **Frontend proxy /api/* przez nginx** — architektura: npmplus → frontend:80 (nginx) → /api/* → backend:8000. Frontend i backend na tej samej domenie, brak CORS w produkcji.

4. **Volume mount `/opt/finanse/backend:/app` w compose** — kod backendu montowany jako volume do kontenera. Pozwala na hot-reload (`--reload`). Do usunięcia w produkcji.

### Znane problemy

- ~~Frontend nie ładuje danych z API~~ — NAPRAWIONE w iteracjach 1-2.

- **Brak importu danych z Actual**: Actual działa na finanse.vps.birek.online ale nie ma jeszcze skryptu migracyjnego. Zaplanowane na Iterację 2.

- **Stirling PDF nie skonfigurowany**: kontener istnieje ale nie ma workflow OCR. Zaplanowane na Iterację 2.

- **`expose` zamiast `ports` w compose**: backend dostępny tylko przez sieć Docker. Dobrze dla bezpieczeństwa, utrudnia lokalny dev bez Dockera.

### Następna sesja
1. Dokumentacja sesji (CHANGELOG, JOURNAL, TASKS)
2. Inbox → Task end-to-end (pierwszy vertical slice)
3. Ekran Today z live danymi z API
