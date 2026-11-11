# Import i wersje harmonogramów kredytów — Implementation Plan (etap B)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Importować tekstowe PDF harmonogramów PLN, pokazywać różnice i jawnie
aktywować nowy przyszły zakres bez zmiany księgi, UUID rat i istniejących spłat.

**Architecture:** Wspólne prywatne źródła, parse revisions, worker i receipts pochodzą
z etapu A. Nowe modele w finance zapisują niezmienne wersje oraz membership/snapshot
rat. Wspólna projekcja aktywnych rat wyklucza zastąpioną przyszłość, zachowując
powiązane i historyczne raty. Aktywacja jest osobnym poleceniem bez wywołania księgi.

**Tech Stack:** Python3.12+, FastAPI, SQLAlchemy2 async/PostgreSQL16/Alembic,
pypdf, ARQ, React18/TypeScript/TanStack Query/Tailwind, pytest/vitest/Playwright.

**Spec:** `docs/superpowers/specs/2026-11-08-bank-statements-and-loan-schedule-import-design.md`.
**Prerequisite:** ukończony i odebrany etap A,
`docs/superpowers/plans/2026-11-08-bank-statement-import.md`; wspólne typy/HTTP opisane tam.

## Global Constraints

- Banki: **Velo, ING i Revolut, bez Citi**; harmonogramy PLN z tekstowych PDF,
  pierwszy zweryfikowany układ Velo. Inny układ pozostaje unsupported do czasu próbek/testów.
- Zdjęcia, skany, Excel i dowolny nierozpoznany układ nie są importerem pierwszej wersji.
- Upload i przygotowanie propozycji nigdy nie tworzą transakcji/postings/sald.
- Sam harmonogram nie tworzy postingów, kosztów, salda długu, nadpłat, prognoz ani „zapłacono”.
- Istniejące kwoty, daty, salda, mapowania Actual i powiązania spłat nie są nadpisywane.
- Wszystkie powiązane raty (także częściowo opłacone), ich UUID i linki pozostają niezmienione.
- Numer bankowy jest pochodzeniem w ramach wersji, nie tożsamością raty.
- PostgreSQL jest źródłem prawdy; pliki JSON nie są stanem procesu ani księgą.
- BIGINT w groszach, typowane strict ints; suma raty=kapitał+odsetki+opłaty.
- Tylko własne istniejące aktywne konta PLN, różne role debt/payment, bez profilu karty
  i bez drugiej umowy dla tego samego konta zadłużenia. Kwoty API <=9_007_199_254_740_991.
- Brak migracyjnego backfillu, nowych harmonogramów lub rewrite Q7 przy deployu.
- Brak merge/push/deploy/produkcyjnej migracji/importu/korekt księgi bez osobnej zgody.
- Stosować testowe bezpieczeństwo i komendy `/test`, `/lint`, `/typecheck`, `/migration`
  z roadmapy; żaden test lub migracja nie może użyć produkcji ani cudzego test DB.

## Review Focus

1. Bank renumeruje raty od1: istniejąca spłata ma nadal ten sam installment UUID — B2/B3/B4.
2. Nadpłata skraca plan, a stara końcówka jest późniejsza niż ostatnia nowa rata:
  zastąpić cały zadeklarowany kompletny przyszły ogon, nie pozostawić podwójnego długu — B3/B4.
3. Częściowo pokryta rata, historyczna niepokryta rata i opuszczona linked rata:
  brak zmiany, fałszywego paid lub cichego usunięcia — B3/B4/B6.
4. Powiązanie/odpięcie/edycja ręczna podczas podglądu: aktywacja musi wykryć konflikt,
  bez deadlocku lub przekierowania wpłaty — B3/B4.
5. Ponowny ten sam plik, nowy parser lub zagubiona odpowiedź: ta sama wersja/receipt,
  nie nowe raty; stare Q7 bez zmian przed pierwszym świadomym importem — B1/B4/B5/B6.

## Mapa plików i zależności

