# Karty kredytowe — wdrożenie produkcyjne

Status: **wdrożone i zweryfikowane**.

## Zgoda i wersja

- Użytkownik: „scal do main i wdróż”, następnie osobno „Tak, migracja i wdrożenie”
  po wskazaniu dokładnej migracji `f3a9d17c2e4b → 00a9ccb532b9`, sześciu tabel,
  backupu, maintenance oraz wymiany backendu, workera i frontendu.
- FF i push `main`: `3479aca → 020c2296f2ea00fa7e296a6f5797cb76d6c571eb`.
  Bez force. Kod produktu identyczny z lokalnym odbiorem: manifest 569 plików,
  pełny backend 1847 PASS, frontend 555 PASS, E2E 159 PASS + 1 oczekiwany skip.
- Świeży gate po scaleniu: 952 backend unit, 555 frontend, Ruff/ESLint/mypy/tsc
  i build PASS; publiczne bajty buildu identyczne z artefaktem odebranym w E2E.
  Nie powtarzano całych integracji na produkcji ani wcześniejszych cudzych bazach.
- Pakiet `/opt/finanse/webapp/releases/020c229/`, trzy obrazy budowane offline.
  Obowiązkowy verifier gotowych image IDs z rzeczywistymi non-root UID:GID
  finalnego Compose oraz odczyt assetów nginx PASS, bez fallbacku do roota.
- Pełne base + prod + inherited active override; konfiguracja poza image/build
  identyczna, zachowane polityki AI, env, limity, sieci i montowania.
  Poprzedni release aplikacji `a68d9e4` i obrazy zachowane dla rollbacku.

## Backup i próba migracji

Świeży szyfrowany backup przez istniejący serwis, odtworzony do wyłącznie własnej
bazy loopback `credit_cards_020c229_rehearsal_restore`. Zweryfikowano checksumy dumpa
i uploads, stary schemat oraz księgę. Próba migracji w docelowym obrazie jako
docelowy użytkownik: zachowane kolumny i wiersze wszystkich 56 starych tabel,
sześć nowych pustych, zero naruszeń księgi; stare i nowe serwisy czytają konta
i kategorie tak samo. Przed APPLY powtórzono próbę na odrębnym świeżym backupie
wykonanym po zatrzymaniu aplikacji, w bazie `credit_cards_020c229_fenced_restore`:
wszystkie dotychczasowe wiersze i uploads zgodne z zamrożonym źródłem produkcji.
Snapshot i manifest nowsze od potwierdzonego fence, checksumy dumpa/uploads PASS.

## Pierwsza próba i jawny rollback

Pierwsza próba zatrzymała się na `frozen-idle`, **przed migracją**. Automatycznie
przywrócono starą aplikację: health 200, trzy stare image IDs, zero restartów,
schemat nadal `f3a9d17c2e4b`. Nie wykonywano downgrade lub odtwarzania produkcji.

RCA: worker zakończył się łagodnie z zerem trwających zadań, ale ARQ pozostawiło
zaplanowany cykliczny `cron:expire_category_proposals`. Kontrola wymagała pustej
kolejki także po zatrzymaniu workera, gdy nikt nie mógł odebrać tej przyszłej pracy.
Log po rollbacku potwierdził wykonanie tego samego opóźnionego zadania cyklicznego.

Poprawka dotyczy tylko operatorowego skryptu, nie obrazu produktu: tryb zamrożony
dopuszcza pozostawione znane funkcje cron z pasującym job ID i bez argumentów,
ale nadal wymaga zera aktywnych oraz trwałych zadań użytkownika. Brak usuwania
Redis jobs lub obchodzenia ochrony danych. Ścisły preflight działającej aplikacji
nadal wymaga pustej kolejki. Siedem izolowanych scenariuszy RED → GREEN, w tym
odrzucenie nieznanej funkcji, danych użytkownika, argumentów i aktywnej pracy.
Po poprawce ponownie zamrożono manifest skryptów i preflight przeszedł.

