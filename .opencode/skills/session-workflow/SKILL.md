---
name: session-workflow
description: Use when starting or ending a work session in the Personal Advisor project — initialize session context by reading the four project docs, or update CHANGELOG/TASKS/JOURNAL after completing work.
---

# Session Workflow (Personal Advisor)

## Overview

Personal Advisor wymaga zdyscyplinowanego workflow sesji: inicjalizacja kontekstu na starcie, aktualizacja dokumentacji na końcu. Bez tego sesje tracą kontekst, a backlog się rozjeżdża.

## Inicjalizacja sesji (START)

Przed JAKĄKOLWIEK pracą przeczytaj w tej kolejności:

1. `/opt/finanse/AGENTS.md` — konstytucja projektu
2. `/opt/finanse/docs/CHANGELOG.md` — historia zmian
3. `/opt/finanse/docs/TASKS.md` — backlog + statusy
4. `/opt/finanse/docs/JOURNAL.md` — kontekst ostatnich sesji

Nie zaczynaj pracy, dopóki nie znasz stanu z tych plików.

## Zakończenie sesji (END)

Po zakończeniu pracy, przed finalnym commitem, zaktualizuj:

1. `docs/CHANGELOG.md` — wpis `[wersja] — data` z sekcjami Added/Changed/Fixed
2. `docs/TASKS.md` — statusy zadań (`[x]` done, `[~]` in progress, `[-]` cancelled)
3. `docs/JOURNAL.md` — wpis sesji na górze: cel, co zrobiono, decyzje techniczne, znane problemy, następna sesja

## Komendy i narzędzia

- Komendy opencode: `/test`, `/lint`, `/typecheck`, `/migrate`, `/migration "opis"`, `/deploy`, `/docs`
- LSP: pyright (Python), typescript-language-server (TS)
- MCP EXA: `web_search_exa` / `web_fetch_exa`
- Testy przed commitem: `make test` (pytest backend + vitest frontend)

## Konwencje commitów

`feat` / `fix` / `docs` / `refactor` / `test` / `chore` + opis po polsku.
