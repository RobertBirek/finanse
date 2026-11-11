# Lokalny odbiór importera harmonogramów Velo

Aktualizacja: 2026-11-11. **B1–B6 i cały zaakceptowany zakres A+B odebrane lokalnie.**
Ten raport nie potwierdza wdrożenia ani importu danych użytkownika.

## Zakres i granice

Importer obsługuje rozpoznany tekstowy PDF harmonogramu Velo w PLN. Użytkownik
wybiera umowę, sprawdza porównanie i potwierdza aktywację. Każda wersja zachowuje
snapshot rat i odnośnik do źródła. Aplikacja przechowuje kwoty w groszach.

Harmonogram nie tworzy transakcji, postingów, salda długu, kosztów lub statusu
zapłaty. Pokrycie nadal zależy od rzeczywistych przelewów i jawnych powiązań.
Przy pierwszej aktywacji istniejącego kredytu aplikacja zapisuje ręczną bazę
historyczną. Migracja nie wykonuje backfillu.

Produkcja, Q7, historia Actual i prywatne oryginały pozostają bez zmian.
Nie wykonano merge, push, deployu, produkcyjnej migracji ani realnego importu.
Testy używają własnego PostgreSQL i runnera bez publikowanych portów.

## Zapisane etapy

| Etap | Commit | Potwierdzony odbiór |
|---|---|---|
| B1: wersje, projekcja legacy, addytywna migracja | `1c60da2` | backend 2204 PASS, retencja i brak backfillu |
| B2: deterministyczny parser PDF | `93abf48` | backend 2235 PASS, 2 oryginały po 59 rat, tylko odczyt |
| B3: diff, aktywny zakres, ochrona mutacji | `d7cff54` | backend 2259 PASS, wyścigi dwóch sesji |
| B4: podgląd, aktywacja, receipt, historia | `976f06c` | backend 2288 PASS, frontend 596 PASS |
| B5: UI, izolacja sesji, źródła historii | `a8fabf7` | backend 2289 PASS, frontend 613 PASS, 4 browser PASS |
| B6: całościowy odbiór i runbook | lokalny commit końcowy | backend2300, frontend617, E2E183 PASS po poprawkach review |

Pełne przebiegi B1–B5 mają 14 standardowo wyłączonych testów proxy i zero
runtime-skips. B5 obejmuje 437 hashy backendu i 303 frontendu, 15 plików builda,
lint/typecheck obu warstw i osiem obejrzanych zrzutów w light/dark na 375/1440 px.

## B6: rzeczywista integracja

Testy używają syntetycznych PDF, uploadu HTTP, trwałego zadania w PostgreSQL,
rzeczywistego workera i parsera, aktywacji oraz nowej sesji DB. Nie podstawiają
gotowych wierszy parsera. Sprawdzają:

- reuse UUID i istniejącej częściowej spłaty, sumy listy oraz szczegółów;
- ten sam receipt po ponowieniu i odczycie, prywatny oryginał i duplikat bajtów;
- krótszy plan z numeracją od 1, zachowanie opłaconej historii i wyłączenie starego ogona;
- HTTP409 po zmianie spłaty między podglądem a aktywacją, bez wersji lub receipt;
- niezmienione konta, transakcje, postings, mapowania Actual i linki płatności;
- owner-scoped pobranie oryginału i odmowę archiwizacji/usunięcia źródła.

Pierwszy przebieg dał **1 FAIL / 2 PASS**. Aktywacja zapisywała plan, ale odczyt
batcha nadal zwracał `not_committed` i nierozstrzygnięte wiersze. Poprawka uwzględnia
membership rat w liczniku i zapisuje `partial`/`committed` w tej samej transakcji
co wersja i receipt. Kolejny przebieg: **3 PASS**. Rozszerzone kontrole retencji,
oba rzeczywiste roundtripy Alembic i pełny backend są teraz w końcowej bramce.

Testy przeglądarki korzystają z syntetycznego API i dokładnego builda produkcyjnego,
bez rzeczywistego serwera lub danych bankowych. Oddzielny test backendu potwierdza
parser i zapis DB; fixture przeglądarki nie stanowi dowodu poprawności parsera.

## Wykryte i poprawione problemy B5

- Link powrotny po aktywacji prowadził do nieistniejącej trasy. Test RED odtworzył
  błąd; UI kieruje do `/settings/finances/loans?loan=…`.
- Formularz i historia miały ten sam klucz React. Przełączenie umowy dublowało
  formularz. Rozdzielenie kluczy zachowało istniejące asercje regresji.
- Historia poszerzała mobilny grid poza ekran. Przegląd zrzutów wykrył problem,
  którego nie łapał pomiar dokumentu. Test granic kart przeszedł po ograniczeniu
  kolumny, `min-w-0` i zawijaniu akcji, bez ukrywania overflow całej karty.