W skróconych sygnaturach DB `db:AsyncSession`, `owner:UUID`, wszystkie ID:UUID;
entrypointy wykonujące I/O są async z pełnymi type hints w implementacji.

- `finance/loan_schedule_models.py`: zatwierdzone wersje i niezmienne membership snapshots.
- `finance/loan_schedule_projection.py`: jeden predicate/projection dla aktywnych rat.
- `finance/loan_schedule_{schemas,diff,preview,commands,router}.py`: API, porównanie,
  zamrożone decyzje i idempotentna aktywacja; żadnego INSERT do finansowych postings.
- `finance/imports/parsers/velo_schedule.py`: czysty parser do ParsedSchedule z A1.
- `finance/{models,loans,loan_schemas,loan_router}.py`: addytywne pola/guardy i kompatybilne odczyty.
- Frontend: `api/loanScheduleImports.ts`, `components/finance/imports/{ScheduleTarget,
  ScheduleDiff,ScheduleConfirmation}.tsx`, `components/finance/loans/ScheduleHistory.tsx`;
  reuse stron Import i istniejącej FinanceLoans.
- Testy: `backend/tests/test_finance/test_loan_schedule_import/`, unit/frontend/E2E;
  prywatne źródła pozostają poza Git. Nie budować drugiego uploadu, kolejki i receipt engine.

B1→B2/B3, następnie B4→B5→B6. B2 konsumuje A1–A3, B4 konsumuje A9 commands
i source preview binding. Po rozpoczęciu B nie zmieniać tych interfejsów potajemnie;
potrzebną zmianę zapisać w obu planach i pokryć regresją A.

## Zamrożone reguły projekcji i targetu

- `LoanAgreement.active_schedule_revision_id:UUID|None` default NULL;
  `LoanInstallment.superseded_by_revision_id:UUID|None` default NULL.
  Istniejące `(loan_id,number)` oraz wszystkie ID/linki pozostają bez zmian.
- `LoanScheduleRevision`: owner,loan_id,ordinal,kind `manual_baseline|bank_import`,
  state `active|superseded`, previous_revision_id, source_revision_id nullable tylko
  baseline, receipt_id, bank_effective_date, activated_on, cutover_date, created_at.
- `LoanScheduleMembership`: owner,revision_id,installment_id,bank_number nullable dla
  manual baseline, source_row_id nullable tylko baseline, snapshot daty/3składowych/
  bankowego salda. Unique revision+installment i bank_number w danej wersji.
  Snapshot nie jest księgowym saldem; zachowuje stary plan, nawet gdy ręczna rata bazowa
  była później kontrolowanie zmieniona. FK RESTRICT i owner checks.
- `active_installment_predicate()->ColumnElement[bool]`:
  `LoanInstallment.superseded_by_revision_id IS NULL`. Żadna powiązana rata nie może
  dostać superseded; przeszłe niepokryte też nie. Dodatkowy guard broni tych invariantów.
- `cutover_date=max(application_today_at_activation, bank_effective_date)`;
  aktywacja innego dnia niż zatwierdzony preview wymaga nowego podglądu.
  Brak jednoznacznej effective_date/pełnej tabeli blokuje, nie zgadujemy jej z nazwy pliku.
- Kompletny pozostały harmonogram zastępuje cały niepowiązany przyszły ogon od cutover,
  również stare raty po nowym terminie końcowym. Niepełny zakres blokuje aktywację.
- Tożsamość raty do reuse: jednoznaczna zgodność due_date i trzech składników;
  numer bankowy nie uczestniczy w tożsamości. Kilka kandydatów nie jest automatycznie
  scalanych. Nowe raty otrzymują wewnętrzny number=max(number w całej umowie)+1 pod
  blokadą, a bank_number pozostaje osobnym polem źródła. Stare numery nigdy nie są przepisywane.
