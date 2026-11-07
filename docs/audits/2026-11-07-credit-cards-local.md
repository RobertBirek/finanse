# Karty kredytowe — odbiór lokalny

Status: **odebrane lokalnie**. Bez merge/push/deploy
i bez konfiguracji lub modyfikacji produkcyjnego konta.

## Zgoda i zakres

Użytkownik zatwierdził obsługę istniejącej karty Velo (limit33600PLN, APR14.50%,
max57dni, nominalny termin12), wyciągów, kosztów/korekt, planów z niezależnymi
stopami i harmonogramami bankowymi, częściowych/wcześniejszych spłat, bez
podwójnego długu lub wydatku. Potwierdził zamknięcie starych planów. Po zmianie
Plan→Build powiedział „ok, działaj”, następnie jawnie zgodził się na własny
efemeryczny PostgreSQL bez publikacji portów i bez używania istniejących baz.

Plan: `docs/superpowers/plans/2026-11-07-credit-cards.md`.
Instrukcja i ograniczenia: `docs/operations/credit-cards.md`.
Bazowa rewizja:3479aca, istniejący linkedworktree. Dwa wcześniejsze robocze raporty
Velo/Q7 nie należą do tej zmiany i nie są stage'owane.

## Decyzje

1. Księga pozostaje źródłem salda. Plan klasyfikuje kapitał istniejącego zakupu/
   wypłaty; nie dopisuje zadłużenia. Bez aktywnych starych planów nie odtwarzamy
   ich na podstawie samych nagłówków wyciągów. Koszt tej decyzji: osobne bankowe
   saldo niewymagalnego kapitału wymaga jawnego uzgodnienia przy imporcie, a nie
   odgadywania i automatycznego wyrównania.
2. Estymacje APR/12 (równy kapitał) i ACT/365 są wyraźnie przybliżone. Brak taryfy
   i kolejności zaliczania wpłat nie uprawnia do twierdzenia, że dokładnie obliczamy
   bankowe odsetki i warunki 57dni. Koszt: szacunki mogą różnić się od banku.
3. Warunki konkretnego konta nie są zaszyte w kodzie lub migracji i nie wybieramy
   rachunku po nazwie. Konfiguracja istniejącego konta nastąpi dopiero po osobnym
   odbiorze/wdrożeniu. Koszt: wymagany jeden świadomy zapis ustawień użytkownika.
4. Pomyłkę w niepowiązanych metadanych można usunąć bez usuwania transakcji;
   rozliczona historia i ledger są chronione, działanie pozostawia audit.
5. Dwa nowo utworzone testowe PostgreSQL izolują baseline i implementację;
   oba `network=none`, bez publikacji portów i bez hostmountów. Użyto `nsenter`
   wyłącznie do sieci tych nowych procesów. Nie połączono żadnej starej bazy.

## TDD / wyniki przed końcowym review

- Matematyka11RED→11PASS; walidacja9RED→20PASS; overflow1RED→21PASS.
- API7RED(404 brak funkcji)→7PASS. Dalsze testy edycji/audytu, blokady dat,
  harmonogramu bankowego, powiązania już istniejącego kosztu i osi alokacji.
- Testy równoległych alokacji i odrzucania oczekujących/cudzych danych PASS.
  Usuwanie błędnej metadanej1RED→PASS, bez zmiany salda/liczby transakcji.
- Downgrade z zapisanymi warunkami1RED→guard; pusty roundtrip PASS.
- Migracja autogenerate wykazała też stare różnice indeksów harmonogramów:
  usunięto je z nowej migracji jako niezwiązane. Praktyczna próba wykazała zachowanie
  **56 starych tabel**, ich wierszy/kolumn/indeksów, dodanie tylko sześciu nowych
  i pusty downgrade/reupgrade. Test wyłącznie na własnej bazie `card_migrations`.
- Baseline pełny backend: **1805PASS**,14deselected,10znanychwarnings,4250.19s.
- Pełny backend przed review: **1841PASS**,14deselected,10warnings,3434.97s.
- Frontend: **555PASS/91plików**,57.65s, ESLint/tsc PASS.
- Build PASS z istniejącym ostrzeżeniem o rozmiarze pakietu. Pierwsze nowe E2E:
  5PASS/1FAIL — Axe wykrył zbyt jasny `text-green-300` na białym tle. Zmieniono
  na już istniejący semantyczny token `text-green-400`; odchylenie też używa
  istniejącego koloru błędu. Pełny świeży E2E po poprawce: **159PASS/1oczekiwanyskip**,
  5.1min, obie szerokości i motywy, w tym nowe karty i kontrole Axe/overflow.
  Świeży build/ESLint/tsc PASS. Obejrzano screenshot desktop jasny i mobile ciemny.
