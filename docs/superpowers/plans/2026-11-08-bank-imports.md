# Import bankowy — Implementation Plan i kolejność dwóch etapów

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Samodzielny, bezpieczny import wyciągów Velo/ING/Revolut oraz kolejnych harmonogramów kredytu bez dublowania historii i spłat.

**Architecture:** Dwa osobno odbieralne rozszerzenia domeny finance, z jednym kontraktem
prywatnych źródeł i trwałego stagingu PostgreSQL. Pierwszy etap dostarcza importer
wyciągów oraz wspólne przygotowanie źródeł; drugi wykorzystuje je do harmonogramów.
Nie powstaje ósma domena ani niezależny mikroserwis.

**Tech Stack:** Python3.12+, FastAPI, SQLAlchemy2 async, PostgreSQL16, Alembic,
obecny worker/Redis, React18, TypeScript, TanStack Query, Tailwind, pytest/vitest/Playwright.

**Spec:** `docs/superpowers/specs/2026-11-08-bank-statements-and-loan-schedule-import-design.md`.

## Global Constraints

- Banki: **Velo, ING i Revolut, bez Citi**.
- Velo PDF rachunku/karty, ING PDF Direct/oszczędnościowe, Revolut CSV PLN/EUR/USD;
  harmonogramy PLN z tekstowych PDF, pierwszy zweryfikowany układ Velo.
- Zdjęcia, skany, Excel i dowolny nierozpoznany układ nie są importerem pierwszej wersji.
- Upload i przygotowanie propozycji nigdy nie tworzą transakcji/postings/sald.
- PostgreSQL jest źródłem prawdy; pliki JSON nie są stanem procesu ani księgą.
- BIGINT w najmniejszej jednostce, min. dwa postings, suma base PLN = 0; transfer != income/expense.
- Istniejące kwoty, daty, salda, mapowania Actual i powiązania spłat nie są nadpisywane.
- Bez automatycznego zakładania kont, księgowania, korekt, OCR, AI lub połączenia do Drive.
- Wszystkie odczyty/mutacje owner-scoped; źródła prywatne, bez danych bankowych w Git.
- Brak zgody na produkcyjną migrację, realny import, merge/push/deploy lub korekty danych.
- Plan opisuje przyszłe testy. Jego zapis nie jest wynikiem testów ani implementacją.

## Review Focus

1. Podobne zakupy i nakładające się eksporty nie mogą ani zniknąć, ani się zdublować — testy etapu A, zadania A4/A8/A9.
2. Brak nogi FX, fee zawarte w kwocie i obcy równoległy import nie mogą utworzyć nierównowagi — A8/A9.
3. Wyciąg z poprawną matematyką, lecz niewłaściwym kontem/ownerem nie uprawnia do commitu — A2/A8/A9.
4. Nowy PDF harmonogramu renumeruje raty i skraca końcówkę, ale nie może zgubić paid/partial/past-unpaid — B2/B3/B4.
5. Wylogowanie/reload/restart workera/utrata odpowiedzi po commit nie mogą ujawnić danych lub powtórzyć księgowania — A3/A10/A11, B5/B6.

## Kolejność wykonania

To roadmapa, nie pojedynczy plan dla task-start. Wykonawca uruchamia osobny ledger/
workspace dla każdego planu etapu; ich nagłówki Task1…TaskN są zgodne ze skryptami
wybranej metody. Oznaczenia A1/B1 to aliasy zależności, nie dodatkowe zadania.

- [ ] **Etap A: wyciągi bankowe** — `2026-11-08-bank-statement-import.md`.
  Dostarcza działające źródła, parsowanie, review i commit dla wszystkich zatwierdzonych
  rodzin wyciągów. Harmonogram nie jest wtedy pustym aktywnym przyciskiem; pojawia się
  dopiero po ukończeniu etapu B. Wspólne modele/kontrakty uwzględniają jego osobny typ.
- [ ] **Etap B: harmonogramy i ich wersje** — `2026-11-08-loan-schedule-import.md`.
  Zależy od zamrożonych kontraktów źródeł/rewizji/receipts etapu A, nie od parserów
  poszczególnych wyciągów ani od ich księgowania. Nie rozpoczynać od drugiego uploadu,
  kolejki lub odrębnego systemu potwierdzania.
- [ ] **Odbiór całości** — osobne testy obu etapów i wspólna końcowa regresja.
  Zakończenie A nie jest twierdzeniem, że dostarczono cały zatwierdzony zakres.

## Przygotowanie wykonania i weryfikacja

- Istniejący worktree `feat/financial-document-workflow` ma lokalne dokumenty Velo/Q7
  i dwa starsze dirty audyty. Nie stage'ować ich przypadkowo, nie resetować/usuwać.
  Użyć using-git-worktrees do weryfikacji izolacji i zapisać BASE oraz stan początkowy.
- Przed implementacją użytkownik wybiera wykonanie i zatwierdza osobne testowe
  PostgreSQL/Docker, jeżeli trzeba je utworzyć. Brak zgody nie oznacza pozwolenia na
  użycie produkcji, wcześniejszego wspólnego test DB ani przypadkowych kontenerów.
  Proponowane zasoby testowe: nowy kontener PostgreSQL16 z własną etykietą i wolumenem,
  wyłącznie loopback 127.0.0.1:55432 (najpierw sprawdzić, czy wolny), finanse_test
  oraz własne scratch DB do Alembic. Bez sieci proxy/produkcyjnych mountów/danych
  i sekretów; cleanup tylko zasobów z zapisanymi ID/OID po osobnej zgodzie obejmującej
  ich utworzenie i usunięcie. Konflikt portu nie jest zgodą na ruszenie innego serwisu.
- Używać `/test`, `/lint`, `/typecheck`, `/migration "opis"` zgodnie z komendami projektu,
  ale z cwd tego worktree i tylko własnym testowym DATABASE_URL. Ścieżki /opt w opisach
  komend są lokalizacją repo bazowego, nie zgodą na wykonanie tam migracji/testów.
- Dla RED/GREEN uruchamiać wskazane selektory pytest/vitest w ramach tych samych
  projektowych narzędzi. Przed każdym commitem wymagane pełne testy/lint/typecheck;
  końcowy odbiór obejmuje również build, pełne E2E i roundtrip prawdziwych migracji.
- Migration ID/filename generuje `/migration`; dopiero jego faktyczny wynik wpisuje
  się do planu/ledgeru. Nie zgadywać rewizji ani nie uruchamiać `/migrate` na produkcji.
  Usunąć z autogeneracji zastany niepowiązany drift; nie zmieniać starych migracji.
  Testy realnego Alembic używają własnej scratch DB i marker migration, bez root
  integration create_all/drop_all uprzedzającego wykonywaną migrację.
- Oryginalne próbki są wyłącznie prywatnym materiałem lokalnego odbioru, nie fixtures
  do commitu. Testy CI korzystają z syntetycznych źródeł zachowujących problematyczny układ.
- Nie wywoływać prawdziwych providerów/banków ani AI w testach; NBP zastąpiony jawnie
  kontrolowanym transportem odpowiedzi, natomiast parsery/liczby/DB/invariants są rzeczywiste.

## Handoff

Pełny projekt został zaakceptowany; ten plan i plany etapów wymagają teraz przeglądu
użytkownika i wyboru sposobu wykonania. Bez tej decyzji nie rozpoczynamy implementacji.
Żaden dokument planu nie rozszerza zgody na produkcyjne operacje.