- Linked/partial przed cutover, pominięte przez nowszy PDF: zachowane w historii.
  Linked/partial wewnątrz zastępowanego ogona muszą być jednoznacznie obecne i zgodne;
  brak/zmiana blokuje całą aktywację, bez arbitralnego carry-forward niepokrytej reszty.
- Historia past-unpaid nie znika. Nowy PDF nie aktualizuje jej kwot; konflikt lub
  brak tożsamości historycznych wierszy jest widoczny i blokuje domyślne zastępowanie.
  Import nie jest narzędziem naprawy historycznych rat.
- Pierwszy import do pustej nowej umowy może wprowadzić pełny bankowy plan także
  z historycznymi datami, ale wszystkie raty zaczynają jako niepowiązane.
- Pierwszy import istniejącego identycznego harmonogramu (np. ręcznie zapisanego Q7)
  reuse'uje dotychczasowe installment IDs. Tworzy dowód/wersję, nie drugi zestaw rat.

### Task 1: Addytywne wersje i migracja bez backfillu Q7 (B1)

**Files:** Create `finance/{loan_schedule_models,loan_schedule_schemas,
loan_schedule_projection}.py`; Modify `finance/{models,loan_schemas}.py`,
`backend/migrations/env.py`; Test `test_loan_schedule_import/{conftest,factories,
test_models,test_migration}.py`.
Migration `/migration "loan_schedule_revisions"`: następca rzeczywistego head A,
po generacji freeze `MIGRATION_PATH`/revision; pojedynczy head, bez zgadywania ID.

**Interfaces:** Produces powyższe modele, predicate,
`ScheduleTarget(loan_id:UUID|None,new_loan:LoanCreate|None)` z exactly-one,
`SchedulePreviewRequest(expected_version:int,source_id:UUID,target:ScheduleTarget,
acknowledgements:list[str])`,
`ScheduleActivateRequest(preview_id:UUID,request_hash:str)` oraz
`ScheduleCommitResult(receipt_id,batch_id,request_hash,loan_id,revision_id,reused_ids,new_ids,
superseded_ids,ledger_changed:Literal[False])`.
Test helper B `financial_history_snapshot(db)->dict[str,str]` hashuje konta,
transactions/postings, Actual mappings i payment links, ale NIE planowe raty, które
to polecenie może jawnie dodawać/archiwizować. Stare raty/ID/składniki są dodatkowo
porównywane osobno. Nie zmieniać szerszego `ledger_snapshot` etapu A.

Wykonawcze doprecyzowanie B1 (2026-11-10): membership ma również `loan_id` jako
kontekst FK do rewizji i raty. Addytywne unique owner keys na LoanAgreement,
LoanInstallment, FinanceCommandReceipt oraz ImportRevision/ImportRow umożliwiają
FK owner/loan, bez zmiany identyfikatorów, DTO i istniejących relacji etapu A.
Migracja obejmuje te constrainty oprócz dwóch tabel i dwóch nullable pointerów.

- [ ] **Step 1: Write failing tests.** Model check/owner FK/ordinal, projected defaults
  NULL i prawdziwy Alembic roundtrip na seeded legacy loan+paid+partial+past-unpaid.
  ```python
  @pytest.mark.integration
  async def test_migration_does_not_create_schedule_versions(legacy_snapshot, migrate):
      await migrate.upgrade_new_head()
      assert await migrate.count("loan_schedule_revisions") == 0
      assert await migrate.original_columns_snapshot() == legacy_snapshot
  ```
  `migrate` test helper uruchamia realny Alembic tylko na osobnym zatwierdzonym test DB;
  nie zastępuje tego Base.metadata.create_all z pytest fixture.
- [ ] **Step 2: Verify RED.** Focus `test_models.py test_migration.py`.
  Expected: brak modeli/migracji, nie skipped DB lub automatyczne tworzenie pustych wersji.
