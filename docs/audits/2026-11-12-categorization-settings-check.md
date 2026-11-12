# Kontrola /settings/finances/categorization

## Zakres i bezpieczeństwo

Audyt na żądanie użytkownika, bez zmiany ustawień, reguł lub transakcji i bez
uruchamiania AI. Produkcja94211b2, frontend z faktycznie wdrożonego pakietu.
Przy wielu aktywnych kontach zatrzymano odczyt danych właściciela do uzyskania
jednoznacznego wskazania konta przez użytkownika. Adresu nie zapisano w raporcie.

Odczyt indywidualnych ustawień wykonano w osobnym procesie backendu w transakcji
`REPEATABLE READ, READ ONLY`, bez lifespan, logowania/sesji użytkownika i bez
wywołania dostawcy. Wywołano te same handlery odczytu, które obsługują stronę.
Po odczycie rollback; brak zmiany liczników transakcji/audytu/receipts/zadań.
Nie obchodzono autoryzacji publicznego serwera — anonimowe API nadal zwraca401.

## Wyniki

- Publiczna trasaSPA i health200; chronione odczyty settings/rules/AIsettings/usage/
  categories401 bez sesji. Browser375/1440 poprawnie przekierowuje na login, bez
  wyjątkówJS, overflow, obcych domen lub żądań mutujących.
- Wszystkie15plików publicznego dist zgodne bajtowo z pakietem94211b2.
- Reguły włączone, kategoria techniczna wskazana i aktywna, poprawna hierarchia
  aktywnych kategorii wydatkowych. Zapisanych reguł:0 (draft/active/paused/retired).
- AI: konfiguracja serwera poprawna, polityka włączona, fingerprint zgodny,
  zgoda konta włączona i efektywna, brak blocked_reason. Pozostałe wywołania:5/dobęUTC
  według aktualnego odczytu. Zadań reguł i sugestii na koncie:0, workerARQready.
- LogiHTTP kategoryzacji z30min: odczyty i zaobserwowane zapisy200, brak5xx;
 401 dotyczą wyłącznie celowych testów braku sesji. Audyt sam nie wykonywał PATCH/POST.
- Świeże frontend18PASS/5plików; workflowreguł4E2EPASS obejmuje ustawienie markera,
  zapis szkicu, podgląd, zgodę/aktywację, wstrzymanie, idempotencyheaders i a11y.
  Wszystkie mutacje tych scenariuszy są syntetyczne, nie produkcyjne.
- Dodatkowe2testy375/1440 odtworzyły stronę z rzeczywiście odczytanymi ustawieniami
  i wdrożonym frontendem. Poprawny marker, stan reguł i AI, komunikaty i blokady
  zapisu bez potwierdzeń, otwieranie edytora i wybór kategorii;0żądań mutujących.
  Prywatny harness wymagał ustawienia ESM i jawnych rozszerzeń importów; błędy jego
  uruchomienia nie dotyczyły aplikacji. Końcowe2PASS.

## Wniosek i ograniczenia

Nie wykryto błędu w sprawdzonym zakresie. Włączone reguły bez żadnej zapisanej
reguły nie przypiszą kategorii automatycznie. Funkcja dotyczy nowych ręcznych
wydatków PLN z kategorią techniczną; nie przegląda historii, importów lub zwrotów.
Propozycja AI zawsze wymaga osobnego przeglądu i zatwierdzenia.

Nie wykonano płatnego wywołania AI ani realnego zapisu na koncie. Nie jest to
potwierdzenie działania zewnętrznego dostawcy end-to-end. Przeglądarka z ustawieniami
konta używała lokalnego replay odczytów, nie przechwyconej lub wygenerowanej sesji.
Kod aplikacji i produkcja bez zmian. Prywatne dane/screeny/logi poza Git:
`/tmp/opencode/categorization-audit-20261112`.