Przejściowy timeout istniejącego testu archiwum dokumentów w B4 pozostał w dowodach.
Test przeszedł osobno i w ponownym pełnym przebiegu bez edycji asercji lub timeoutów.
Nie przypisano mu fikcyjnej naprawy produktu. B6 E2E wymagało poprawienia locatorów
nowego testu do istniejących etykiet UI; tych błędów nie uznano za regresje produktu.

## Ograniczenia

- Nieznany układ, brak daty obowiązywania lub niepełna tabela blokują aktywację.
- Pominięta lub zmieniona przyszła rata z powiązaną spłatą blokuje całą aktywację.
- Przeszłe niepokryte raty pozostają widoczne; brak zgodnej niepowiązanej raty blokuje zapis.
- Wybór rewizji-kandydata wymaga porównania obu tabel i potwierdzenia konkretnego
  odczytu. Nowa wersja planu wskazuje wybraną rewizję, bez nadpisania starej ekstrakcji.
- Klucz niepewnej komendy żyje w pamięci widoku. Zapisany receipt udanej aktywacji
  można odzyskać po otwarciu źródła bez klucza; niezakończona komenda może nadal wymagać
  sprawdzenia receipt przez operatora.
- Szerokie tabele przewijają się w swoim kontenerze. Build zgłasza dotychczasowe
  ostrzeżenie o bundle większym niż 500 kB.

## Stan końcowych bramek

Pełny backend, frontend/E2E i jeden niezależny review są w toku. Dopiero wynik
JUnit, zgodne manifesty i rozpatrzenie uwag review pozwalają zamknąć B6.
Nie traktuj numerów z B5 jako wyniku nowych testów B6.

Aktualizacja przed poprawkami review: frontend 613 PASS, pełne E2E 179 PASS oraz
1 oczekiwany skip desktopowego wariantu testu przeznaczonego wyłącznie na mobile
(mobile PASS). Lint, typy i build PASS; 304 hashe źródeł zgodne. Build pozostaje
identyczny z obejrzanym artefaktem B5. Backend nadal w toku.

Niezależny reviewer wskazał **2 Important**, bez Critical/Minor: brak odczytu receipt
po ponownym otwarciu widoku oraz brak ścieżki wyboru/porównania odczytu nowym parserem.
Autor potwierdził obie luki. B6 nie jest zamknięte; poprawki wymagają RED→GREEN i nowych
pełnych bramek. Wyniki powyżej są punktem odniesienia sprzed tych poprawek.

### Pojedynczy fix pass po review

Testy odtworzyły brak receipt w odczycie źródła i blokadę wyboru nowej rewizji.
Po rozszerzeniu testów także status importu po aktywacji kandydata oraz wybór
kontroli nowego parsera miały potwierdzone RED. Poprawki zachowują ekstrakcję bieżącą
i poprzednie wersje. Równoważny kandydat wskazuje istniejący receipt; zmieniony
przechodzi zwykły diff i jawne zatwierdzenie. Nie ma nowego przycisku aktywacji
dla równoważnego odczytu.

Skupiona regresja backendu: **43 PASS**, ruff PASS, mypy 191 plików PASS.
Po restarcie autor potwierdził, że polecenie frontendu nie wystartowało (brak logów
i procesów), więc uruchomił je po raz pierwszy. Pełny backend po poprawkach,
frontend i przeglądarka są teraz w toku. Nie odbywa się drugi review.

Frontend po poprawkach: **617 PASS**, lint/typecheck/build PASS, **12 skupionych
scenariuszy przeglądarki PASS**. Autor obejrzał cztery nowe ekrany porównania w light/dark
na 375/1440 px. 307 hashy frontendu i 15 plików builda są zgodne. Pełne E2E na tym
samym buildzie oraz pełny backend po poprawkach nadal trwają.

Pełne E2E po poprawkach zakończyło się: **183 PASS, 1 oczekiwany skip** (desktopowy
wariant testu przeznaczonego wyłącznie na mobile; mobile PASS), 8,2 min.
307 hashy źródeł i 15 plików builda nadal się zgadza. Frontend ma komplet dowodów;
do zamknięcia B6 pozostaje pełny wynik backendu po poprawkach z JUnit i manifestem.

## Końcowy wynik po poprawkach review

- **Backend: 2300 PASS**, 14 standardowo wyłączonych proxy, zero runtime-skips,
  10128,69 s. JUnit i kolekcja potwierdzają brak błędów, failures i skips.
- **Frontend: 617 PASS**, lint i typy obu warstw oraz build PASS.
- **Pełne E2E: 183 PASS + 1 oczekiwany skip**, 8,2 min. Skip dotyczy desktopowego
  wariantu mobilnego kalendarza; test wykonał się na mobile.
- Skupiona regresja po review: 43 backend PASS, 12 browser PASS. Nowe testy
  odtworzyły obie ważne luki przed poprawką; żadne obejście nie wyłącza kontroli.