- [ ] **Step 3: Implement additive schema.** Dwie nowe tabele i dwa nullable FK,
  snapshot values BIGINT, zachowanie wszystkich starych constraint/ID. Bez UPDATE
  tworzącego baseline dla każdego kredytu. Downgrade odmawia przy nowych wersjach/
  superseded/provenance zamiast usuwać dane. Bazę wersji tworzy dopiero jawne polecenie B4.
  Cykl LoanAgreement.active_revision↔Revision.loan ma nazwany FK/use_alter; integration
  create_all/drop_all zachowuje działanie. Test migration używa owned_migration_database
  z A1 i marker migration, nie integration metadata.create_all.
  Partial unique index loan_id WHERE state='active' zapewnia jedną aktywną wersję;
  pierwszą manual_baseline można utworzyć już jako superseded w tej samej jawnej
  transakcji, przed dodaniem active bank_import, bez chwilowego łamania unique.
- [ ] **Step 4: Verify GREEN.** Te same testy: upgrade/downgrade/upgrade rozszerzenia
  bez jego danych, retencja A i starych danych, odmowa niepustego downgrade.
  Expected: PASS, zero zmienionych starych kolumn/ID i zero utworzonych rat/linków.
- [ ] **Step 5: Commit.** `/lint`, `/typecheck`, `/test`; `feat: dodaj wersje harmonogramów bez zmiany historii`.

### Task 2: Bankowy PDF harmonogramu i pełna walidacja tabeli (B2)

**Files:** Create `imports/parsers/velo_schedule.py`;
Modify `imports/parsers/registry.py`; Test `test_loan_schedule_import/test_parser.py`,
syntetyczne `fixtures/velo_schedule_{initial,revised,truncated,renumbered}.pdf`.

**Interfaces:** Consumes ParserInput/ParsedSchedule/ScheduleRow z A1 i bounded pypdf A2.
Produces `parse_velo_schedule(data:ParserInput)->ParsedSchedule`; registry obsługuje
`kind='loan_schedule'` tylko dla jawnie wspieranego Velo layout.

- [ ] **Step 1: Write failing tests.** Co najmniej dwa oryginalne układy dat wersji
  na syntetycznych PDF, strony/stopy, polskie separatory, kontynuacja tabeli i
  renumeracja od1. Wiersze=3składniki, kapitał przechodzi między saldami.
  ```python
  def test_renumbered_pdf_preserves_bank_number_not_internal_identity(revised_pdf):
      parsed = parse_velo_schedule(revised_pdf)
      assert parsed.rows[0].bank_number == 1
      assert parsed.currency == "PLN" and parsed.complete_tail
      assert all(c.result == "passed" for c in parsed.checks if c.required)
  ```
  Dodać brak strony/kolumny/saldo, kwotę rozbitą na linie, fee absent vs zero,
  brak effective_date, jawny końcowy residual/balloon, unknown bank/Citi/image/encrypted.
- [ ] **Step 2: Verify RED.** Focus `test_parser.py` + registry A. Expected: unsupported
  Velo schedule przed implementacją; brak mockowania wyniku parse w testach ekstrakcji.
- [ ] **Step 3: Implement deterministic parser.** Odczytać wszystkie wiersze/numery/
  terminy i oznaczenia końca planu, jawne skutki fee=0, bank_effective_date z treści.
  `complete_tail=True` tylko dla kompletnej pozostałej tabeli potwierdzonej strukturą
  dokumentu/wierszami/sumami, nie dlatego, że ostatnia przeczytana linia wygląda poprawnie.
  Residual nie wymusza automatycznie zera, ale musi być jawną kontrolowaną treścią źródła.
  Odczyt nie wylicza stopy procentowej ani wykonanych spłat i nie tworzy umowy.
- [ ] **Step 4: Verify GREEN.** Focus + read-only odbiór dwóch prywatnych PDF harmonogramu,
  źródłowe sumy i pełny łańcuch wszystkich rat, bez księgi. Expected: PASS lub jawny
  unsupported/blocked dla niewspieranego układu, żadnych prywatnych danych w fixtures Git.
- [ ] **Step 5: Commit.** Bramki projektu; `feat: odczytuj bankowe PDF harmonogramów Velo`.

