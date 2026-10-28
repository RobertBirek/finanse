# Loan Schedule Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans or superpowers:subagent-driven-development. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Pierwszy slice Q7: plan kapitał/odsetki/opłaty i ręczne powiązanie
istniejącego transferu z ratą, bez księgowania lub poprawiania historii.
**Architecture:** Trzy modele relacyjne w finance; metadane powiązań wskazują
niezmienne postingi jako źródło rzeczywistej kwoty. Statusy wyliczane, nie przełączane.
**Tech Stack:** PostgreSQL/SQLAlchemy/Alembic/FastAPI/Pydantic, React/TS/TanStack Query.
**Spec:** `docs/superpowers/specs/2026-10-27-loan-schedule-design.md`.

## Global Constraints

- Implementacja bez produkcyjnego upgrade/importu.28.10 użytkownik osobno zatwierdził
  main/push/deploy i addytywną migrację; nadal bez importu harmonogramu i korekty odsetek.
- BIGINT grosze, pierwszy slice PLN. Bez drugiego licznika kapitału poza księgą.
- Link nie tworzy transakcji i nie rozpoznaje historycznych odsetek jako kosztu.
- Bez automatycznego dopisywania rat do wspólnej prognozy; bez podwójnego naliczania.

## Review Focus

- Równoczesne linki nie przekraczają raty i nie wykorzystują ponownie jednego przelewu.
- Płatność połączona z ratą nie może stać się pending lub zostać usunięta poza workflow.
- Capability waluty nie pozwala rozjechać kont pustej umowy; wyścig create vs PATCH.
- UI nie utożsamia planu ani starego salda księgowego z uzgodnionym kapitałem.
- Migracja dodaje wyłącznie nowe tabele; brak bootstrapu danych użytkownika.

### Task 1: Modele, migracja i serwis

**Files:** `backend/app/finance/models.py`, nowe `loan_schemas.py`, `loans.py`,
`backend/migrations/versions/<revision>_loan_schedules.py`,
`backend/tests/test_finance/test_loans.py` i `test_loan_migration.py`.

**Interfaces:** `create_loan(db,user_id,data) -> LoanAgreement`,
`get_loans(db,user_id) -> list[LoanResponse]`,
`get_loan(db,user_id,loan_id) -> LoanDetailResponse | None`,
`create_loan_installment(db,user_id,loan_id,data) -> LoanInstallment`,
`update_loan_installment(db,user_id,loan_id,installment_id,data) -> LoanInstallment | None`,
`delete_loan_installment(...) -> bool`,
`link_loan_payment(db,user_id,loan_id,installment_id,transaction_id) -> LoanDetailResponse | None`,
`unlink_loan_payment(...,link_id) -> bool`,
`get_loan_payment_candidates(...,limit,offset) -> paginated result`.

- [ ] RED: tabele/umowa/rata/ownership/kwoty zgodne ze spec i syntetycznym przykładem.
- [x] GREEN: modele i schematy, addytywna migracja i grupowe odczyty serwisowe.
- [ ] RED: partial/paid, idempotencja, overpayment/duplicate409, pending/future/foreign.
- [x] GREEN: link wyłącznie poprawnego transferu; loan row lock następnie transaction
  row lock; pełna walidacja i świeże odczyty przed przypisaniem. Unlink metadanych.
- [ ] Test dwóch sesji: różne płatności do tej samej raty, ten sam przelew do różnych rat.
- [x] Test before/after pełnych rekordów ledger i raportów: niezmienione.

### Task 2: Guardy i router

**Files:** `backend/app/finance/{queries,entities,transactions,router}.py`, nowe
`loan_router.py`, `backend/tests/test_finance/test_loans.py`.

**Interfaces:** `/finance/loans` GET/POST, `/loans/{id}` GET/PATCH(name/is_active),
`/loans/{id}/installments` POST, `/installments/{iid}` PATCH/DELETE,
`/installments/{iid}/payments` POST, `/payments/{link_id}` DELETE,
`/installments/{iid}/payment-candidates` GET (limit/offset).

- [ ] RED: owner404, validation422, history409, atomicitet, stare endpointy bez regresji.
- [x] GREEN: mały router dołączony do finance/router, bez commit w serwisach.
- [ ] RED: waluta obu kont umowy zablokowana, edycja daty/pending/deletion powiązanego
  transferu409; opis dozwolony i po unlink operacja znów dostępna.
- [x] GREEN: blokady Account i Transaction przed sprawdzeniem referencji; get_db zarządza
  transakcją. SQL FK RESTRICT dodatkowo chroni przed przypadkowym usunięciem.
- [x] Migracja na izolowanej bazie: stary wiersz/kolumny bez zmian i jeden Alembic head.

### Task 3: UI

**Files:** `frontend/src/api/loans.ts`, `pages/FinanceLoans.tsx`,
`components/finance/loans/*`, routing i settings navigation oraz testy tych plików.

**Interfaces:** API odpowiedzi z Task1; walidacja kwot przez istniejący parser PLN,
bez floating-point do obliczeń groszy, możliwość wprowadzenia0 dla składników.

