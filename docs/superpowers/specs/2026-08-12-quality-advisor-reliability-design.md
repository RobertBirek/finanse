# Jakość i niezawodność Doradcy — specyfikacja

Data: 2026-08-12  
Status: approved

## Cel

Spłacić bieżący dług jakościowy bez dodawania nowej funkcjonalności biznesowej:
usunąć błędy Ruff i mypy, zwiększyć pokrycie krytycznej pętli tool-calling,
uruchamiać testy integracyjne z PostgreSQL oraz zapewnić odświeżanie statusu
mutacji Doradcy po potwierdzeniu lub odrzuceniu.

## Zakres i decyzje

### 1. Lint i typowanie

- Uruchomić Ruff z konfiguracją projektu i wykorzystać bezpieczne automatyczne
  poprawki.
- Pozostałe błędy poprawić ręcznie, bez wyłączania reguł tylko po to, aby
  uzyskać zielony wynik.
- Uzupełnić adnotacje typów oraz zawęzić typy odpowiedzi tam, gdzie jest to
  potrzebne do poprawnego wyniku mypy.
- Nie wykonywać niezwiązanych refaktorów.

### 2. Testy Doradcy

Dodać testy jednostkowe i serwisowe z mockowanym klientem LLM. Testy muszą
obejmować:

- odpowiedź LLM bez tool calla;
- wykonanie narzędzia odczytowego i przekazanie jego wyniku do kolejnej
  odpowiedzi LLM;
- narzędzie nieznane, niepoprawne argumenty JSON i wyjątek executora;
- zatrzymanie po `MAX_TOOL_ITERATIONS`;
- narzędzie Level 2 zapisane jako `pending_confirmation`, bez wykonania mutacji;
- confirm wykonujący narzędzie dokładnie raz i zapisujący audit log;
- deny zmieniający status bez wykonania narzędzia;
- ochronę przed ponownym confirm/deny już rozstrzygniętej egzekucji;
- izolację użytkownika przy dostępie do tool execution.

Mocki nie będą wykonywać połączeń do zewnętrznego LLM ani wymagać sekretów.
Testy zachowają istniejący invariant finansowy: każda utworzona transakcja ma
co najmniej dwa postingi, a ich suma wynosi zero.

### 3. Testowa baza PostgreSQL

- Fixture testowej bazy będzie korzystać z `TEST_DATABASE_URL`, z obecnym
  lokalnym adresem jako wartością domyślną.
- Dodać dokumentowany sposób uruchomienia izolowanego PostgreSQL w Dockerze
  dla testów, bez publikowania portów produkcyjnej bazy.
- Testy integracyjne mają być wykrywalne i uruchamialne standardowym
  `pytest`; brak dostępnej bazy ma zakończyć testy czytelnym komunikatem,
  a nie błędem importu aplikacji.
- Fixture nadal tworzy i sprząta schemat testowy per test; nie wolno dotykać
  produkcyjnej bazy ani wykonywać destrukcyjnych operacji poza testową bazą.

### 4. Odświeżanie statusu w frontendzie

- Po wysłaniu wiadomości frontend odświeża wiadomości aktywnej rozmowy, gdy
  występuje `pending_confirmation`.
- Polling używa istniejących hooków TanStack Query i zatrzymuje się, gdy nie ma
  oczekujących egzekucji lub gdy rozmowa nie jest aktywna.
- Confirm i deny unieważniają cache wiadomości oraz konwersacji, aby status i
  wynik były widoczne bez ręcznego przeładowania.
- Przycisk jest blokowany podczas żądania, a błędy są obsługiwane bez utraty
  istniejącego bannera.
- Nie wprowadzamy SSE ani WebSocketów.

## Przepływ danych

1. `send_message` zapisuje wiadomość użytkownika.
2. Mockowany lub rzeczywisty LLM zwraca odpowiedź albo tool call.
3. Registry wykonuje narzędzie Level 0 albo zapisuje Level 2 jako
   `pending_confirmation`.
4. Backend zwraca wiadomość wraz z eager-loaded `tool_executions`.
5. Frontend pokazuje banner i okresowo pobiera aktualny stan.
6. Confirm/deny sprawdza właściciela i status, zmienia egzekucję, zapisuje
   audit log dla operacji człowieka i unieważnia cache UI.

## Obsługa błędów i bezpieczeństwo

- Nieznane narzędzie, błędny JSON i wyjątki executora są reprezentowane jako
  kontrolowany wynik `error`, bez ujawniania tracebacka użytkownikowi.
- Confirm/deny dla nieistniejącej egzekucji lub cudzej rozmowy zwraca 404.
- Confirm/deny dla statusu innego niż `pending_confirmation` nie wykonuje
  ponownie mutacji i zwraca błąd konfliktu.
- Wszystkie mutacje przechodzą przez istniejące serwisy domenowe i audit log;
  LLM nie otrzymuje bezpośredniego dostępu do bazy.

## Weryfikacja

Po implementacji uruchomić:

1. `make lint`
2. `make typecheck`
3. `make test`

Dodatkowo uruchomić testy integracyjne z PostgreSQL w Dockerze oraz sprawdzić,
że frontendowy polling nie wykonuje żądań po zakończeniu lub odrzuceniu
egzekucji.

## Poza zakresem

- Nowe narzędzia Doradcy i nowe domenowe funkcje biznesowe.
- SSE, WebSockety i streaming odpowiedzi LLM.
- Zmiana modelu autonomii lub polityki zatwierdzeń.
- Migracje produkcyjnej bazy danych.
