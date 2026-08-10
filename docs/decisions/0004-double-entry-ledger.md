# ADR-004: Double-entry ledger jako rdzeń finansów

**Status:** Accepted
**Date:** 2026-08-10

## Kontekst

System finansowy ma być rzetelnym źródłem prawdy, nie tylko rejestrem wydatków. Wymagane są transfery wewnętrzne, przewalutowania i wielowalutowość.

## Decyzja

Stosujemy uproszczoną księgę podwójnego zapisu:
- Każda transakcja ma min. 2 postings
- Suma postings w walucie bazowej = 0 (invariant)
- Kwoty w `BIGINT` (najmniejsza jednostka: grosze, centy)
- Każdy posting przechowuje: source_amount, source_currency, base_amount_pln, fx_rate

## Alternatywy odrzucone

- **Pojedyncza tabela przychodów/wydatków:** Nie obsługuje transferów, przewalutowań, wielowalutowości
- **Pełna księga GAAP/IFRS:** Overkill dla personal finance
- **Actual Budget API:** Chcemy własny system, nie zależność od zewnętrznego

## Konsekwencje

- Frontend może pokazywać prosty formularz (kwota, kategoria, konto), backend tworzy odpowiednie postings
- Transfer wewnętrzny: 2 postings (debit z konta A, credit na konto B), type=transfer, nie income/expense
- Przewalutowanie: 2 postings z rzeczywistym kursem (np. PLN→EUR po 4.30)
- Prowizja: osobny posting kosztowy
- Testy property-based: suma postings = 0, transfery nie są income/expense