- Końcowy unit frontend po wszystkich zmianach: **555PASS/91plików**,55.51s.
  E2E używa statycznego buildu i izolowanych fixture API, bez produkcji; właściwe
  obliczenia/księgowanie są oddzielnie testowane na prawdziwym własnym PostgreSQL.

## Niezależny review i poprawki

Jedna sesja read-only: `ses_e490e7f92ffeTtwAqL0GiDaGcT`.

- Important1: zwrot miał kategorię kosztu i prawidłowy koszt netto, ale typ
  transakcji `income`, błędny dla odbiorców filtrujących po typie.
- Important2: brak rozdzielenia kont obsługi kredytu i kart.
- Minor3: dopuszczanie odwróconych typów przy powiązaniu istniejącego kosztu.
  Przeklasyfikowano jako część Important1: niezgodność reprezentacji finansowej,
  nie kosmetyka. Jedna wspólna poprawka wymaga typu expense oraz właściwego kierunku.

Testy review:3RED/1ochronnyPASS→4PASS. Zwrot ma teraz kontrolowaną ścieżkę
`expense` z odwróconymi postings, niedostępną przez sam `source` klienta.
Konfiguracja karty i tworzenie umowy kredytowej obustronnie odmawiają wspólnego
konta, pod tą samą blokadą zmian użytkownika. Końcowy pełny backend po tej
pojedynczej rundzie poprawek jest uruchomiony; nie zastępujemy go wcześniejszym1841.

Jeden ukierunkowany przebieg cards+loans został przerwany limitem120s po32testach;
nie oznaczono go jako PASS. Później cztery testy napraw przeszły22.89s, a pełny
backend jest uruchomiony bez limitu. Logi zachowano.

### Granice review

- Dokładne taryfy bankowe/grace/kolejność spłat: estymacje pozostają oznaczone,
  fakty i harmonogram banku mają pierwszeństwo. Ryzyko różnicy szacunku jawne.
- Historyczne zmiany pending: brak nieistniejącej historii tych zmian; pokazujemy
  uzgodnienie na podstawie bieżącej księgi i dat, nie gwarancję dawnego stanu banku.
- Reviewer nie uruchamiał testów: wykonawca odczytuje zakończone logi i oddzielnie
  raportuje każdy nowy gate. Brak twierdzenia o testach na produkcji.

## Dowody

Logi, build, proof migracji i zrzuty UI:
`/tmp/opencode/credit-cards-20261107/` (prywatny katalog).
Końcowe wyniki/commit/cleanup zostaną dopisane po zakończeniu gate.

## Końcowy odbiór — PASS

- **Backend1847PASS**, zero failures/errors/runtime-skips; podział1042+805,
  zwykła kolejność plików w każdej grupie. Czas2427.38s i1745.07s. Manifest pełnej
  kolekcji:1847wybranych/1861,14standardowo wyłączonych proxy. JUnit potwierdza
  rozłączność i pełne pokrycie wybranych plików.12powtórzonych znanych ostrzeżeń
  zależności w dwóch procesach, nie błędy aplikacji. Każda grupa uruchomiona na
  swoim nowym offlinePG; żadnych integracjiDB pominiętych z powodu niedostępności.
- **Frontend555PASS/91plików**,55.51s; **159E2EPASS/1expectedskip**,5.1min.
  Świeży build i lint/types obu stron PASS, mypy152pliki. Ostrzeżenie builda
  o rozmiarze istniejącego pakietu pozostaje jawne i nie było naprawiane poza zakresem.
- Porównanie manifestu569plików przed i po testach potwierdziło identyczne źródła.
  Dowód migracji:56starychtabel/wierszy/kolumn/indeksów zachowanych i6nowych tabel,
  pusty downgrade/reupgrade, guard odrzucający utratę zapisanych danych.
- Jedna niezależna sesja review; Important i powiązana niespójność klasyfikacji
  naprawione przez RED→GREEN. Późniejsze konkretne regresje kontraktu, retry po
  odpięciu metadanej i prywatności również odtworzone i naprawione przed finalnym
  pełnym przebiegiem. Bez drugiej sesji review, bez ukrywania wcześniejszych błędów.
- Commity produktu: backend **09d1d79**, frontend **7aa1629**; następny commit
  wyłącznie dokumentuje odbiór. Gałąź `feat/financial-document-workflow` zachowana.
