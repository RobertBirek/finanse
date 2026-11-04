# Kategoryzacja, pozycje paragonów i daty zakupów — zatwierdzony kierunek lokalny

## Zgoda i zakres

W rozmowie użytkownik uzgodnił kategorie/podkategorie proponowane przez LLM,
kategoryzację operacji z wyciągu bez paragonu, podział pozycji jednego paragonu
między kategorie, wcześniejsze nieskategoryzowane transakcje oraz oddzielne daty
zakupu/księgowania. Po przedstawieniu sześciu etapów i przełączeniu z Plan do
agenta wykonawczego odpowiedział „ok, działaj dalej”. To zgoda na lokalną pracę
iteracyjną, nie wdrożenie, produkcyjną migrację, kosztowne realne AI lub zmianę historii.

## Uzgodniony kontrakt produktu

- Ręczne przypisania mają pierwszeństwo. Istniejące kategorie wybierane z użyciem
  zatwierdzonych reguł, źródeł dokumentowych i dopiero w pozostałych przypadkach LLM.
- Doprecyzowanie usera2026-11-04: hybryda. Autozapis tylko z wcześniej zatwierdzonej
  reguły na nowej nieskategoryzowanej transakcji; LLM wyłącznie propozycje do ludzkiego
  przeglądu, także zatwierdzenie wybranej partii. Pewność modelu nigdy nie wystarcza do
  zapisu. Reguły nie mogą nadpisywać ręcznych przypisań ani uruchamiać historii wstecz.
- Nowe kategorie/podkategorie wymagają zatwierdzenia. Nie duplikować podobnych nazw
  ani samodzielnie scalać/przenosić istniejącego drzewa. Proponowany limit dwóch
  poziomów dotyczy nowych propozycji agenta, nie zastanego ręcznego drzewa.
- Pojedynczy wydatek z wyciągu może otrzymać przybliżoną kategorię na podstawie
  kontrahenta/opisu (Kaufland to wskazówka, nie dowód zawartości koszyka).
- Po dołączeniu paragonu agent może zaproponować podział według pozycji, np.100PLN
  jako80PLN spożywka/20PLN chemia. Każdy podział użytkownik zatwierdza przed
  zastosowaniem w finansach. Jedna płatność pozostaje jedną płatnością.
- Kwoty liczy i waliduje backend w jednostkach najmniejszych; suma podziału musi
  być zgodna co do grosza. Rabaty i nieczytelne pozycje nie upoważniają do zgadywania
  lub dopisywania różnic. LLM nie oblicza sald i nie wykonuje SQL.
- Zakup w piątek i księgowanie w poniedziałek mogą dotyczyć tej samej płatności.
  Zachować obie daty i ich pochodzenie; nie przesuwać źródłowej daty bankowej.
- Budżety/analiza zakupów według daty zakupu, uzgodnienie banku według księgowania.
  Gdy zakupowa data nieznana, jawnie oznaczony fallback do dotychczasowej daty;
  nie wyprowadzać historycznej daty księgowania z samego istnienia legacy.date.
- Dopasowanie uwzględnia kwotę/walutę/kontrahenta/konto/odstęp dat; wieloznaczne
  dopasowania i różnice kwoty do sprawdzenia. LLM nie zmienia typu transakcji.
- Wcześniejsze nieskategoryzowane transakcje objęte zakresem, ale tylko osobnym
  uruchomieniem partiami z podglądem/zatwierdzeniem. Konfiguracja jednoznacznie
  wskazuje kategorię techniczną „bez kategorii”; nazwa „Pozostałe” nie wystarcza.
- Transfery/przewalutowania nie stają się wydatkami. Nie tworzyć drugiego wydatku
  przez dodanie paragonu ani przez wprowadzenie drugiej daty.
- Pełny split/rozliczenie w pierwszej wersji PLN, zgodnie z obecnym ograniczeniem
  alokacji dokumentów. FX split i różnice kwot nie są niejawnie aprobowane.

## Etapy i obecna jednostka wykonania

1. Daty zakupów/księgowania, proweniencja, raporty/budżety, bezpieczna ręczna korekta.
2. Dedykowane polecenie zmiany kategorii/splitu, zachowujące ID strony kontowej,
   alokacje płatności, kwoty i invariant księgi; audyt i ochrona przed starą decyzją.
3. Trwałe propozycje/reguły/ograniczone zadania klasyfikacji, walidowane Structured
   Outputs, kontrola kosztu/powtórzeń i zatwierdzanie nowych kategorii.
4. Pozycje dokumentu, rabaty, kontrola sum i zatwierdzany podział.
5. Kandydaci płatności z rozdzielonymi datami, lepsze wyjaśnienia i brak duplikatów.
6. Jawnie uruchamiane partie historii, przegląd propozycji i finalny UX/odbiór.

Etapy1/2 oraz3A/3B ukończono lokalnie, bez wdrożenia; odbiór3B8a9560f/0347e58/0cd6bb1.
Aktualna jednostka to projekt etapu4 (`2026-11-04-receipt-item-categorization-design.md`)
z historią produktów sklepu i wyszukiwaną listą kategorii. Rekomendowane4A ręczne/4B odczyt
wymaga akceptacji użytkownika; etapy4–6 nie są gotowe po samych datach/splitach/propozycjach.
Dalsza realizacja opiera się na tym kontrakcie;
kolejne wydania wymagają własnego odbioru i osobnej zgody.

## Nienaruszalne ograniczenia

- Źródło prawdy PostgreSQL; kategorie księgowe nie mają równoległego alternatywnego
  źródła sum w raportach. Pliki JSON wyłącznie schematy/propozycje/proofy, nie ledger.
- Zachować oryginały, archiwum2f, historię review/jobs/usage/audit, daty źródłowe,
  identyfikatory postings i powiązania finansowe. Zero produkcyjnych mutacji tej sesji.
- Żadnego automatycznego przepisania dawnych ręcznych/importowanych kategorii/dat.
- Owner scope, CSRF, sesje, idempotencja i sprawdzanie wersji także dla nowych akcji.
- Istniejące Actual history pins i odzyskiwanie danych pozostają kompatybilne;
  additive schema i rollout/rollback muszą uwzględniać nowe metadane przed wydaniem.
- Utrzymać istniejący stack/modularny monolit, bez nowych usług lub pakietów runtime.
- Unrelated Velo/Q7, hostmain, działający release8106532 i inne aplikacje nietknięte.