### Task 3: Porównanie, aktywna projekcja i ochrona powiązanych rat (B3)

**Files:** Create `finance/loan_schedule_diff.py`;
Modify `finance/{loans,loan_schedule_projection,loan_schemas,loan_router}.py`;
Test `test_loan_schedule_import/{test_diff,test_projection,test_manual_races}.py`,
regresje `test_loans.py`, `test_loan_contracts.py`.

**Interfaces:** Produces `load_schedule_state(db,owner,loan_id,*,lock:bool)->ScheduleState`,
`diff_schedule(state:ScheduleState,parsed:ParsedSchedule,*,today:date)->ScheduleDiff`.
`ScheduleState(loan_id,active_revision_id,installments,payment_links,fingerprint)`;
`ScheduleDiff(cutover_date,reused_ids,new_rows,superseded_ids,retained_history_ids,
conflicts,warnings,fingerprint)`. Fingerprint obejmuje daty/kwoty/ID/linki i aktualny
plan, nie tylko updated_at samej umowy. `ScheduleConflict(code,row_key,installment_ids)`.

- [ ] **Step 1: Write failing tests.** Nowe sumy nie zawierają superseded przyszłości;
  paid/partial/past-unpaid zachowane; incoming renumbering nie zmienia ID spłaty.
  ```python
  def test_shorter_complete_plan_replaces_entire_old_future_tail(state, shorter_plan):
      diff = diff_schedule(state, shorter_plan, today=date(2026, 11, 8))
      assert state.old_last_installment_id in diff.superseded_ids
      assert state.paid_installment_id not in diff.superseded_ids
      assert not diff.conflicts
  ```
  Testy: pierwszy identyczny import59syntetycznych rat+1link reuse59/create0;
  przyszła linked rata nieobecna w nowym ogonie→blocked; bank renumber1 vs stare internal
  number różne; document effective date przeszła vs activation today; płatność dodana
  po preview zmienia fingerprint; ręczny update/link/unlink nie mają odwrotnego lock order.
- [ ] **Step 2: Verify RED.** Focus trzy nowe pliki + istniejące loan tests.
  Expected: aktualny `_detail()` błędnie sumuje wszystkie raty lub brak diff.
- [ ] **Step 3: Implement single active projection.** `_detail`, get/list, candidates,
  link/update/delete używają wspólnego predicate i fresh owner checks. History endpoint
  czyta membership snapshot, nie aktywną listę udającą pełną historię. Wszystkie
  mutacje planu/linków: owner mutation mutex→loan row→installment→transaction/link,
  accounts sorted tylko tam gdzie potrzebne, bez odwrócenia względem istniejących guards.
  Dopasowanie jednoznacznej daty+składników, nie numeru; niejednoznaczność conflict.
  Legacy bez active_revision zachowuje dotychczasową ręczną obsługę. Po bankowej
  aktywacji nie edytować/usuwać źródłowych rat w miejscu: istniejący endpoint zwraca
 409 z instrukcją importu nowej wersji; superseded nie przyjmuje nowego linku. Ręczne
  tworzenie rat w bank-managed planie również409, bez ukrytego rozjechania wersji.
  Linki retained historical/paid pozostają addressable po UUID, a unlink nie gubi raty.
  Pozostałe consumers transakcji/dates/bills/correction/provenance zachowują swoje guardy.
- [ ] **Step 4: Verify GREEN.** Focus + loan/transaction/bill/card guards. Expected:
  zgodne stare API przed aktywacją, brak podwójnych sum, superseded409, brak zmiany księgi.
- [ ] **Step 5: Commit.** Bramki projektu; `feat: porównuj wersje i zachowuj aktywny zakres rat`.

### Task 4: Preview i idempotentna aktywacja harmonogramu (B4)

**Files:** Create `finance/{loan_schedule_preview,loan_schedule_commands,
loan_schedule_router}.py`; Modify `finance/import_router.py`;
Test `test_loan_schedule_import/{test_preview,test_activation,test_races,test_routes}.py`.

