# ADR-001: Personal Advisor jako nadrzędny produkt

**Status:** Accepted
**Date:** 2026-08-10

## Kontekst

System ma łączyć finanse, zarządzanie czasem, projekty, dokumenty i AI w jednym produkcie. Istniejąca aplikacja Actual (finanse) działa pod domeną `finanse.birek.online`.

## Decyzja

Budujemy jeden produkt — **Personal Advisor** — który zastępuje Actual. Nie tworzymy osobnych aplikacji dla każdej domeny, ani nie integrujemy osobnych narzędzi zewnętrznych jako głównych komponentów.

Personal Advisor wykorzystuje wyspecjalizowane silniki domenowe (finance, work, inbox, advisor) działające wewnątrz jednego modularnego monolitu.

## Konsekwencje

- Jeden frontend (React SPA), jeden backend (FastAPI), jedna baza (PostgreSQL)
- Domeny są oddzielone na poziomie pakietów backendu, ale współdzielą infrastrukturę
- Actual działa tymczasowo obok, zostanie wyłączony po migracji danych
- UI nie wygląda jak ERP — ma prostą nawigację (Dzisiaj, Inbox, Projekty, Finanse, Doradca)