- Usunięto **wyłącznie dwa własne** testowe PostgreSQL i ich anonimowe wolumeny,
  po porównaniu pełnych DockerIDs ze złożonymi wcześniej plikami identyfikatorów.
  Brak tych kontenerów po cleanup potwierdzony; sharedimage i wcześniejsze usługi
  pozostawione. `cleanup-proof.json` PASS.

Dowody finalne: `acceptance-final/final-suite-proof.json`, manifesty i JUnit,
`tested-source-manifest-acceptance.json`, `migration-proof.json`, `cleanup-proof.json`
w prywatnym katalogu `/tmp/opencode/credit-cards-20261107/`.

Następny krok wymaga odrębnej zgody: integracja/main/push, backup i kontrolowana
migracja produkcyjna f3a9→00a9, deployment, a następnie świadoma konfiguracja
istniejącego konta oraz uzgodnienie salda. W tej sesji **nie zmieniono main,
kontenerów aplikacji, schematu produkcji ani danych użytkownika**.

### Regresja publicznego kontraktu wykryta w pełnym przebiegu

Pierwszy pełny przebieg po review: **1844PASS/1FAIL**,14deselected,3297.89s.
Jedyny błąd: `test_service_retains_transaction_and_forecast_call_signatures`.
Nowy keyword argument zmienił istniejącą publiczną sygnaturę. Nie zmieniono
testu kontraktu. Po odtworzeniu RED wydzielono prywatne wspólne księgowanie
i osobny kontrolowany `create_card_refund_transaction`; publiczny
`create_transaction` zachowuje dokładnie dotychczasową sygnaturę i tożsamość
entrypointu fasady. Kontrakt i wszystkie testy kart: **23PASS**,61.59s.

Końcowy ponowny odbiór backendu obejmuje wszystkie wybrane przypadki, podzielone
całymi plikami między dwa wcześniej zatwierdzone, własne PostgreSQL. Manifest
kolekcji dowodzi rozłączności i kompletności, a JUnit musi potwierdzić zgodną
liczbę przypadków i zero failures/errors/skips. To skrócenie czasu powtórnego
odbioru, nie wyłączenie testów lub zmiana ich warunków. Poprzedni pojedynczy
pełny przebieg i jego błąd pozostają jawne. Source manifest aktualizuje wyłącznie
dwa pliki poprawki fasady; frontend i schemat pozostały identyczne.

### Dalszy odbiór: kolejność testów i ochrona późnego ponowienia

Pierwszy podział całych plików był uporządkowany według szacowanego kosztu:
grupa1 **804PASS**, grupa0 **1040PASS/1FAIL**. Jedyny błąd dotyczył starego
`test_vision_upload_redis_failure_keeps_durable_job_for_dispatch`: domyślny pool
asyncpg był używany z innym event loop po zmianie kolejności plików. Nie zmieniano
kodu OCR lub jego testu. Próba samotnego pliku miała5setupERROR, ponieważ nie
rejestrowała pełnych modeli przed autouse fixture. Powtórka z normalną rejestracją
aplikacji: **6PASS**,37.27s. To błąd założeń uruchomienia testów, nie nowy zakres
naprawy modułu dokumentów. Ostateczny podział zachowuje zwykłą kolejność plików
pytest wewnątrz obu grup.

Podczas odbioru uzupełniono dwie konkretne regresje bezpieczeństwa:
- Dawny klucz po celowym usunięciu opisu kosztu nie może odtworzyć księgowania.
  Test1RED→PASS; istniejący audit utworzenia jest trwałym tombstone klucza.
  Koszt decyzji: audit utworzenia trzeba zachować lub zastąpić równoważnymi
  receiptami przed ewentualnym przyszłym usuwaniem logów. Nie dodano kolejnej tabeli.
- Cudzy identyfikator wyciągu nie ujawnia stanem409 zamiast404, czy ma spłaty.
  Test1RED→PASS; sprawdzamy właściciela przed sprawdzeniem powiązań.

Wszystkie testy kart po tych uzupełnieniach: **19PASS**,76.07s; Ruff i mypy152 PASS.
Niedokończona powtórka jednej grupy została świadomie przerwana SIGINT dopiero
po wykryciu potrzeby tych uzupełnień — nie służy jako dowód PASS. Końcowy pełny
odbiór **od nowa**, obu grup, normalny porządek, nowy manifest kodu i kolekcji:
`acceptance-final/`. Wcześniejsze błędy/logi zachowano bez nadpisywania. Frontend,
schemat i raport retencji pozostają identyczne; brak operacji produkcyjnych.
