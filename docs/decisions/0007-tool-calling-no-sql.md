# ADR-007: Tool calling bez dowolnego SQL

**Status:** Accepted
**Date:** 2026-08-10

## Kontekst

Doradca AI potrzebuje dostępu do danych użytkownika, ale nie może mieć nieograniczonego dostępu do bazy danych.

## Decyzja

Implementujemy kontrolowane narzędzia aplikacyjne zdefiniowane jako funkcje Python:

- Każde narzędzie ma jasno określony scope (np. `get_financial_summary(user_id, period)`)
- Narzędzia wołają serwisy domenowe, nie wykonują SQL bezpośrednio
- Narzędzia mutujące przechodzą przez policy engine z poziomami autonomii 0-4
- Wszystkie wywołania narzędzi są logowane w `tool_executions` i `audit_events`

Przykładowe narzędzia:
- **Finance:** get_financial_summary, get_accounts, get_upcoming_obligations
- **Work:** get_projects, get_today_schedule, get_tasks
- **Operations:** create_task, classify_inbox_item (mutujące, wymagają zatwierdzenia)

## Konsekwencje

- OpenAI widzi tylko wyniki narzędzi, nigdy surowe dane z bazy
- Łatwe dodawanie nowych narzędzi bez zmiany architektury
- Audit log pokazuje każde wywołanie narzędzia z argumentami i wynikiem
- Bezpieczeństwo: prompt injection nie może wykonać narzędzia spoza listy