**Interfaces:** Consumes A1–A3/A9, B1–B3. Produces
`prepare_schedule_preview(db,owner,batch_id,data:SchedulePreviewRequest)->SchedulePreviewDTO`,
`activate_schedule(db,owner,batch_id,data:ScheduleActivateRequest,key:str)->ScheduleCommitResult`,
`list_schedule_revisions(db,owner,loan_id)->list[ScheduleRevisionDTO]`,
`get_schedule_revision(db,owner,loan_id,revision_id)->ScheduleRevisionDetailDTO|None`.
`SchedulePreviewDTO(id,batch_id,request_hash,source_revision_id,target,cutover_date,
loan_fingerprint,diff,ledger_effect:Literal['none'])`. Preview bind jak A8, dodatkowo
target/diff/fingerprint/today; klient nie podaje gotowych LoanInstallment ORM rows.

HTTP: `POST /finance/imports/{batch_id}/schedule-preview`,
`POST /finance/imports/{batch_id}/activate-schedule`, odzyskanie receipt wspólnym
`GET /finance/imports/{batch_id}/commands/{key}`; historia
`GET /finance/loans/{loan_id}/schedule-revisions` i `.../{revision_id}`.
Osobne action receipt `loan_schedule.activate`, bez użycia bank-import commit dla ledger.

- [ ] **Step 1: Write failing tests.** Import do pustej nowej umowy tylko po jawnej
  decyzji target; existing target nigdy nie tworzy drugiej umowy. Nowy preview ma
  ledger_effect=none; aktywacja tworzy wersję/reuse/new/archive i żadnych financial rows.
  ```python
  async def test_activation_keeps_linked_ids_and_ledger(db_session, owner, confirmed_schedule):
      before = await financial_history_snapshot(db_session)
      linked = await linked_installment_ids(db_session)
      result = await activate_schedule(db_session, owner.id,
          confirmed_schedule.batch_id, confirmed_schedule.request, "schedule-intent")
      assert result.ledger_changed is False
      assert await financial_history_snapshot(db_session) == before
      assert await linked_installment_ids(db_session) == linked
  ```
  Snapshot finansowy obejmuje konta/transaction/postings/Actual/linki,
  NIE nowe planowe LoanInstallment; old installment values/IDs porównywane osobno.
  Dodać lost response/replay same result, changed key payload409, concurrent link
  przed aktywacją409, dwa concurrent imports, inny dzień aktywacji409, źródło archived,
  bank/konto/loanowner mismatch404/422, karta/loan account konflikt, newID numer overflow.
- [ ] **Step 2: Verify RED.** Focus cztery nowe pliki. Expected: brak routes/command,
  nie brak odpowiedniej klasycznej pożyczki albo próbne mutacje produkcji.
- [ ] **Step 3: Implement one command transaction.** Command-key lock→owner mutation
  mutex→batch/source/preview→loan→accounts sorted→installments/payment links,
  zgodnie z B3 i istniejącą kolejnością create_loan. Wersja target i dzień muszą być
  niezmienione; po blokadach ponownie obliczyć diff/fingerprint/checks przed zapisem.
  Dla new target create_loan przez istniejący serwis dopiero po walidacji preview;
  unikalność konta/owner/currency/profile sprawdzana w tej samej transakcji.
  Baseline istniejących rat zapisać dopiero przy pierwszym jawnym poleceniu, snapshot
  wszystkich ich wartości, bez przepisywania starych rekordów. Reuse zgodnych IDs,
  archive wyłącznie niespowiązany ogon przez superseded_by_revision_id, nowe raty
  numerować ponad istniejącym max pod lockiem, zachować bank_number w membership.
  Zmiana active pointer/stanów revision, audit, receipt i rezultat atomowo. Nie wywoływać
  create_transaction, link_loan_payment, forecast, generatora odsetek lub korekty salda.
  Replay zwraca receipt przed ponowną oceną aktualnego dnia; nowy intent dla przeterminowanego
  preview wymaga nowego preview. Tak samo rozróżnić utraconą odpowiedź od błędu przed commit.
