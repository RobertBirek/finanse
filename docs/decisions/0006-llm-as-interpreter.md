# ADR-006: LLM jako interpreter, nie kalkulator

**Status:** Accepted
**Date:** 2026-08-10

## Kontekst

System wykorzystuje OpenAI API do interakcji z użytkownikiem przez Doradcę. LLM może generować tekst, ale nie może być źródłem prawdy dla danych finansowych ani harmonogramu.

## Decyzja

Architektura:

```
DANE (PostgreSQL)
    ↓
SILNIKI DOMENOWE (serwisy FastAPI)
    ↓
FAKTY / KPI / SCENARIUSZE
    ↓
ADVISOR (OpenAI + tools)
    ↓
WYJAŚNIENIE / REKOMENDACJA
```

LLM może: interpretować, klasyfikować, podsumowywać, porównywać, proponować, wyjaśniać, wywoływać kontrolowane tools.

LLM nie może: obliczać sald, obliczać KPI, układać harmonogramu bez walidacji, wykonywać dowolnego SQL, wymyślać kwot, samodzielnie wykonywać operacji mutujących.

## Konsekwencje

- Tools są małe, kontrolowane i specyficzne dla domeny (np. `get_financial_summary`, nie `SELECT * FROM transactions`)
- Wszystkie dane liczbowe pochodzą z serwisów domenowych
- Operacje mutujące przechodzą przez: autoryzacja → walidacja → policy engine → audit log → zatwierdzenie
