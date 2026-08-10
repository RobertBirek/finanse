# ADR-003: Oddzielenie domen finance/work/advisor

**Status:** Accepted
**Date:** 2026-08-10

## Kontekst

System łączy finanse, zarządzanie pracą i AI. Te domeny mają różne cykle życia, różne invarianty i różne wymagania dotyczące integralności.

## Decyzja

Utrzymujemy ścisłe oddzielenie trzech głównych domen:

```
task != calendar_event != time_block != transaction != document != decision
```

- **Finance:** Double-entry ledger, invarianty bilansowe, audytowalność
- **Work:** Projekty, zadania, time blocking, estymacje
- **Advisor:** Konwersacje AI, tool calling, polityki autonomii

Encje mogą być powiązane (np. transakcja → projekt, zadanie → time_block) ale nie są sztucznie scalane.

## Konsekwencje

- Każda domena może ewoluować niezależnie
- Testy domenowe są odizolowane
- Nie można "uprościć" księgi przez wrzucenie transakcji do tasków
- Project działa jako most między domenami (finanse i praca) przez powiązania FK