- [ ] **Step 4: Verify GREEN.** Rzeczywiste oddzielne sesje PG dla wyścigów; identyczny
  import existing59/1link nie zmienia starych wierszy. Expected: PASS, jedyna active
  revision, żadne przeniesienie spłaty, zero postings, nowe sumy bez starego ogona.
- [ ] **Step 5: Commit.** Bramki projektu; `feat: aktywuj import harmonogramu z ochroną istniejących spłat`.

### Task 5: Wybór kredytu, porównanie i historia wersji w aplikacji (B5)

**Files:** Create `frontend/src/api/loanScheduleImports.ts`,
`components/finance/imports/{ScheduleTarget,ScheduleDiff,ScheduleConfirmation}.tsx`,
`components/finance/loans/ScheduleHistory.tsx`; Modify `api/{bankImports,loans}.ts`,
`pages/{FinanceImports,FinanceImportReview,FinanceLoans}.tsx`;
Test nowe komponenty/hooks i istniejące FinanceLoans tests.

**Interfaces:** Consumes B4 DTO/routes. Hooks `useSchedulePreview`,
`useActivateSchedule`, `useLoanScheduleRevisions`, `useLoanScheduleRevision`.
Rozszerzenia LoanDetail: `active_schedule_revision_id?:string|null`,
LoanInstallment: `bank_number?:number|null`, `schedule_revision_id?:string|null`;
legacy fields/number/UUID pozostają kompatybilne. Historia to oddzielny odczyt.

Doprecyzowanie interfejsu B4→B5 (2026-11-11): historia potrzebuje owner-scoped
`document_id/original_name/batch_id` (nullable dla manual_baseline), a preview
`bank_effective_date` odrębnej od cutover. Są to wyłącznie addytywne odczytowe DTO,
bez nowego modelu/migracji/księgowania. Test źródłowego powiązania RED przed zmianą.
Workspace UI wydzielony do komponentu, aby nie mieszać decyzji księgi i aktywacji planu.

- [ ] **Step 1: Write failing tests.** URL kredytu preselectuje target bez utworzenia
  umowy; nowy kredyt wymaga jawnego wyboru dwóch kont; upload bez aktywacji.
  ```tsx
  it("does not infer paid status from a schedule PDF", async () => {
    renderScheduleImport();
    await uploadSchedulePdf();
    expect(screen.getByText("Harmonogram nie księguje spłat")).toBeVisible();
    expect(scheduleApi.activate).not.toHaveBeenCalled();
  });
  ```
  Dodać bank_number vs internal number, skipped old future w aktywnej sumie, linked
  conflict blocked, past-unpaid preserved, baseline/revised original view, aktywacja
  invalidated po409, receipt recovery i stale actor/inactive accounts.
- [ ] **Step 2: Verify RED.** Frontend focus `loanScheduleImports.test.ts`,
  `ScheduleDiff.test.tsx`, `FinanceLoans.test.tsx` i rozszerzone import tests.
  Expected: brak harmonogramowego target/diff, nie niespodziewane realne API.
- [ ] **Step 3: Implement existing-style extension.** Włącz typ „Harmonogram kredytu”
  w wspólnym Import, plus przycisk „Importuj harmonogram” w Kredyty i pożyczki.
  Potwierdzenie mówi jawnie: aktualizuje plan, nie księguje, zachowuje powiązania.
  Pokaż datę obowiązywania/cutover, retained/new/superseded/conflict oraz oryginały.
  Numer bankowy opisany jako numer w wersji, nie nowy identyfikator wpłaty.
  Historia osobno od aktywnej listy, bez archiwalnych kwot w bieżących sumach.
  Query keys owner+generation i ten sam retry key, brak danych w localStorage.
  Invalidacja loans/imports/history; nie modyfikować sald w cache i prognozy.
