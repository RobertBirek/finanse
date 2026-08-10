# ADR-008: Poziomy autonomii i human-in-the-loop

**Status:** Accepted
**Date:** 2026-08-10

## Kontekst

System ma oferować różne poziomy autonomii agenta AI, od obserwacji po ograniczoną autonomię. Niektóre operacje (finansowe, bezpieczeństwa) zawsze wymagają zatwierdzenia.

## Decyzja

Definiujemy 5 poziomów autonomii:

| Poziom | Nazwa | Opis |
|--------|-------|------|
| 0 | Obserwacja | Tylko read-only tools |
| 1 | Sugestie | Propozycje bez wykonania |
| 2 | Do zatwierdzenia | Operacje wymagające potwierdzenia użytkownika |
| 3 | Ograniczona autonomia | Automatyczne wykonanie niskiego ryzyka |
| 4 | Agent operacyjny | Pełna autonomia (przyszłość) |

Domyślnie startujemy z poziomem 1-2.

### Klasyfikacja ryzyka operacji:

**Niskie ryzyko (poziom 3):** propozycja kategorii, propozycja zadania, podsumowanie projektu
**Wysokie ryzyko (zawsze poziom 2 max):** usunięcie danych, operacja finansowa, utworzenie zobowiązania, zmiana bezpieczeństwa

## Konsekwencje

- Policy engine sprawdza poziom autonomii przed wykonaniem każdej operacji mutującej
- Operacje wysokiego ryzyka zawsze wymagają jawnego zatwierdzenia
- Audit log rejestruje poziom autonomii przy każdym tool_execution
- Użytkownik może skonfigurować poziom per narzędzie
