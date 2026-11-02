# Wydanie dokumentów i całego AI na OpenAI — 2026-11-02

## Zgoda i zakres

Użytkownik polecił bezpośrednie wdrożenie zamiast pilotażu, przeniesienie całego AI
aplikacji na OpenAI i zatwierdził modele: `gpt-6.1-sol` dla doradcy/narzędzi oraz
`gpt-6.1-terra` dla ekstrakcji tekstu i obrazów. Następnie polecił dokończyć.
Nie obejmuje to innych projektów VPS, importów historii, płatności ani samoczynnego
zatwierdzania propozycji. Oryginały dokumentów i stare dane pozostają niezmienione.

## Stan: WDROŻONE I ODEBRANE — 2026-11-02T11:05:32Z

- Poprzednie aktywne aplikacje: `9db255b`, schema `c2d7e9a4f801`.
- Przyrost dokumentów/vision odebrany wcześniej w `bb831ce` (kod `85e086c`).
- Nowa migracja klientów Responses odebrana w `84c9c271ba9c8ceabfcbad07bb6dced5f1701f0a`.
- Zgoda dotyczy wymaganych addytywnych migracji c2→7f8→92; nie dodano migracji
  dla samej zmiany dostawcy. Produkcyjne upgrade, kontrolowane przełączenie i jawny
  policy enable i końcowa obserwacja zakończyły się powodzeniem. Metadane aktywnego
  wydania zaktualizowane atomowo, rollback zachowany. Nie ponawiać apply.

## Dowody przygotowania

- Świeży zaszyfrowany backup `a82d4237`, backup i zainstalowany restore drill success/0.
- Odczyt produkcji: 23 legacy tables, zero naruszeń minimum2postingów/sumy0,
  brak aktywnych dokumentów, hashe9 oryginalnych plików zachowane w prywatnym baseline.
- Frontend build i pełne E2E: **93 PASS, 1 celowy skip**, kod frontendu bez zmian.
- GET obu modeli z projektowym kluczem:200/id zgodny; nie ujawniono klucza.
- Nowy runtime zależności rzeczywiście zbudowany offline z wheelhouse; SDK2.54.0,
  pip check i import/Responses jako UID10001 PASS. Finalny pakiet84c9c27 zarchiwumGit,
 199plików backendu w każdym obrazie zgodne hashami, brak hostmountu /app.
- Pierwszy pełny backend:1021PASS/4FAIL. Cztery błędy testów CLI wynikały z zależności
  od usuniętego ignorowanego scratchgate poprzedniego planu; testy przenoszą źródło
  DSN na rzeczywisty guarded fixture zamiast odtwarzać prywatny artefakt w repo.
- Operacyjny review zatrzymał procedurę przed jej wykonaniem: renderowana konfiguracja
  ma być utrwalana tylko po redakcji. Wdrożono HMAC-porównanie zmienionych sekretów,
  bez ich wartości w artefakcie. Offline6guard regresji PASS. Scoped odbiór warunkowo
  zaakceptowany; wymaga jeszcze rzeczywistego rehearsal rollbackdisable bez visionconfig.
- Bezpośrednie syntetyczne Responses SDK dla Sol/Terra completed/OK. Test przez
  aplikacyjny transport wykrył podwójną dekompresję gzip (APIConnectionError przyczynowo
  DecodingError); lokalna reprodukcja potwierdza błąd. Independentreview zatrzymał
  kandydata przed wdrożeniem. Poprawka transportu i3regresje spec/wire następnie odebrane.
- Końcowy gate po poprawce: **1031 backend PASS, 8 deselected, 10 znanych warningów;
 308 frontend PASS**, lint/types PASS. Scopedreview transportu i3regresji Approved.
- Rzeczywisty test na dokładnym obrazie84c9c27: Sol wykonał1 fikcyjne narzędzie odczytu,
  Terra poprawnie obsłużyła ekstrakcję tekstową, review i syntetyczny JPEG. Zero połączeń
  do produkcyjnej bazy i zero prywatnych dokumentów.
- Zainstalowany restore drill po aktualizacji hostcheckout do84c9c27 success/0; migracje
  następnych backupów pozostają dostępne w hostrepo. Bez push do zdalnego repozytorium.
- Rehearsal na network-none kopii: c2→92,23staretabele/kolumny/wiersze niezmienne,
  zero naruszeń ledger, nowy startup UID10001 PASS. Cykl polityki1→2→3 potwierdza
  aktywację i disable bez visioncredentials. Operatorbootstrap importuje app.main dla
  rejestracji modeli SQLAlchemy (bez lifespan); bez tego standaloneCLI nie zna users
  potrzebnych do flush audytu. Trwały rollback używa tej samej zweryfikowanej procedury.
- Końcowy operacyjny odbiór: Approved for authorized apply, bez otwartych blokad.

## Pierwsza próba i kontrolowane ponowienie

Pierwszy apply poprawnie wykonał migrację c2→92 i wymienił aplikacje, lecz automatycznie
cofnął je do9db: guard wymagał niezmiennego audytu, a cztery własne anonimowe GET401
dopisały cztery prawidłowe wpisy `security/session_rejected/system`. Nie był to błąd
OpenAI ani zmiana danych finansowych. Niezależny odczyt potwierdził zachowanie wszystkich
starych wierszy, dokumentów i oryginałów, usług danych, oraz policyfalse/epoch1.