- **747 hashy źródeł** (440 backend +307 frontend) i15 plików builda zgadza się
  z odebranymi artefaktami. Backend przechodzi testy w niezmiennym snapshotcie.
- Oba realne Alembic roundtripy z retencją przeszły w B6; pełny przebieg po poprawkach
  także wykonał testy migracji. Oryginały po59 rat pozostały parser-only i niezmienione.
- Jeden świeży review: brak Critical, dwa Important poprawione w jednym RED→GREEN
  fix pass, brak Minor i pozycji odłożonych bez oceny. Nie wykonywano drugiego review.

Operator zachowuje gałąź i worktree. Końcowy commit i task-done nie upoważniają do
merge, push, deployu, produkcyjnej migracji lub importu rzeczywistych harmonogramów.
Cleanup obejmuje wyłącznie wcześniej zatwierdzone własne zasoby testowe po kontroli
ID, etykiet, sieci, portów i mountów. Historia Actual, Q7 i oryginały nie były modyfikowane.

## Rejestr decyzji autora

Pełny ledger zachowuje także decyzje tymczasowe. Poniżej kolejność i koszt pomyłki:

1. Membership zawiera loan_id i klucze owner/loan w SQL. Koszt: dodatkowe indeksy i kolumna;
   tożsamości starych danych pozostają bez zmian.
2. Seed testów starej migracji używa starych fizycznych kolumn, nie nowszego ORM.
   Koszt: utrzymanie testowego SQL, zamiast fałszywego testu przyszłego schematu.
3. Dwa stare testy migracji używają własnej bazy i prawdziwego Alembic UP/DOWN/UP.
   Koszt: zależność od zatwierdzonej izolowanej fixture; bez stałego URL i DROP SCHEMA.
4. Dwa oryginały mają ten sam układ dat. Innych układów dat nie zadeklarowano bez próbki.
   Koszt: nieznany format pozostaje nieobsługiwany, bez zgadywania daty z nazwy pliku.
5. Pominięta przeszła niepowiązana rata i pominięta przyszła powiązana rata blokują zapis.
   Koszt: użytkownik wyjaśnia historię osobno; aplikacja nie usuwa długu lub linków.
6. Historia HTTP powstała w B4, nie w B3. Koszt: późniejsza dostępność UI podczas budowy,
   bez zdublowania endpointów.
7. Preview i receipt korzystają z mechanizmów etapu A. Koszt: wspólny kontrakt;
   kind/hash/owner chronią przed użyciem podglądu innego rodzaju.
8. Przypisanie źródła do kredytu wymaga osobnego potwierdzenia. Koszt: jeden dodatkowy
   krok, ponieważ model umowy nie dowodzi zgodności po samym numerze z PDF.
9. Jeden moduł wystawia routery importu i historii w istniejących ścieżkach.
   Koszt: dwa include/importy, bez nowej domeny lub powielania tras.
10. Początkowo kandydat blokował preview i źródło po aktywacji odmawiało nowego zamiaru.
    Koszt: brak kompletnej ścieżki ponowienia; końcowy review wykrył tę lukę i autor
    dodał jawne porównanie oraz odzyskiwanie receipt. Nie pozostała jako ograniczenie.
11. B5 uzupełnił DTO historii o oryginał i preview o datę bankową. Koszt: addytywne pola
    tylko do odczytu i testy; bez nowego schematu lub księgowania.
12. Workspace harmonogramu jest osobnym komponentem, współdzieli fencing z importerem A.
    Koszt: trzy wewnętrzne eksporty; zachowanie sesji nie jest duplikowane.
13. Backend i frontend mają odrębne zamrożone manifesty, scalone przed commitem.
    Koszt: trzeba potwierdzić także most API i build; nie deklarowano testów całego
    snapshotu na podstawie jednej niezgodnej części.
14. Testy odbiorcze, które od razu przechodzą, pozostały charakterystyką zachowania.
    Koszt: nie stanowią RED; realna luka statusu ma osobne RED→GREEN i regresję A.
15. Review objął B1–B5 i jawny, zamrożony suplement B6 przed końcowym commitem.
    Koszt: poprawki wymagały nowego pełnego gate; autor nie uznał pending za PASS.
16. Wybór kandydata nie promuje ekstrakcji w miejscu. Nowy plan wskazuje wybraną rewizję,
    a równoważny odczyt tylko identyfikuje istniejący receipt. Koszt: nie utworzy się
    drugiego planu przez zmianę parsera; zmienione fakty wymagają zwykłej aktywacji.

Instrukcja użytkownika i operatora: [bank-imports.md](../operations/bank-imports.md).
Prywatne PDF pozostają poza Git; raport zawiera wyłącznie wyniki kontroli,
nie numery umów, rachunków ani kopie harmonogramów użytkownika.
