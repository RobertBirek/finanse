# ADR-005: Projekt jako most między czasem i finansami

**Status:** Accepted
**Date:** 2026-08-10

## Kontekst

System ma pokazywać rentowność projektów łącząc dane z domeny work (czas pracy) i finance (przychody, koszty).

## Decyzja

`Project` jest encją z domeny `work`, która posiada opcjonalne powiązania z domeną `finance`:

- `financial_transactions.project_id` — transakcje przypisane do projektu
- `time_blocks.project_id` — bloki czasu przypisane do projektu (oprócz task_id)

KPI projektu (np. effective_hourly_rate) są obliczane przez serwis domenowy `work`, który odczytuje dane finansowe przez serwis `finance` (nie bezpośrednio z tabel).

## Konsekwencje

- Projekt nie musi mieć finansów (może być czysto zadaniowy)
- Projekt nie musi mieć time blocków
- KPI są wersjonowane jako algorytmy, nie hardkodowane
- Serwis `work` zależy od serwisu `finance` — akceptowalna zależność