- [ ] **Step 4: Verify GREEN.** Focus + wszystkie unit tests loans/imports i build;
  mobile/desktop i dark/light zachowują czytelne kwoty/konflikty. Expected: PASS.
- [ ] **Step 5: Commit.** Bramki projektu; `feat: dodaj import i porównanie bankowych harmonogramów`.

### Task 6: Odbiór całości, retencja i instrukcja użytkownika (B6)

**Files:** Create `test_loan_schedule_import/test_acceptance.py`,
`frontend/e2e/loan-schedule-import.spec.ts`,
`docs/audits/2026-11-08-loan-schedule-import-local.md`;
Modify `docs/operations/bank-imports.md`, CHANGELOG/TASKS/JOURNAL i syntetyczne E2E fixtures.

**Interfaces:** Consumes A+B; potwierdza wszystkie kryteria spec, bez nowych kontraktów.

- [ ] **Step 1: Write failing acceptance tests.** Prawdziwy syntetyczny PDF przez
  worker/durable DB → diff → activation → nowa sesja → active/history/list/payment
  candidates. Zmiana powiązania między preview/activation daje409 i zachowuje stan.
  Drugi identyczny plik nie dodaje wersji/rat; shorter/renumbered nie zmienia paid IDs.
  Pełne receipt/source metadata i brak zapisów w tabelach księgi.
- [ ] **Step 2: Verify RED.** Focus acceptance oraz build+
  `npm run test:e2e -- loan-schedule-import.spec.ts`. Expected: odtworzona luka
  integracyjna, nie brak fixture, nie kontakt z produkcją.
- [ ] **Step 3: Close only reproduced gaps.** Zaktualizować runbook obu etapów:
  supported files, bank-managed plan vs manual, blocked linked conflict, bank numbering,
  missing effective date, receipt recovery, history i brak kosztów/nadpłat od planu.
  Aktualizacja instrukcji nie zmienia Q7 lub istniejących transakcji.
- [ ] **Step 4: Full verification.** `/test`, `/lint`, `/typecheck`, frontend build,
  pełne E2E, oba realne Alembic roundtripy z retencją danych62+stageA, prywatne PDF
  acceptance read-only bez danych w repo. Nowy test nie może przechodzić przez skip DB.
  Zamrozić manifest source/rezultatów, screenshots obejrzeć, jeden końcowy całościowy
  review zgodnie z wybraną metodą; poprawki Important/Critical wyłącznie RED→GREEN.
- [ ] **Step 5: Commit and stop at release boundary.**
  `docs: zapisz odbiór importu harmonogramów i ochrony historii`; raportuje testy,
  ograniczenia i zakończenie całego zaakceptowanego zakresu A+B. Produkcyjny deploy,
  migracja, import prawdziwych danych, main/push/cleanup cudzych danych nie są zgodą z tego planu.

## Self-review planu

- Spec8 wszystkie podpunkty: B1–B5; source/no-ledger/job safeguards z A1–A3 są reuse,
  nie drugi proces. First-new-loan i same-current-plan import mają osobne testy.
- Projektowana bezpieczna aktualizacja zastępuje tylko cały udokumentowany przyszły
  ogon; zachowuje przeszłe niepokryte i wszystkie linked, a niedające się bezpiecznie
  rozstrzygnąć konflikty blokuje. Shortened maturity i dzień aktywacji mają konkretne testy.
- Jedyna projekcja aktywności konsumowana przez wszystkie siedem bezpośrednich query
  w loans.py; zewnętrzne guards zachowują niezmienne IDs/linki. Nie dodajemy tej funkcji
  potajemnie do forecast/reporting, które nie są obecnie konsumentami planu.
- Baseline dopiero przy jawnej aktywacji, nie w migracji; modele/nazwy/DTO i endpointy
  B1/B3/B4 są zgodne z konsumentami B5. Żadnych brakujących parserów innych banków.
- To plan przyszłego wykonania. Testy/komendy powyżej nie były uruchamiane przy pisaniu planu.