- [ ] RED: lista/error/empty nie mylą się; formularze umowy i rat; pełny syntetyczny przykład.
- [x] GREEN: komponenty i dostępne etykiety/komunikaty, brak prywatnych danych w fixtures.
- [ ] RED: link/unlink bez tworzenia transakcji, błąd409 zostawia wybór do poprawy,
  pending/nieprawidłowi kandydaci niewybieralni, rozróżnienie planu i salda księgowego.
- [x] GREEN: TanStack hooks i właściwa invalidacja loan keys; historia finansów bez mutacji.
- [x] E2E desktop/mobile, dwa motywy/axe i negatywne scenariusze na fikcyjnym API.

### Task 4: Gate i dokumentacja

- [x] Pełne pytest na lokalnej finanse_test, Ruff/mypy, Vitest/ESLint/tsc/build/E2E.
- [ ] Świeży review całości, ważne uwagi naprawione TDD, dokumentacja trzech plików.
- [ ] Małe commity w gałęzi, bez merge/push/migracji/deployu produkcyjnego.

## Progress

- [x] Potwierdzenie użytkownika, że dostarczony harmonogram dotyczy Q7.
- [x] Analiza ograniczeń istniejących harmonogramów i księgi; brak zmian aplikacji.
- [x] Builder check: doprecyzowano blokady transakcji/loan, FK/unikalność/409 przy
  usuwaniu konta, zakres kwot API i DB, obie role waluty i paginację kandydatów.
- [x] Zgoda: wcześniejsze „ok, działaj” dla Q7 + potwierdzenie przypisania dokumentu.
  Builder nie wskazał brakujących decyzji użytkownika dla tego bezksięgowego slice.
- Wykonanie: backend i frontend równolegle, rozdzielone własności plików;
  koordynator integruje E2E, pełny gate, dokumentację i końcowe review.
- Gałąź `feat/loan-schedule` od0d52f9d. Backend ses_e8167b723ffe7QD7wTHBpF56C0,
  frontend ses_e81677873ffeIWDNbBIgKE1rys — brak commitów i pełnego gate na tym etapie.
- Koordynator: syntetyczne `frontend/e2e/loan-fixtures.ts` obsługuje odczyty/link/unlink;
  bazowe fixtures nadal odrzucają jakąkolwiek mutację ledger.
- Review frontendu (ses_e8161a244ffeKtzpPBLI3NNBtF): wykryto stan formularza
  przechodzący między umowami, brak resetu po zapisie, aktywne przyciski kandydata
  podczas linkowania i niewidoczne błędy mutacji. Wykonawca poprawił w pierwszej
  rundzie; raport 44 testy targeted (41 wcześniejszych +3 regresje), lint/tsc PASS.
  Oczekuje weryfikacji koordynatora i końcowego review.
- E2E: pierwszy start nie dotarł do aplikacji (brak oczekiwanego binarium Playwright).
  Ponowienie używa istniejącego `/usr/bin/google-chrome` przez przewidziane
  `PLAYWRIGHT_CHROMIUM_EXECUTABLE`; bez instalacji i bez zmian konfiguracji produkcji.
- Review poprawek frontendu potwierdził rozwiązanie wszystkich ważnych uwag.
  Braki testów pending/paginacji/odpięcia uzupełniono scenariuszem E2E, dodatkowo
  E2E formularza sprawdza trzy dokładne kwoty i reset po sukcesie.
- Pierwszy wykonany E2E:6 PASS,2 FAIL (axe kontrast jasnego motywu).
  Lokalne klasy statusu i panelu poprawione, pełny build/E2E uruchomiony ponownie.
  Pełne Vitest243/243, ESLint/tsc PASS przed zmianą wyłącznie tych klas.
- Ponowiony pełny frontend gate po zmianie klas: Vitest243/243, ESLint,
  TypeScript i git diff --check PASS (sh_17ea79107001dTcHGBUA7YQLcL).
- Pełne build/E2E po poprawkach: build PASS,59 E2E PASS +1 dotychczasowy celowy
  skip desktop;12 przebiegów Q7 obejmuje także nowe regresje pending/paginacji/unlink.
-28.10 koordynator przejął backend po limicie podagenta. Targeted32 PASS po RED→GREEN:
  strict integers/blank name/no-op PATCH/owner404/sanitized conflict/stale ORM/unlink lock.
  Migracja zachowuje stare konta/postingi, nie tworzy danych użytkownika.
- Użytkownik zatwierdził teraz main/push/deploy; pełny gate i procedura wydania w toku.
- Pierwszy pełny gate841/1fail wymusił naprawę serializacji PATCH transakcji:
  selectinload razem z odświeżeniem po lock;2 nowe regresje RED→GREEN,
  loan+integrity47 PASS, Ruff/mypy PASS. Pełne ponowienie przed integracją.
- Końcowy pełny backend844 PASS,8 deselected,2 znane warningi; osobno proxy5 PASS.
  Testy samego przelewu w różnych ratach są sekwencyjne +DB UNIQUE; współbieżne
  testy sprawdzają limit pokrycia i link vs zmiana/usunięcie transakcji, nie każdą
  kombinację dwóch umów. Niezależny review protokołu blokad nie wykrył blokad.
