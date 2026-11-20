# OpenAI settings implementation plan

> **For agentic workers:** Use `executing-plans` or `subagent-driven-development`.

**Goal:** Zarządzanie modelem, kluczem i promptami OpenAI oraz pomiar użycia.
**Spec:** Uzgodniony zakres w rozmowie: tylko OpenAI, konfiguracja per funkcja,
klucze write-only, weryfikacja syntetyczna, wersjonowanie promptu, statystyki;
niezmienne granice danych i potwierdzeń.

## Zadania

- [x] Pionowy przyrost Doradcy: addytywna migracja, właścicielski model i klucz,
  wersjonowanie promptu, test syntetyczny i metryki, UI, bez zmiany ustawień
  pozostałych funkcji.
- [x] Doradca: odróżnić awarię od odpowiedzi, ograniczyć kontekst wysyłany
  do dostawcy i zachować potwierdzanie po stronie serwera.
- [ ] Rozszerzenie na ekstrakcję tekstu i vision, po związaniu rewizji
  ustawień z kolejką i dotychczasowymi limitami/epokami.
- [ ] Rozszerzenie na pozycje paragonów i sugestie kategorii z zachowaniem
  ich odrębnych rezerwacji limitu i ochrony przed zastosowaniem starego wyniku.
- [ ] Pełny przegląd, testy i odbiór lokalny. Migracja produkcyjna i wdrożenie
  poza zakresem; wymagają osobnego przygotowania i zgody.

## Kontrakt pierwszego przyrostu

- `GET /api/advisor/settings`, `PUT .../settings/model`,
  `PUT/DELETE .../settings/credential`, `GET/POST .../settings/prompts`,
  `POST .../settings/test`, `GET .../settings/usage?days=7|30|90`.
- Rozdzielone mutacje ograniczają ryzyko przypadkowego nadpisania innych ustawień.
- Klucz AES-256-GCM związany z właścicielem i wersją formatu. Oddzielny sekret
  instalacji; brak sekretu → odmowa zapisania/odszyfrowania własnego klucza,
  nie ciche użycie klucza serwera. Brak własnego klucza zachowuje konfigurację
  serwerową. Klucz i treści provider errors nie wracają w DTO i logach.
- Każda próba połączenia ma stały syntetyczny input, wywołanie allowlistowanego
  `api.openai.com`, limity i brak narzędzi aplikacji. Statystyki rozróżniają
  próby czatu i testy połączenia. Brak raportu tokenów to nie zero.
- Pełny zakres promptów, logów i wywołań pozostałych usług nie jest częścią
  pierwszego przyrostu; interfejs nie przedstawia go jako dostępnego.