Guard zachowuje wszystkie stare wiersze audytu i dopuszcza tylko dokładnie policzone,
niezależnie zidentyfikowane dopiski tego typu (4 jawne401 oraz późniejszy licznik401
przeglądarki), nie dowolny przyrost. Regresje9PASS, scoped odbiór Approved. Kontrolowane
jednorazowe ponowienie używa osobnego baseline po rollbacku, sprawdza zgodność starych
obrazów, nie ponawia migracji. Dowody pierwszej próby zachowane w prywatnym first-attempt/.

## Odbiór produkcyjnego przełączenia

- Backend/worker/frontend działają na84c9c27; policyvision aktywna po jawnej CLI
  expectedepoch1→2. Obrazy przypięte ID, pełny Compose z zachowaniem hardeningu.
- HTTPS/login/health/staticassets oraz4anonimowe API401 PASS. Guard starych wierszy,
  oryginałów i usług danych PASS; brak automatycznych importów/przetwarzania historii.
- Egress i dostęp do obu modeli z rzeczywistego kontenera produkcyjnego200PASS,
  bez wysyłania treści dokumentów. Wcześniejszy pełny liveadapter używał syntetyków.
- Read-only browser375/1440 PASS, brak mutacji przeglądarki i błędów JS.18własnych401
  policzonych w guardzie audytu. Ostatnia pięciominutowa obserwacja10/10PASS,
  zero restartów/nowych błędów, atomowy zapis active-release metadata PASS.
- Backend/worker imageID `sha256:0382796371d0de2d1e73e01d9a098b20eeda637bbaf7ec2d4ac0ca0d45afa876`;
  frontend `sha256:ca9bcb29409cba7e59164556868f858cf28fb5e8f11a0daf083e54f6a9f044a4`.
- Pełny finalny Compose: bazowy+prod+`/opt/finanse/webapp/releases/84c9c27/compose.active.yaml`.
  Rollback: `/opt/finanse/webapp/releases/84c9c27/rollback.sh`, wyłączenie vision przed
  przywróceniem9db, schema92 pozostaje. Prywatne tymczasowe backend.env/worker.env usunięte.
- Dodatkowy zaszyfrowany backup po przełączeniu `e037d2e8` i zainstalowany restore
  tego stanu schema92: success/0. Poprzedni backup sprzed migracji zachowany.

CI zdalne: nie uruchamiano (bez push). Dowodem źródła jest pełny lokalny gate dokładnej
rewizji i kontrola zawartości obrazów, nie twierdzenie o zielonym zdalnym CI.

Guard niezmienności dotyczy okna wdrożenia zakończonego `verified_on`. Późniejszy
zwykły ruch użytkownika (odrzucenia sesji/logowanie) nie jest rozszerzeniem smoke
ani powodem do cofania wydania. Świeży health i identyfikatory obrazów po zakończeniu PASS.

## Dane i ograniczenia

`store=false` we wszystkich wywołaniach. Dane API nie służą domyślnie do treningu;
standardowe logi bezpieczeństwa mogą pozostać do30dni. Nie obiecujemy ZDR. Osobna
konfiguracja i polityka vision, bez fallbacku DeepSeek lub automatycznego backfillu.
Rollback wyłącza vision przed starymi obrazami i zachowuje addytywny schema; bez
automatycznego downgrade. Nie certyfikowano prawdziwych Android/iPhone.

Prywatne dowody: `/tmp/opencode/openai-production-20261102/` (0700), bez sekretów
w raporcie publicznym. Dowody implementacji: podkatalog `implementation-evidence/`.

## Rozstrzygnięcia koordynatora i koszt pomyłki

1. Zatwierdzony opis i polecenie natychmiastowego wydania uznano za zgodę na wykonanie
   wąskiego planu bez kolejnego pytania o metodę pracy; koszt: inna kolejność wewnętrzna
   może wymagać odwracalnej korekty przed apply.
2. SDK2.54.0 zamiast3.42.1 zachowuje httpx0.27; koszt: osobny przyszły majorupgrade.
3. Historyczny zapis tool_calls pozostaje bez migracji, zmienia się adapterwire;
   koszt: dodatkowa logika replay, zabezpieczona regresją rzeczywistego SDK.
4. Lokalny hostmain FF do84c9c27, bez push, zapewnia nowe migracje installedrestore;
   koszt: lokalny main posuwa się naprzód. Obrazy starego runtime i rollback zachowane.
5. Operatorbootstrap rejestruje modele przez importapp.main przed CLI.run, bezlifespan;
   koszt: zależność operatora od importu aplikacji. Bezpieczne disable nie wymaga
   visionkey/config; potwierdzono rzeczywisty cykl na izolowanej kopii.
6. Guard dopuszcza wyłącznie dokładnie policzone dopisane audyty własnych401,
   nigdy zmiany starychwierszy; koszt: równoległy legalny ruch może zatrzymać odbiór.
7. Po wyjaśnionym rollbacku wykonano jeden kontrolowanyresume z nowymbaseline,
   bez powtarzania migracji; koszt: ewentualny kolejny rollback, bez ślepego retry.
8. Redakcja sekretów pomija tylko3jawne numeryczne limity tokenów; koszt: dodatkowy
   cykl weryfikacji metadanych. Pierwsza konsolidacja zatrzymana przed zapisem active
   metadata, nigdy nie zastosowano błędnego override. Rzeczywiste klucze nadalHMAC,
   ponowny render porównany z poprzednim dokładnie, bez zmiany parametrów runtime.
