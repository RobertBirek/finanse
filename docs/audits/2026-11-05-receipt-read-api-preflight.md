# 4B — preflight pierwszej próby API: STOP przed wysyłką

## Zgoda i wynik

2026-11-05 user odpowiedział „tak” na pytanie „Czy zatwierdzasz wykonanie jednej próby
na tych warunkach?” po przedstawieniu zakresu c6d687d. Zgoda obejmuje jedną syntetyczną
próbę `gpt-6.1-terra`, wyłącznie po wiarygodnym potwierdzeniu górnego kosztu≤2PLN.
Brak wiarygodnej wyceny oznacza STOP, nie zgodę na szacowanie na podstawie podobnego modelu.

**Wynik: BLOCKED w preflight. Liczba requestów próby do OpenAI:0.** Nie pobrano/odczytano
klucza, nie utworzono harnessu ani obrazu, nie wykonano GET model ani generacji.
Zgoda na pojedynczy płatny call nie została wykorzystana; nie ma zużycia tej próby do rozliczenia.
Nie jest to negatywny wynik odczytu — do odczytu w ogóle nie doszło.

## Potwierdzone źródła publiczne

Sprawdzono publiczną dokumentację przez Exa, bez autoryzacji kluczem aplikacji:

1. https://developers.openai.com/api/docs/models/gpt-6.1-terra
   - Exact modelID `gpt-6.1-terra`, text/image input, Responses i Structured Outputs.
   - `reasoning.effort=none` obsługiwane.
   - Standard input1USD/1M tokens, output5USD/1M tokens; cached input0,05USD/1M.
   - Osobne dopłaty/warunki cache writes, long context i trybów; nie wolno ignorować
     taryfy konkretnego uruchomienia ani utożsamiać outputlimit z całym kosztem.
2. https://developers.openai.com/api/docs/pricing
   - Tabela Standard potwierdza dla tego exactID stawki1/5USD przy short context.
3. https://openai.com/index/introducing-gpt-6-1-terra/
   - Potwierdza standardowe1USD input/5USD output, nie podaje reguły image tokenization.
4. https://developers.openai.com/api/docs/guides/images-vision
   - Obraz jest billable input; pominięte `detail` oznacza `auto` (tak działa klient4B).
   - Opublikowana tabela sizing/multiplier obejmuje m.in. `gpt-6-astra` i modele5.6,
     ale w sprawdzonej treści nie określa zachowania/mnożnika dla `gpt-6.1-terra`.
   - Nie przeniesiono mnożnika1,2 ani limitu patches z innego modelu na Terra6.1.
5. https://developers.openai.com/api/docs/guides/latest-model
   - Sekcja Terra odsyła do ogólnego przewodnika image inputs; nie uzupełnia brakującej
     reguły naliczania dla tego exactID. Dodatkowe wyszukiwanie exactID nie dostarczyło jej.

Ogólna strona marketingowa https://openai.com/api/pricing/ pokazywała starsze rodziny5.6;
nie zastosowano jej stawek do6.1. Brak wpisu w sprawdzonej dokumentacji NIE oznacza
braku obsługi obrazów lub braku publicznej reguły gdziekolwiek — oznacza brak
potwierdzonej podstawy do wymaganego ograniczenia kosztu w tej próbie.

## Przyczyna zatrzymania

Output≤2048 daje granicę części wyjściowej, ale nie wszystkich kosztów. Bez potwierdzonej
tokenizacji/wyceny obrazu nie da się rzetelnie zakończyć wyceny pełnego wejścia+output
i porównać jej z2PLN. Nie zastąpiono jej intuicyjnym „mały paragon będzie tani”.
Nie przedstawiono końcowej wycenyUSD/PLN ani gwarancji kosztu. Nie uruchamiano requestu
tylko po to, by dowiedzieć się z usage, ile obraz kosztował.

## Co pozwoli wznowić

Potwierdzona, adekwatna do tego modelu i konta reguła tokenizacji/rozliczania obrazu,
aktualna taryfa oraz konserwatywna pełna wycena z udokumentowanym przeliczeniemUSD→PLN,
mieszcząca się w2PLN. Jeżeli zmieni się model, limit kosztu lub zakres, potrzebna jest
nowa zgoda. Nie przełączono samodzielnie modelu ani nie podniesiono budżetu.

## Zachowany stan

Receipt_items purpose w aplikacji nadal OFF. Bez DB/Redis/uploadów/importów/księgowania,
prywatnych dokumentów, produkcji, merge lub push. Źródła produktu i wcześniejsze proofy
pozostają bez zmian; w tej sesji jedynie publiczny research/preflight i dokumentacja.