Przegląd operatorowych skryptów również wykrył trzy Important: rollback po
aktywacji metadanych, świeżość backupu względem fence oraz niepełny manifest
skryptów. Wszystkie poprawiono przed pierwszym maintenance. Manifest z brakami
odrzucony w RED, kompletny zaakceptowany w GREEN; fenced backup bez fence odrzucony
przed operacjami. MD5 fingerprint wierszy służy wykryciu przypadkowych zmian,
nie jest deklarowany jako dowód kryptograficzny wobec aktywnego przeciwnika.

## Udane przełączenie

- Publiczne 503 na czas maintenance; łagodnie zatrzymane stare backend/worker,
  brak aktywnej pracy. Bez kasowania Redis jobs; znane oczekujące cron zachowane.
- Produkcyjny Alembic uruchomiony raz w nowym obrazie i z pełnym inherited Compose:
  `f3a9d17c2e4b → 00a9ccb532b9`. Po migracji wiersze i kolumny wszystkich 56 starych
  tabel zgodne z baseline, sześć nowych pustych, księga bez naruszeń. Stare i nowe
  serwisy odczytują dotychczasowe konta i kategorie na nowym schemacie tak samo.
- Wymieniono tylko backend/worker/frontend. Nowy frontend utworzony jako zatrzymany,
  następnie ogrodzony maintenance przed startem. Bez host mountu `/app`.
- Przed otwarciem ruchu sprawdzono health, image IDs/revision, kod kart,
  niezmienione env/users/mounts i identyfikatory/czas startu/restarty usług danych;
  ponowiona retencja dotychczasowych danych i puste nowe tabele PASS.
- Po otwarciu: HTTPS health/login 200, anonimowe API kart i kandydatów oraz rachunki
  401; publiczne assety identyczne z odebranym pakietem.
- Przeglądarka produkcyjna tylko GET/HEAD/OPTIONS, bez sesji: szerokości 375/1440,
  login i chronione trasy, fonty, brak overflow i błędów JS; zero mutacji i obcego
  ruchu. Zrzuty obu szerokości obejrzane. Nie jest to test autoryzowanego zapisu karty.
- Końcowa obserwacja: **312 sekund, 31 kontroli**. Health 200, maksymalny zmierzony
  czas odpowiedzi 61 ms, trzy właściwe obrazy uruchomione, zero restartów i błędów
  w logach nowych kontenerów. Schemat `00a9ccb532b9`, zero naruszeń księgi, Redis
  gotowy; kontenery PostgreSQL/Redis/Stirling, obrazy i czasy startu bez zmian.
- Po tych bramkach atomowo zapisano prawdziwe metadane aktywnego release'u
  (`verified-live`) oraz trwałe prywatne dowody, bez plików env sond.
- Usunięto wyłącznie dwie własne bazy restore: nazwy, zapisane OID i brak połączeń
  sprawdzone przed `dropdb`, potwierdzony brak po usunięciu. Bez force i bez zmian
  produkcyjnej bazy lub innych środowisk testowych; `cleanup-proof.json` PASS.

## Granice zakresu

- Bez tworzenia sesji użytkownika lub zapisów próbnych w ramach smoke testu.
- Bez konfiguracji profilu „VELOBANK - karta”, tworzenia starych planów,
  automatycznego uzgodnienia salda, importów lub zmian historii.
- Bankowe terminy i harmonogramy mają pierwszeństwo; odsetki w aplikacji
  pozostają oznaczonym szacunkiem, nie wyliczeniem bankowej należności.
- Rollback aplikacji do zachowanego pakietu nie cofa addytywnego schematu;
  brak automatycznego downgrade lub odtwarzania bazy produkcyjnej.
- Dwa stare niezwiązane raporty Velo/Q7 pozostały nietknięte i poza commitem.

Dowody prywatne: `/tmp/opencode/credit-cards-release-020c229/` i trwała kopia
`/opt/finanse/webapp/releases/020c229/evidence/` z manifestem SHA-256,
handoff, proofami backupów/migracji, runtime/import/browser/observation/cleanup.
Metadane wskazują zachowany rollback do `a68d9e4`, z pozostawieniem schematu00a9.
