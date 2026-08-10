# PRD — Personal Advisor

Product Requirement Document dla osobistego systemu operacyjnego.

## Wizja

> Pomóż użytkownikowi podejmować dobre decyzje dotyczące czasu, pieniędzy, pracy, projektów i celów.

Personal Advisor nie jest zbiorem osobnych aplikacji (finanse, task manager, kalendarz). To jeden system z wyspecjalizowanymi silnikami domenowymi działającymi w tle.

## Kluczowe pytania, na które system odpowiada

```
Co powinienem zrobić teraz?
Na co przeznaczyć dzisiaj czas?
Który projekt wymaga uwagi?
Czy mam czas na nowe zlecenie?
Czy stać mnie na zakup X?
Ile naprawdę zarabiam na projekcie?
Gdzie tracę czas / pieniądze?
Czy działania są zgodne z celami?
```

## Zasoby użytkownika

System rozumie cztery podstawowe zasoby:

- **CZAS** — taski, bloki, kalendarz, estymaty
- **PIENIĄDZE** — księga, konta, transakcje, cash-flow
- **UWAGA / ENERGIA** — priorytety, kontekst, focus (późniejsza faza)
- **KAPITAŁ / MAJĄTEK** — aktywa, zobowiązania (późniejsza faza)

## Nawigacja

Podstawowa:
- Dzisiaj
- Inbox
- Projekty
- Kalendarz
- Finanse
- Doradca

Zaawansowana (Więcej):
- Cele
- Majątek
- Dokumenty
- Analizy
- Ustawienia

## MVP — Iteracja 1

### A. Fundaments

- Auth (rejestracja, logowanie, sesje HttpOnly cookies)
- Double-entry ledger (konta, kategorie, transakcje, postings)
- Projekty z zadaniami
- Inbox z klasyfikacją
- Doradca z read-only tools

### B. Ekran Dzisiaj

- Plan czasowy (dzisiejsze time blocki)
- Najważniejsze zadania
- Zobowiązania finansowe
- Szybkie podsumowanie

### C. Inbox

- Przechwycenie tekstu/notatki
- AI proponuje klasyfikację (task/project/transaction/reference)
- Użytkownik zatwierdza lub poprawia
- Przekształcenie w encję domenową

### D. Projekty

- CRUD projektów
- Zadania per projekt
- Rejestracja czasu (ręczna)
- Podstawowe finanse projektu (przychody, koszty)

### E. Finanse

- Konta (PLN, EUR, USD)
- Transakcje z podwójnym zapisem
- Transfery wewnętrzne
- Przewalutowania
- Kategorie
- Podstawowe KPI

### F. Doradca

- Czat z AI
- Narzędzia read-only: get_financial_summary, get_today_schedule, get_projects
- Poziom autonomii: 1-2

## Iteracja 2 (planned)

- Import danych z Actual
- Integracja Stirling PDF (OCR dokumentów)
- Sygnały personalizacji
- Zaawansowany scheduler (deterministyczny)
- Pamięć semantyczna (pgvector)

## Iteracja 3+ (planned)

- Cele i śledzenie postępu
- Majątek i inwestycje
- Automatyzacje
- OpenClaw jako warstwa wykonawcza
- Integracje zewnętrzne
