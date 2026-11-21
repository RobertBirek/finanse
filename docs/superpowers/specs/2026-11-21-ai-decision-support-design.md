# Doradca: decyzje na podstawie danych i porównanie OpenAI

Zatwierdzony zakres: 1 → 2 → 3 → 5. Oddzielny przyrost dla każdej funkcji,
bez zmian produkcji w ramach implementacji. Nie obejmuje wyjaśniania sugestii
przy dokumentach (punkt 4).

## 1. Co wymaga mojej uwagi?

Na żądanie, w Doradcy: najwyżej trzy sprawy, po jednym wpisie na źródło.
Źródła: zbliżające się lub zaległe płatności z istniejącej prognozy,
dokumenty z listy do decyzji i zadania po terminie. Backend wybiera kolejność
i dostarcza uzasadnienie oraz odnośnik. Na początek zbliżająca się płatność
oznacza najbliższe siedem dni (włącznie z dziś); stosuj datę lokalną z domeny.
Puste listy są normalnym wynikiem. Bez przetwarzania treści dokumentów.

## 2. Symulator „co jeśli?”

Porównaj istniejącą prognozę z jednym hipotetycznym wydatkiem PLN. Formularz
przyjmuje kwotę i datę z przedziału objętego prognozą. Pokaż minimalne saldo
wariantu bazowego i wariantu z wydatkiem, pierwszą datę ujemnego salda
oraz ograniczenia prognozy. Wydatku nie zapisuj. Wersja pierwsza używa
dziennych sald zamknięcia, nie próbuje ustalić kolejności godzinowej. Brak
ujemnego salda nie oznacza gwarancji płynności; wyłączenia i niepełny okres
do wypłaty są widoczne, a saldo już ujemne jest pokazane osobno.

## 3. Wyjaśnienie zmian w wydatkach

Porównaj dwa sąsiednie, równe przedziały zakończonych dni: 14, 30 lub 90 dni
każdy; domyślnie 30. Użyj daty zakupu z takim samym fallbackiem oraz
filtra kont budżetowych zgodnych z raportem finansowym. Podaj sumy netto,
różnicę oraz pozycje o największym wpływie. Wyklucz transfery, uwzględniaj
zwroty zgodnie ze znakiem zapisu, nie licz tych samych postings wielokrotnie.
Jeśli pokażesz powtarzalność, oznacz ją jako sugestię wraz z podstawą, nie jako
potwierdzoną subskrypcję. Informacja o ucięciu listy nie zmienia sum.

## 5. Porównanie modeli i promptów

W ustawieniach Doradcy porównaj ręcznie dwa jawnie wskazane warianty OpenAI
na tych samych trzech wersjonowanych przykładach syntetycznych. Żadnych
rzeczywistych danych użytkownika poza instrukcjami, które świadomie poda
do testu, i wyraźnym ostrzeżeniem, by nie wklejać do nich danych wrażliwych.
Klucz pozostaje w istniejącym serwerowym mechanizmie konfiguracji; bez pola
na klucz benchmarku. Ocenę zgodności ze spodziewaną odpowiedzią liczy kod.
Pokaż czas, tokeny gdy dostawca je raportuje i osobny status błędu każdego
wariantu. Porównanie nie zapisuje ani nie aktywuje konfiguracji; wywołania
liczą się do jawnego limitu i statystyk testów. Bez automatycznych powtórek.

## Wspólne ograniczenia

- Tylko OpenAI i wyłącznie po jawnej akcji. Fakty 1–3 są dostępne bez modelu;
  OpenAI może je zwięźle wyjaśnić, nie zmienia faktów, kolejności ani linków.
- Dane właściciela wyłącznie przez autoryzowane serwisy. Do objaśnienia wysyłaj
  minimalny ustrukturyzowany zestaw faktów, bez kluczy, pełnych opisów czy
  dokumentów. Nie zapisuj promptów lub odpowiedzi tych operacji w logach.
- Bez automatycznych zapisów w domenach, bez dowolnego SQL, bez migracji
  i nowych zależności w pierwszej wersji. Zachowaj istniejące zgody domenowe.
- Testy działają na danych syntetycznych; błędy OpenAI symulowane w testach
  muszą pozostawiać czytelne dane i status, nie udawać sukcesu.
