# Wyciągi Velo/ING/Revolut — Implementation Plan (etap A)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Działający import wszystkich zatwierdzonych rodzin wyciągów: plik → trwały odczyt → review → jawny, idempotentny zapis przez księgę.

**Architecture:** Pakiet `app.finance.imports` przechowuje źródła, niezmienne rewizje,
decyzje, preview i pochodzenie transakcji w PostgreSQL. Dokumenty zapewniają prywatne
oryginały; ARQ dostarcza tylko trwałe intencje odczytu. Commit jest osobnym poleceniem
użytkownika, nigdy działaniem workera. Nie powstaje ósma domena.

**Tech Stack:** Istniejące Python3.12+/FastAPI/SQLAlchemy/PostgreSQL/Alembic/ARQ,
`pypdf>=6,<7`, stdlib `csv`/`Decimal`, React18/TypeScript/TanStack Query/Tailwind.

**Spec:** `docs/superpowers/specs/2026-11-08-bank-statements-and-loan-schedule-import-design.md`.
**Roadmap i środowisko:** `docs/superpowers/plans/2026-11-08-bank-imports.md`.

## Global Constraints

- Banki: **Velo, ING i Revolut, bez Citi**. Velo PDF rachunku/karty; ING PDF Direct/
  oszczędnościowe; Revolut CSV PLN/EUR/USD. Inne układy są jawnie unsupported.
- Zdjęcia, skany, Excel i dowolny nierozpoznany układ nie są importerem pierwszej wersji.
- Upload i przygotowanie propozycji nigdy nie tworzą transakcji/postings/sald.
- PostgreSQL jest źródłem prawdy; pliki JSON nie są stanem procesu ani księgą.
- BIGINT w najmniejszej jednostce, min. dwa postings, suma base PLN = 0; transfer != income/expense.
- Istniejące kwoty, daty, salda, mapowania Actual i powiązania spłat nie są nadpisywane.
- Wszystkie odczyty/mutacje owner-scoped; źródła prywatne, bez danych bankowych w Git.
- Brak automatycznego zakładania kont, księgowania, korekt, OCR, AI lub integracji Drive.
- Kurs NBP dla booking_date, istniejący weekend fallback, jawny ręczny kurs przy braku
  notowania; Decimal/ROUND_HALF_EVEN. Quote utrwalony w preview, bez fetch podczas commit.
- Parametry parserów i zasobów konfigurowalne; kwoty API <=9_007_199_254_740_991.
- Pełne bramki `/test`, `/lint`, `/typecheck` według roadmapy. RED/GREEN ma konkretne
  selektory poniżej; działają wyłącznie w zatwierdzonym izolowanym środowisku testowym.
- Nie używać testów runtime-skipped jako dowodu integracji/migracji. Nie używać produkcji.
- Nie stage'ować zastanych dokumentów/audytów. Brak merge/push/deploy/realnego importu.
- Poprawne prywatne próbki zatwierdzonych układów muszą rzeczywiście dać ready i
  poprawne wiersze/sumy. Samo zwrócenie blocked dla wszystkiego nie jest odbiorem
  parsera. Błędne/unsupported fixtures mają być blokowane. Jeśli poprawny rzeczywisty
  układ wymaga zgadywania, to blocker wydania lub jawna zmiana zakresu z użytkownikiem.

## Review Focus

1. Prawdziwe podobne zakupy vs overlap bez bankowego ID: zachować liczność i wymagać decyzji — A4/A8/A9.
2. Fee w kwocie, zwrot wydatku i FX EUR↔USD: nie podwajać kosztu ani wymyślać nogi/kursu — A4/A8/A9.
3. Poprawny matematycznie plik przypięty do złego właściciela/konta: odrzucić zapis — A2/A8/A9.
4. Osierocony worker, reparse zatwierdzonego źródła lub usunięty oryginał: bez utraty pochodzenia — A2/A3/A9.
5. Zmiana aktora, wyceny lub danych po preview i utrata odpowiedzi commit: bez wycieku i powtórki — A8/A9/A10/A11.

## Mapa plików i zależności

- `backend/app/finance/imports/{models,contracts,schemas,service,queries,errors}.py`:
  trwały model, granica typów, owner-scoped odczyty i błędy z kodem.
- `imports/{storage,jobs,worker,pdf_text}.py`: bezpieczne źródła i odczyt bez OCR/AI.
- `imports/parsers/{registry,money,revolut_csv,velo_account,velo_card,ing}.py`:
  czyste parsery wersjonowanych układów, bez DB/HTTP/księgi.
- `imports/{matching,decisions,valuation,preview,commands,commit,provenance}.py`:
  decyzje użytkownika, wycena, zamrożony podgląd, idempotencja i zapis finansowy.
- `backend/app/finance/import_router.py`: HTTP adapter; include w `finance/router.py`.
- `documents/import_storage.py`, `documents/{models,schemas,lifecycle}.py`: oryginały,
  nowa metoda `bank_import`, blokada archiwizacji źródeł użytych w imporcie.
- `finance/bank_transactions.py`, `finance/transaction_dates.py`: zaufane entrypointy
  nowych bankowych operacji i dat, bez osłabiania publicznego TransactionCreate.
- `frontend/src/api/bankImports.ts`, `pages/{FinanceImports,FinanceImportReview}.tsx`,
  `components/finance/imports/`: hooki, lista, upload, mapowanie, review i receipt.
- Testy: `backend/tests/test_finance/test_bank_imports/`, dokumentowe regresje;
  `frontend/src/pages/FinanceImports.test.tsx`, komponentowe testy i `e2e/bank-imports.spec.ts`.

A1→A2→A3. A4–A7 konsumują kontrakty A1 i tekst A2, bez wzajemnych zależności.
A8 konsumuje A1–A7; A9 konsumuje A8. A10 konsumuje zamrożone HTTP DTO A1/A8/A9;
A11 odbiera całość. Etap B korzysta ze źródeł/rewizji/jobów A1–A3 i commands A9.

## Zamrożone kontrakty między zadaniami

W skróconych sygnaturach DB poniżej `db:AsyncSession`, `owner:UUID`, wszystkie ID:UUID;
entrypointy wykonujące I/O są async i w kodzie mają pełne type hints. Nowe moduły
są wewnątrz `backend/app/finance/`, chyba że podano inną ścieżkę.

Typy Pydantic/dataclass w `imports/contracts.py` (strict minor-unit integers):
- `Bank = Literal['velo','ing','revolut']`; `ImportKind = Literal['statement','loan_schedule']`.
- `Check(code:str, required:bool, result:Literal['passed','failed','unavailable'],
  expected:int|None, actual:int|None)`; `SourcePosition(page:int|None,line:int,section:str|None)`.
- `StatementRow(key:str, position:SourcePosition, booking_date:date|None,
  operation_date:date|None, started_at:str|None, completed_at:str|None,
  description:str, amount:int, fee:int, currency:Literal['PLN','EUR','USD'],
  state:Literal['posted','pending','reverted','cancelled','unknown'],
  balance_after:int|None, bank_reference:str|None, raw:dict[str,object])`.
  `amount` to podpisana zmiana salda rachunku NETTO, już z fee. `fee` jest podpisaną
  opłatą: dodatnia=obciążenie, ujemna=zwrot opłaty; znak wynika z parsera, nigdy abs().
  Rozkład: main_movement=amount+fee, fee_movement=-fee; suma obu=amount.
  Składowa0 nie tworzy postingu. Nazwy i wartości bankowych kolumn zachowane w raw.
- `ParsedStatement(kind='statement',bank:Bank,layout:str,parser_version:str,
  account_reference:str|None,currency:str,period_start:date,period_end:date,
  opening:int|None,closing:int|None,rows:list[StatementRow],checks:list[Check],
  warnings:list[str],card_header:dict[str,object]|None)`.
- `ScheduleRow(bank_number:int,due_date:date,principal:int,interest:int,fees:int,
  total:int,balance_after:int|None,position:SourcePosition)` oraz
  `ParsedSchedule(kind='loan_schedule',bank:Bank,layout:str,parser_version:str,
  loan_reference:str|None,effective_date:date|None,currency='PLN',
  rows:list[ScheduleRow],checks:list[Check],warnings:list[str],complete_tail:bool)`.
  A1 definiuje oba kształty; parser/aktywacja harmonogramu dopiero w etapie B.
- `ParsedImport = ParsedStatement | ParsedSchedule`, discriminator `kind`.
- `ParserInput(content:bytes,pages:tuple[str,...]|None,mime_type:str,sha256:str)`;
  `parse_import(data:ParserInput,kind:ImportKind)->ParsedImport` w registry.
  PDF pages są wynikiem bounded pypdf, nie tekstem OCR dostarczonym przez klienta.
- `ImportError(code:str,detail:str,http_status:int=409)`; inne zasoby 404,
  błędne dane422, przeterminowane decyzje/preview409, za duży plik413.

HTTP DTO w `imports/schemas.py`, TS mirror w `api/bankImports.ts`:
- Batch `{id,kind,version,archived_at,commit_state,sources,unresolved_count}`.
- Source `{id,batch_id,document_id,sha256,original_name,bank,layout,parser_version,
  processing_state,validation_state,current_revision_id,checks,warnings}`.
- Row `{id,source_id,revision_id,source_key,position,kind,bank_fields,schedule_fields,
  candidate_ids,decision}`; exactly-one bank_fields:StatementRow lub
  schedule_fields:ScheduleRow zgodnie z kind. To źródło, nie dowolne postings z klienta.
  W etapie A UI obsługuje tylko statement; B korzysta z tego samego źródła/rewizji.
- Decision `{group_id,row_ids,action:'create'|'link'|'defer',kind:'expense'|'income'|
  'expense_refund'|'transfer'|'exchange',account_id,other_account_id?,category_id?,
  existing_transaction_id?,fee_category_id?,manual_rate?,acknowledgements}`.
- Preview `{id,batch_id,version,request_hash,groups,new_transaction_count,
  linked_count,unresolved_count,warnings,quotes}`; serwer trzyma kanoniczny payload.
- CommitResult `{receipt_id,batch_id,request_hash,transaction_ids,linked_row_ids,
  remaining_group_ids,commit_state}`. Żaden klient nie dostarcza gotowych postings.
- Klasy HTTP: `BatchDTO,SourceDTO,RowDTO,SourceUploadResult,PreviewRequest,
  DecisionUpdate,PreviewDTO,CommitRequest,CommitResult,JobDTO` zgodnie z kształtami wyżej.
  `RowPage(items:list[RowDTO],total:int,offset:int,limit:int)`; PreviewRequest
  acknowledgements domyślnie [], pozostałe wymagane pola jawne.
  `ImportFailure(code:str,retryable:bool)` opisuje błąd workera, nie gotowy dokument.

Ścieżki pod `/api/finance/imports` (CSRF przez istniejący mount finance):
`POST '' {kind}`, `GET ''`, `GET /{batch_id}`, `POST /{batch_id}/sources` multipart,
`POST /{batch_id}/sources/existing {document_id}`, `POST /{batch_id}/sources/{id}/prepare`,
`GET /{batch_id}/rows?source_id=&offset=&limit=`, `PUT /{batch_id}/decisions
{expected_version,decisions}`, `POST /{batch_id}/preview {expected_version,group_ids,
acknowledgements}`, `POST /{batch_id}/commit {preview_id,request_hash}`,
`GET /{batch_id}/commands/{idempotency_key}`, `POST /{batch_id}/archive`.
Mutacje wymagają `Idempotency-Key`; preview/decision mają dodatkowo wersję optymistyczną.
Ten sam Document + kind u właściciela otwiera istniejące źródło/batch; odpowiedź uploadu
zawiera `{source,is_duplicate,existing_batch_id}`. Inny właściciel nie poznaje tego ID.

### Task 1: Trwałe kontrakty i addytywny staging (A1)

**Files:** Create `imports/{__init__,models,contracts,schemas,service,queries,errors}.py`;
Modify `documents/{models,schemas}.py`, `backend/migrations/env.py`;
Modify `backend/pyproject.toml` wyłącznie o marker migration;
Test `test_bank_imports/{conftest,factories,test_contracts,test_staging,test_migration}.py`;
Create `backend/tests/migration_fixtures.py` dla prywatnej scratch DB i realnego Alembic.
Migration: `/migration "bank_import_staging"`; po generacji zapisać rzeczywisty
`MIGRATION_PATH` i revision w ledgerze; down_revision=739144d5eaef, pojedynczy head.

**Interfaces:** Produces powyższe DTO i `create_batch(db:AsyncSession,owner:UUID,
kind:ImportKind)->BatchDTO`, `get_batch(db,owner,batch_id)->BatchDTO|None`,
`list_rows(db,owner,batch_id,*,source_id:UUID|None,offset:int,limit:int)->RowPage`.
Test helpers w factories: `ready_statement(db,owner,payload:ParsedStatement)->UUID`
z prywatnym syntetycznym Document; `ledger_snapshot(db)->dict[str,str]` hashuje
istniejące konta/transakcje/postings/mapowania/raty/linki. Helpers nigdy w app.

- [ ] **Step 1: Write failing tests.** Contract roundtrip, strict ints/zero vs missing,
  owner404, staging bez księgi i prawdziwa migracja zachowująca istniejące rekordy.
  ```python
  @pytest.mark.integration
  async def test_empty_batch_has_no_ledger_effect(db_session, owner):
      before = await ledger_snapshot(db_session)
      batch = await create_batch(db_session, owner.id, "statement")
      assert batch.version == 1 and batch.commit_state == "not_committed"
      assert await ledger_snapshot(db_session) == before
  ```
- [ ] **Step 2: Verify RED.** Backend cwd: `.venv/bin/pytest tests/test_finance/test_bank_imports/test_contracts.py tests/test_finance/test_bank_imports/test_staging.py -q`.
  Expected: missing new contracts/service, nie błąd połączenia/skip integracji.
- [ ] **Step 3: Implement minimal staging.** Modele `ImportBatch,ImportSource,
  ImportRevision,ImportRow,ImportJob,ImportGroup,ImportGroupRow,ImportDecision,
  ImportPreview,ImportEvidence,ImportBankIdentity`; receipts użyją FinanceCommandReceipt.
  Version/checks/commit states według kontraktu; owner+Document+kind unique; ordinal
  unique w rewizji, grupy nie mogą konsumować tej samej row dwa razy. ImportEvidence
  rozróżnia component main|fee|whole i signed attributed_source_amount, unique(row,component),
  aby jedna linia z fee mogła dokumentować dwa postingi kont bez podwojenia ruchu.
  ImportBankIdentity ma unique(owner,bank,account,currency,strong_reference) i wskazuje
  jeden zatwierdzony group/event z całą jego alokacją, nie pojedynczy posting fee.
  Wiele evidence może dokumentować tę samą identity bez ponownego kosztu. Brak
  strong_reference nie jest wypełniany row_hashem. FK RESTRICT,
  kwoty BIGINT, JSONB tylko surowe/propozycyjne pola; hash wiersza NIE globalnie unique.
  `Document.processing_method` dodaje `bank_import` bez zmiany starych wierszy;
  jawny import modeli w Alembic. Cykl Source.current_revision↔Revision.source ma
  nazwany FK/use_alter, aby metadata.create_all/drop_all testów działało.
  Downgrade odmawia przy nowych danych/importowych
  Document, zamiast ich usuwać lub przepisywać metodę. Brak backfillu Q7/Actual.
- [ ] **Step 4: Verify GREEN.** Te same testy + `test_migration.py` na własnym PG:
  realne upgrade/downgrade/upgrade pustego rozszerzenia, zachowanie legacy fixture,
  odmowa niepustego downgrade; Expected: PASS, jeden head, zero runtime skips.
  Realne migration testy oznaczyć migration, nie integration: root autouse create_all
  nie może uprzednio stworzyć nowych tabel. `owned_migration_database` z
  tests/migration_fixtures waliduje zatwierdzony host/port finanse_test i własny
  kontener/OID, tworzy tylko swoją unikalną scratch DB, uruchamia Alembic w subprocess
  z jej jawnym URL i sprząta wyłącznie ją. Nie rozszerzać root safety gate.
- [ ] **Step 5: Commit.** Po `/lint`, `/typecheck`, `/test` według roadmapy:
  `feat: dodaj trwały staging importu bankowego`; stage tylko pliki zadania i `MIGRATION_PATH`.

### Task 2: Prywatny upload PDF/CSV bez pipeline faktur i AI (A2)

**Files:** Create `documents/import_storage.py`, `imports/{storage,pdf_text}.py`;
Modify `documents/{lifecycle,router,review_router}.py`, `config.py`,
`frontend/src/api/documents.ts`, `components/documents/documentProcessing.ts`;
Test `test_bank_imports/{test_storage,test_pdf_text}.py`, document lifecycle/review regressions.

**Interfaces:** Consumes A1. Produces
`store_import_document(db,owner,*,filename:str,content:bytes)->tuple[Document,bool]`,
`attach_source(db,owner,batch_id,document_id)->SourceUploadResult`,
`read_import_input(db,owner,source_id)->ParserInput`,
`extract_pdf_pages(content:bytes,limits:PdfLimits)->tuple[str,...]`.
`PdfLimits(max_bytes:int,max_pages:int,max_text_chars:int,timeout_seconds:float,
max_memory_bytes:int)` i upload-row limits są projekcją konfigurowalnych settings.

- [ ] **Step 1: Write failing tests.** Oryginalne bajty identyczne, PDF/CSV dozwolone
  tylko w imporcie, dokumenty fakturowe nadal odrzucają CSV, crossowner404, hash/path
  integrity, aktywny OCR/vision źródła odmawia attach do czasu zakończenia lub jawnego
  zatrzymania przez istniejący obieg. Reuse gotowego dokumentu nie zmienia jego metody.
  ```python
  async def test_bank_upload_has_no_document_jobs(db_session, owner, csv_bytes):
      doc, duplicate = await store_import_document(db_session, owner.id,
          filename="statement.csv", content=csv_bytes)
      assert not duplicate and doc.processing_method == "bank_import"
      assert doc.status == "done"
      assert await document_job_count(db_session, doc.id) == 0
  ```
  Dodać testy: źródło importu blokuje archive/delete/review/OCR409, nie ma enqueue
  `process_document`, OCR, vision lub sugestii; importer nie modyfikuje starego Document.
- [ ] **Step 2: Verify RED.** Focus `/test`: `test_storage.py`, `test_pdf_text.py`
  i istniejące `tests/test_documents/test_lifecycle.py`. Expected: nowe funkcje nie istnieją.
- [ ] **Step 3: Implement storage and bounded pypdf extraction.** Reuse content-addressed
  zapisu i zweryfikowanego prywatnego odczytu; nowe pliki `bank_import/done`, bez kolejki
  dokumentów i bez DocumentText/OCR. Osobna walidacja MIME+bytes+CSV nagłówków; stdlib
  CSV tekst, nie wykonywanie formuł. pypdf w ograniczonym procesie, limit bytes/pages/
  output/time/memory; uszkodzone/encrypted/image-only/Excel rejected z kodem. Preserve
  pages i kolejność; brakujące glyphs/kwoty to incomplete, nie zgadywanie.
  Lifecycle sprawdza referencje importu przed archiwizacją; prywatny streaming bez zmian.
  Frontend rozpoznaje metodę bank_import bez oznaczania jej jako AI/OCR.
- [ ] **Step 4: Verify GREEN.** Te same testy + originals/admission/review regressions,
  PDF z naprawdę wyciąganym tekstem i odrzucenie skanu. Expected: PASS i zero jobów AI/OCR.
- [ ] **Step 5: Commit.** Bramki projektu; `feat: dodaj bezpieczne źródła PDF i CSV importera`.

### Task 3: Trwały worker, lease i wersje odczytu (A3)

**Files:** Create `imports/{jobs,worker}.py`, `imports/parsers/{__init__,registry}.py`;
Modify `backend/app/worker.py`, `config.py`; Test `test_bank_imports/test_jobs.py`,
`test_worker.py`, `test_registry.py`.

**Interfaces:** Consumes A1/A2. Produces `request_prepare(db,owner,source_id,key:str)->JobDTO`,
`claim_import_job(db,job_id:UUID,now:datetime)->ImportClaim|None`,
`finish_import_job(db,claim:ImportClaim,result:ParsedImport|ImportFailure)->bool`,
`dispatch_import_jobs(ctx:dict[str,object])->None`,
`process_import_job(ctx:dict[str,object],job_id:str)->None`;
`ImportClaim(job_id,owner_id,batch_id,source_id,revision_id,lease_token,attempt)`.
Registry `parse_import(ParserInput,kind)->ParsedImport`, allowlisted layouts only.

- [ ] **Step 1: Write failing tests.** PostgreSQL intent przeżywa brak Redis;
  jeden claim, retry po stale lease, stary lease nie zapisuje wyniku; parse bez księgi.
  ```python
  async def test_stale_worker_cannot_publish_newer_revision(db_session, claimed_jobs):
      old, current, result = claimed_jobs
      assert await finish_import_job(db_session, old, result) is False
      assert await finish_import_job(db_session, current, result) is True
  ```
  Reparse nigdy nie usuwa committed evidence/decisions; rozpoznanie Citi/unsupported
  jest komunikatem bez gotowych wierszy finansowych. Dwie identyczne intencje nie tworzą dwóch rewizji.
- [ ] **Step 2: Verify RED.** Focus `/test` na `test_jobs.py test_worker.py test_registry.py`.
  Expected: brak nowych entrypointów; fixtures PG działają, nie ma external API.
- [ ] **Step 3: Implement durable intent/recovery.** DB commit przed enqueue; ARQ
  `_job_id=finance-import:{job_id}`, bounded dispatcher i retry, SKIP LOCKED, fencing
  token i wersja źródła. Oddzielne stany process/validation/commit. Job na źródło,
  nie trzymanie transakcji DB podczas pypdf; publish tylko dla aktualnego claim.
  Bez dispatchu receipt/AI, brak importu finance.service powodującego circular import.
  Reparse źródła częściowo zatwierdzonego zachowuje starą rewizję/evidence i wymaga
  jawnego porównania niezapisanych wierszy; nie odblokowuje ponownego commitu starych.
  Claim trzyma tylko job i kończy transakcję; publication/zmiana current revision
  zachowuje owner mutex→batch→source→revision→job. Nie trzymać job lock podczas
  oczekiwania na owner mutex, parsowania lub wykonywania delivery.
- [ ] **Step 4: Verify GREEN.** Te same testy, odzyskanie po restarcie i oba istniejące
  dispatchery dokumentów bez regresji. Expected: PASS, stale publish=False, ledger unchanged.
- [ ] **Step 5: Commit.** Bramki projektu; `feat: dodaj trwały odczyt i retry importów bankowych`.

### Task 4: Revolut CSV — trzy waluty, fee i stany (A4)

**Files:** Create `imports/parsers/{money,revolut_csv}.py`;
Test `test_bank_imports/test_revolut_csv.py`, syntetyczne `fixtures/revolut_*.csv`.

**Interfaces:** Consumes A1 registry. Produces `parse_revolut_csv(data:ParserInput)->ParsedStatement`;
`parse_minor_units(value:str,*,decimal_separator:str)->int` odrzuca niepełne kwoty,
nie używa float; registry dispatchuje po pełnym kontrakcie kolumn, nie nazwie pliku.

- [ ] **Step 1: Write failing tests.** Pełne dziesięć kolumn, BOM/cytowanie/newlines,
  PLN/EUR/USD, ukończone vs pending/reverted, duplikaty podobnych zakupów i overlap.
  ```python
  def test_same_description_amount_keeps_two_real_purchases(revolut_two_purchases):
      result = parse_revolut_csv(revolut_two_purchases)
      assert [row.amount for row in result.rows] == [-100, -100]
      assert [row.balance_after for row in result.rows] == [900, 800]
      assert len({row.key for row in result.rows}) == 2
  ```
  Oddzielne fixtures dowodzą, czy fee w eksportowanej Amount jest już uwzględnione;
  równanie sald musi to sprawdzać, nie zmieniać znaków pod oczekiwany wynik.
- [ ] **Step 2: Verify RED.** `.venv/bin/pytest tests/test_finance/test_bank_imports/test_revolut_csv.py -q`.
  Expected: brak parsera, nie akceptacja pominiętych wierszy.
- [ ] **Step 3: Implement parser and register.** Zachować komplet kolumn, surowe timestampy
  i brak strefy; równość sald z uwzględnieniem fee i kierunku eksportu, opening-derived
  oznaczone ostrzeżeniem. Nie mieszać walut w jednym rachunku. Każdy rekord czytany;
  nieznany stan nie staje się posted. Brak required balance completed blokuje układ.
  Pending/cancelled/reverted pozostają widoczne jako nieksięgowane i nie wymagają
  fikcyjnego txn do domknięcia importu. Posted z amount=fee=0 jest tylko informacją,
  jeżeli saldo źródła potwierdza brak ruchu; nie wywoływać ledger dla zerowych kwot.
  Unknown state wymaga nowego rozpoznanego kontraktu, nie przycisku „uznaj za posted”.
- [ ] **Step 4: Verify GREEN.** Ten sam plik + contracts/registry. Expected: wszystkie
  wiersze zachowane, kontrolne błędy blokowane, CSV nigdy nie wywołuje spreadsheet/AI.
- [ ] **Step 5: Commit.** Bramki projektu; `feat: odczytuj wyciągi CSV Revolut`.

### Task 5: Velo PDF rachunku — pełna tabela i salda (A5)

**Files:** Create `imports/parsers/velo_account.py`;
Test `test_bank_imports/test_velo_account.py`, `fixtures/velo_account_*.pdf`.

**Interfaces:** Consumes A1/A2/A4 money. Produces
`parse_velo_account(data:ParserInput)->ParsedStatement`, bez DB/HTTP.

- [ ] **Step 1: Write failing tests.** Wielostronicowe wiersze, powtórzone nagłówki,
  znaki WN/MA, dwa rodzaje dat, otwarcie/obroty/zamknięcie i salda po każdej operacji.
  ```python
  def test_truncated_velo_statement_is_not_ready(velo_truncated):
      result = parse_velo_account(velo_truncated)
      assert any(c.required and c.result == "failed" for c in result.checks)
  ```
  Co najmniej jeden test przechodzi przez rzeczywisty pypdf z syntetycznego PDF;
  porównanie sąsiednich okresów nie wymyśla brakujących operacji.
- [ ] **Step 2: Verify RED.** Focus `test_velo_account.py`. Expected: brak parsera.
- [ ] **Step 3: Implement deterministic layout parser.** Wersjonowane kotwice nagłówka,
  kolejność stron/wierszy i kontrola całego tekstu; brak unmatched finansowych linii
  pomijanych po cichu. Rozpoznanie konta jest propozycją, nie zgodą na jego wybór.
- [ ] **Step 4: Verify GREEN.** Focus + prywatny lokalny read-only odbiór trzech próbek
  z niezależnymi sumami. Expected: wszystkie kontrolne równania PASS lub jawne blocked,
  bez danych źródłowych w logach/fixture Git i bez połączenia do produkcji.
- [ ] **Step 5: Commit.** Bramki projektu; `feat: odczytuj wyciągi rachunku Velo PDF`.

### Task 6: ING PDF Direct i oszczędnościowe (A6)

**Files:** Create `imports/parsers/ing.py`;
Test `test_bank_imports/test_ing_pdf.py`, `fixtures/ing_{direct,savings}_*.pdf`.

**Interfaces:** Consumes A1/A2/A4. Produces
`parse_ing_statement(data:ParserInput)->ParsedStatement` z layout
`ing_direct_v1|ing_savings_v1`; jeden parser per udokumentowana rodzina układu.

- [ ] **Step 1: Write failing tests.** Direct, oszczędnościowe, wielomiesięczny okres,
  długie opisy, rozdzielenie nagłówków od operacji, poprawne sumy obu stron.
  ```python
  def test_savings_period_is_not_assumed_monthly(ing_savings_multimonth):
      parsed = parse_ing_statement(ing_savings_multimonth)
      assert (parsed.period_end - parsed.period_start).days > 31
      assert all(c.result == "passed" for c in parsed.checks if c.required)
  ```
  Brak daty/kwoty w pojedynczym wierszu musi blokować kompletność, nie usuwać wiersza.
- [ ] **Step 2: Verify RED.** Focus `test_ing_pdf.py`. Expected: brak parsera.
- [ ] **Step 3: Implement two explicit layouts.** Nie zakładać okresu miesięcznego;
  wyodrębniać i sprawdzać wszystkie wiersze, nie tylko wcześniejsze audytowane nagłówki.
  Currency/account/source dates nie są dziedziczone z innego pliku użytkownika.
- [ ] **Step 4: Verify GREEN.** Focus + lokalny read-only odbiór obu rodzin prywatnych
  próbek (w tym każde wierszowe równanie), contracts/registry. Expected: PASS bez ledger mutation.
- [ ] **Step 5: Commit.** Bramki projektu; `feat: odczytuj wyciągi ING Direct i oszczędnościowe`.

### Task 7: Velo karta PDF i bezpieczne metadane okresu (A7)

**Files:** Create `imports/parsers/velo_card.py`, `imports/card_statements.py`;
Test `test_bank_imports/test_velo_card.py`, `test_card_headers.py`, syntetyczne PDF sekcji karty.

**Interfaces:** Consumes A1/A2/A4. Produces
`parse_velo_card(data:ParserInput)->ParsedStatement`,
`validate_card_header(parsed:ParsedStatement,decision:CardHeaderDecision)->StatementCreate`
z istniejącego `finance/credit_card_schemas.py`.
`CardHeaderDecision(account_id,period_start,period_end,due_date,debt_pln,minimum_pln,
debt_definition_confirmed:bool)`; użyć istniejącego schematu wejścia karty bez drugiego salda.

- [ ] **Step 1: Write failing tests.** Trzy przypadki: ta sama operacja wydrukowana
  w kilku sekcjach, dwa prawdziwe podobne zakupy i układ niejednoznaczny.
  ```python
  def test_ambiguous_card_repeat_cannot_be_deduplicated_to_fit_total(card_ambiguous):
      parsed = parse_velo_card(card_ambiguous)
      assert any(c.required and c.result == "failed" for c in parsed.checks)
  ```
  Header minimum/termin/rodzaj długu wymagają osobnego potwierdzenia; nie dodają księgi.
  Rozróżnić current-cycle debt/total debt/future installment principal; unknown nie staje się0.
- [ ] **Step 2: Verify RED.** Focus `test_velo_card.py test_card_headers.py`.
  Expected: brak nowego parsera/adaptera nagłówka, stare testy kart nadal działają.
- [ ] **Step 3: Implement validated section rules.** Reguły powielenia przypisane
  do wersji układu i kontrolnych sum, nie do ogólnego identycznego napisu. Header
  niejednoznaczny blokuje tylko metadata, jeśli niezależna tabela jest poprawna.
  Metadane okresu zapisuje później A9 przez istniejący serwis karty, z jawnym review.
- [ ] **Step 4: Verify GREEN.** Focus + read-only odbiór pięciu prywatnych cykli,
  w tym problematycznej sekcji; regresje kart. Expected: rzeczywista powtórka vs
  dwa zakupy rozstrzygnięte testami, nierozpoznany przypadek blocked, bez zmiany sald.
- [ ] **Step 5: Commit.** Bramki projektu; `feat: odczytuj wyciągi kart Velo bez zgadywania duplikatów`.

### Task 8: Mapowania, kandydaci, wycena i niezmienny preview (A8)

**Files:** Create `imports/{matching,decisions,valuation,preview}.py`;
Test `test_bank_imports/{test_matching,test_decisions,test_valuation,test_preview}.py`.

**Interfaces:** Consumes A1–A7. Produces
`save_decisions(db,owner,batch_id,data:DecisionUpdate)->BatchDTO`,
`get_candidates(db,owner,row_id)->list[ExistingCandidate]`,
`prepare_preview(db,owner,batch_id,data:PreviewRequest)->PreviewDTO`,
`canonical_preview_payload(db,owner,preview_id)->dict[str,object]`.
`ExistingCandidate(transaction_id,account_posting_id,strength:'strong'|'possible',
reasons:list[str],conflicts:list[str])`; client nie wybiera strength.
`FrozenQuote(currency,requested_date,effective_date,rate:Decimal,source,base_amount:int)`.
`ExchangeValuation(base_pln:int,from_rate:Decimal,to_rate:Decimal,from_source:str,
to_source:str,quote_date:date)` jest częścią zamrożonej grupy, nie dopiero wynikiem commitu.

- [ ] **Step 1: Write failing tests.** Możliwy duplikat Actual nie staje się automatycznie
  linkiem/skipem, różne konta/waluty odmawiają link; mocna referencja nie nadpisuje kwoty.
  ```python
  async def test_preview_has_zero_financial_effect(db_session, owner, ready_batch):
      before = await ledger_snapshot(db_session)
      preview = await prepare_preview(db_session, owner.id, ready_batch.id,
          PreviewRequest(expected_version=ready_batch.version, group_ids=ready_batch.group_ids))
      assert preview.new_transaction_count == 1
      assert await ledger_snapshot(db_session) == before
  ```
  Dodać EUR/USD historical NBP/weekend/manual/noquote, frozen quote, external expense
  vs own transfer, fee już w Amount, para FX bez drugiej nogi, cash withdrawal bez
  wybranego konta gotówki, poprawny source ale niezgodny IBAN/konto, stare otwarcie
  wymagające acknowledgement bez korekty i stara preview version409.
- [ ] **Step 2: Verify RED.** Focus cztery nowe pliki. Expected: brak serwisów,
  nie brak providerów (NBP transport kontrolowany w testach).
- [ ] **Step 3: Implement review and preview.** Mapowanie owner+bank+rachunek+currency,
  bez nowych kont; user wybiera create/link/defer i kategorię/typ. Decyzje grupują
  kompletny transfer/FX/fee. Każdy link sprawdza account posting, kierunek i kwotę;
  sama data/amount/description/row_hash daje tylko possible. Liczność powtórzeń zachowana.
  Kursy pobierane przed write locks, przeliczenia Decimal, max6 miejsc kursu zgodnie
  z ledger_validation; immutable payload wiąże owner/source hash/parser revision/
  decision version/selected groups/quote i odczytane aktualne powiązane rekordy.
  Wszystkie source required checks PASS; ledger gap osobny warning do potwierdzenia.
  Cache ręcznie sprawdzonych mapowań jest propozycją, nigdy upoważnieniem do commitu.
  Link do starej operacji obejmującej całe net amount (np. Actual z nierozbitą fee)
  może pokryć źródłowy wiersz jako whole. Wymaga dokładnej zgodności konta/waluty/
  kierunku/kwoty i jawnego wyboru; pokaż „podział kosztów do uzgodnienia”, nie twórz
  dodatkowej fee ani nie zmieniaj starej kategorii. Nowe create rozkłada main/fee;
  nie wolno mieszać whole i components dla tego samego eventu/wiersza.
  Fingerprint ledger obejmuje też przeliczone source/base salda docelowych kont oraz
  zestaw/updated_at wszystkich potencjalnych dopasowań wybranych rows. Nowy możliwy
  duplikat po preview musi dać409 nawet gdy równoległe operacje mają łączny ruch0.
  FX z nogą PLN: wspólny base to jej rzeczywista kwota, foreign rate wynika z actual legs.
  EUR↔USD: kotwica base to jawna wycena NBP waluty wychodzącej, a PLN rate drugiej
  nogi jest implied przez rzeczywisty cross-rate (nie udaje NBP). Oba rates/source
  i base są widoczne i zamrożone. Jeśli nie da się zachować actual legs przy
  existing precyzji6/rounding validatora, grupa blocked. Zwrot zakupów i ujemne fee
  wymagają jawnej klasyfikacji expense_refund, nie income lub utraty znaku.
- [ ] **Step 4: Verify GREEN.** Te same pliki + parsers. Expected: immutable preview,
  brak postings, brak wyceny istniejącego Actual, oba prawdziwe zakupy nadal odrębne.
- [ ] **Step 5: Commit.** Bramki projektu; `feat: dodaj weryfikację i podgląd importu wyciągów`.

### Task 9: Atomowy commit, rzeczywiste FX i pochodzenie (A9)

**Files:** Create `imports/{commands,commit,provenance}.py`, `finance/bank_transactions.py`,
`finance/import_router.py`; Modify `finance/{router,transactions,ledger_validation,
transaction_dates,document_guards,currency_correction}.py` tylko dla zaufanej integracji;
Test `test_bank_imports/{test_commit,test_commit_races,test_bank_transactions,test_routes}.py`.

**Interfaces:** Consumes A8. Produces
`commit_import(db,owner,batch_id,data:CommitRequest,key:str)->CommitResult`,
`get_command_result(db,owner,batch_id,key:str)->dict[str,object]|None`,
`record_import_evidence(db,owner,*,row_ids:list[UUID],transaction_id:UUID,
posting_id:UUID,receipt_id:UUID,component:Literal['main','fee','whole'],
attributed_source_amount:int)->None`,
`create_bank_transaction(db,owner,data:BankTransactionInput)->FinancialTransaction`.
`BankPostingInput(account_id:UUID|None,category_id:UUID|None,source_amount:int,
source_currency:str,base_amount_pln:int,fx_rate:Decimal,fx_rate_source:str,direction:str)`;
`BankTransactionInput(kind:Literal['expense','income','expense_refund','transfer','exchange'],
booking_date:date,purchase_date:date|None,description:str,postings:tuple[BankPostingInput,...])`
powstaje tylko na serwerze z preview. Żadnego modelu ORM lub postings od klienta.
Wspólny adapter A/B: `ImportCommandOutcome(response:BaseModel,entity_id:UUID,
version:int|None,result_ids:list[UUID])` oraz
`run_import_command(db,owner,*,action:str,key:str,batch_id:UUID,payload:dict[str,object],
operation:Callable[[UUID],Awaitable[ImportCommandOutcome]])->dict[str,object]`.
Action allowlist bank_import.commit|loan_schedule.activate, entity_id=batch_id,
response_json zawiera batch_id/request_hash; GET commands wybiera action według batch.kind.

- [ ] **Step 1: Write failing tests.** Pełny commit/replay/races, rollback całej
  wybranej grupy, to samo key z innym payload409, utracona odpowiedź i GET commands.
  ```python
  async def test_replay_does_not_repost(db_session, owner, confirmed_preview):
      first = await commit_import(db_session, owner.id, confirmed_preview.batch_id,
          confirmed_preview.request, "same-intent")
      after = await ledger_snapshot(db_session)
      again = await commit_import(db_session, owner.id, confirmed_preview.batch_id,
          confirmed_preview.request, "same-intent")
      assert again == first
      assert await ledger_snapshot(db_session) == after
  ```
  Dodać: link-only bez zmiany starego txn/postings/dates/Actual/loan links; drugi
  wyciąg dokumentuje tę samą nogę przelewu; double click i dwa batches konkurują
  o mocną referencję; owner404; zmiana źródła/revision/decision/konta/txn po preview409;
  data source import nie staje się manual; nowe źródło klienta nie omija walidacji;
  EUR↔USD actual legs, fee osobno, refund expense-credit nie jako income;
  niepełna para/nieosiągalny kurs w precyzji6 blokuje, nie zaokrągla actual amounts.
- [ ] **Step 2: Verify RED.** Focus cztery nowe pliki + `test_exchange.py`,
  `test_transaction_dates.py`, guards dokumentów/kart/kredytów. Expected: brak commit,
  niewspierany trusted bank exchange/refund; żaden publiczny guard nie może osłabnąć.
- [ ] **Step 3: Implement trusted command.** Nie wywoływać `run_receipt_command` bez
  adaptacji: hardkoduje entity_type receipt_items. Współdzielić FinanceCommandReceipt
  przez własne action `bank_import.commit` i analogiczny kanoniczny digest/replay.
  Lock order: command-key→shared owner mutation mutex→batch/source/decision/preview
  w posortowanej kolejności→accounts sorted UUID→existing transactions/postings→
  evidence/receipt/audit. Współdzielony mutex przed accounts zachowuje kolejność
  istniejących mutacji; bez HTTP/parse pod write locks. Atomowy wynik i receipts.
  Revalidate pełny preview payload i ledger evidence; źródło nie może stracić oryginału.
  `create_bank_transaction` używa istniejącego ledger core z trusted flags, nie INSERT
  postings z routera. Publiczne `source='bank_import'` nigdy nie włącza wyjątków.
  Dla refund jawny wewnętrzny expense-credit guard z zachowaniem istniejącego card
  refund; źródłowe kwoty/daty są bankowe, metadata źródło='import', bez zmian starych dat.
  `add_import_date_metadata(db,txn,purchase:date|None,booking:date)->None` jest
  zaufanym helperem: tylko nowy txn source=bank_import, txn.date==booking, brak meta;
  nie rozszerzać publicznego manual-date API o możliwość fałszywej proweniencji.
  Dla FX nie używać starego ExchangeCreate wyliczającego to_amount. Zaufać tylko
  dwóm rzeczywistym nogom i wycenie preview: jeden wspólny dodatni base PLN,
  rate≤6dec, zachowanie obu actual source amounts i ledger round-trip validation.
  EUR↔USD wymaga jawnej wspólnej wyceny PLN z NBP jednej kotwicy i implied PLN rate
  drugiej nogi wynikającego z rzeczywistego cross-rate; pokazać oba źródła w preview.
  Jeśli dokładne legs nie mieszczą się w existing 6-dec/rounding invariant, blocked.
  Bez cichego fikcyjnego PLN account/rounding posting lub zmiany globalnego validatora.
  Fee osobna expense w tej samej atomowej grupie, rozliczona bez podwojenia Amount.
  ImportEvidence zabezpiecza delete/date/pending/currency-change źródłowych txn;
  kontrolowana zmiana opisu/kategorii pozostaje zgodna z dotychczasowymi regułami.
  Dane wyciągu karty tylko po CardHeaderDecision, idempotentnie, przez card service;
  brak automatycznego wiązania spłat/rat kredytowych od samego odczytu wyciągu.
- [ ] **Step 4: Verify GREEN.** Focus + pełne invariants/property cases, races
  rzeczywistymi osobnymi sesjami PostgreSQL; Expected: jedna operacja, jedna receipt,
  debit-credit=0, source legs i stare rekordy identyczne, brak provider call w commit.
- [ ] **Step 5: Commit.** Bramki projektu; `feat: zatwierdzaj importy bankowe atomowo i idempotentnie`.

### Task 10: Interfejs upload → review → zatwierdzenie → receipt (A10)

**Files:** Create `frontend/src/api/bankImports.ts`, `pages/{FinanceImports,
FinanceImportReview}.tsx`, `components/finance/imports/{ImportUpload,ImportSources,
ImportAccountMapping,ImportRows,ImportGroupEditor,ImportPreview,ImportReceipt}.tsx`;
Modify `App.tsx`, `components/navigation.ts`, `components/finance/FinanceTabs.tsx`,
`pages/{FinanceAccounts,FinanceCreditCardDetails,Documents}.tsx`;
Test nowe hooki/komponenty/strony, istniejące navigation/documents/card tests.

**Interfaces:** Consumes frozen HTTP DTO i ścieżki A1/A9. Produces hooks
`useImports`, `useImport(batchId)`, `useImportRows(batchId,filters)`,
`useCreateImport`, `useUploadImportSource`, `useAttachImportDocument`,
`usePrepareImportSource`, `useSaveImportDecisions`, `usePreviewImport`,
`useCommitImport`, `useImportCommandResult`. Typy eksportowane, nie duplikowane po komponentach.
Routes `/finances/imports`, `/finances/imports/:batchId`; context/URL jako źródło wybranego batch.

- [ ] **Step 1: Write failing tests.** Upload wielu plików z per-file wynikiem,
  source duplicate otwiera existing_batch_id, poprawny deep link po reload, frozen
  preview i wyłączony commit do czasu jawnego potwierdzenia, incomplete group blocked.
  ```tsx
  it("does not commit when uploading a statement", async () => {
    renderImportPage();
    await userUpload("statement.csv");
    expect(importApi.commit).not.toHaveBeenCalled();
    expect(await screen.findByText("Wymaga sprawdzenia")).toBeVisible();
  });
  ```
  Test helpers `renderImportPage`, `userUpload` z realnym Router/QueryClient i
  kontrolowanym HTTP adapterem fixture; nie testować, czy mock wywołuje sam siebie.
  Dodać user switching/stale promise, protected date display, trzy waluty bez sumy,
  ledger gap vs source error, external payment/refund/transfer, receipt recovery
  zachowujący ten sam idempotency key po timeout, niewysyłanie postings z klienta.
- [ ] **Step 2: Verify RED.** Frontend cwd: `npm test -- src/pages/FinanceImports.test.tsx
  src/pages/FinanceImportReview.test.tsx src/api/bankImports.test.ts`.
  Expected: brak stron/hooków; bez prawdziwego serwera/providerów.
- [ ] **Step 3: Implement existing-style UI.** Dodaj „Import” w finance nav/tabs.
  Link z rachunku/karty preselectuje account, ale serwer waliduje wybór; istniejący
  PDF w Dokumentach ma „Użyj do importu”, a nie „zatwierdź fakturę”. Nie pokazywać
  aktywnego importu harmonogramów aż do B5. Prywatny podgląd oryginału istniejącym
  viewerem, bez zawężania per-file błędów do jednego ogólnego upload-error.
  Cache klucze `['finance','imports',ownerId,generation,...]`, capture/current actor
  jak documents.ts; brak bankowych danych w localStorage i replays po zmianie usera.
  Kwoty edytowalne wyłącznie jako mapowanie/wycena według serwera, nie raw row repair.
  Retry commit używa tego samego intent key; przy niejasności pyta GET command result.
  Po commit invalidacja accounts/transactions/card summaries/reports/budgets/cashflow/
  imports, bez optymistycznego liczenia sald. Keyboard, mobile375 i desktop1440, oba motywy.
- [ ] **Step 4: Verify GREEN.** Te same testy + navigation/documents/card regressions,
  `npm run build`. Expected: realne decyzje i preview w DOM, brak before-confirm mutation,
  zero stale actor leaks; kwoty PLN/EUR/USD oddzielnie.
- [ ] **Step 5: Commit.** Bramki projektu; `feat: dodaj ekran importu i weryfikacji wyciągów`.

### Task 11: Pełny odbiór etapu, prywatne źródła i dokumentacja (A11)

**Files:** Create `frontend/e2e/bank-imports.spec.ts`,
`backend/tests/test_finance/test_bank_imports/test_acceptance.py`,
`docs/operations/bank-imports.md`, `docs/audits/2026-11-08-bank-imports-local.md`;
Modify tylko konieczne syntetyczne E2E fixture handlers i CHANGELOG/TASKS/JOURNAL.

**Interfaces:** Consumes A1–A10; freezes źródłowe hash manifesty i kontrakty używane przez etap B.

- [ ] **Step 1: Write failing end-to-end acceptance tests.** Rzeczywisty tekstowy PDF/CSV
  → persisted revision → decyzje → preview → commit → nowa sesja odczytowa. Powtórka
  i overlap dodają wyłącznie nowe, zatwierdzone wpisy; blank/truncated/wrong-owner blocked.
  Test mutation ledger baseline i źródeł, debit-credit=0 oraz bez naruszenia Q7/card guards.
  E2E w istniejącym ui.test.invalid fixture runtime, bez produkcyjnych cookies/API;
  wszystkie niespodziewane requesty są błędem, a screenshot nie zastępuje parser tests.
- [ ] **Step 2: Verify RED.** Focus `test_acceptance.py`, build +
  `npm run test:e2e -- bank-imports.spec.ts`; Expected: brakujące przekrojowe zachowanie,
  nie brak fixture endpointów błędnie uznany za produktową regresję.
- [ ] **Step 3: Close only demonstrated integration gaps.** Bez dodawania Citi/innych
  formatów/autoimports. Lokalny prywatny acceptance harness odczytuje rzeczywiste próbki,
  zapisuje poza Git hash/układ/liczbę/kontrole bez transakcji użytkownika w test DB.
  Używać syntetycznych odpowiedników dla mutacji DB i fixtures repo. Uzupełnić runbook:
  supported formats, upload != commit, otwarcie vs źródło, fee/FX, unknown layout,
  source archive protection, lost-response receipt recovery, brak automatycznego rollbacku.
- [ ] **Step 4: Verify full GREEN.** `/test`, `/lint`, `/typecheck`, frontend build,
  pełne E2E, realny roundtrip Alembic/retencja, wszystkie rodziny prywatnych próbek
  w read-only parser acceptance. Expected: PASS, bez runtime skip integracji,
  brak danych bankowych w repo/logach/E2E, brak zmian produkcji.
- [ ] **Step 5: Commit and hand over.** `docs: zapisz lokalny odbiór importu wyciągów`.
  Jeden świeży całościowy review zgodnie z wybraną metodą; Important/Critical fixes
  przez RED→GREEN i ponowne pełne bramki. Etap B dopiero po zamrożeniu interfejsów A.
  Nie oznaczać całej funkcji jako ukończonej, nie merge/push/deploy bez osobnej zgody.

## Self-review planu

- Spec1–7: A1–A10, pięć rodzin wyciągów (ING ma dwa układy), Revolut w trzech walutach.
- Spec8: jawnie etap B, nie obietnica A; wspólne typed contracts już A1.
- Spec9–10: A1–A3/A8–A9; obca rewizja/parser i source lifecycle objęte testami.
- Spec11: A11; realne migracje i prywatne parsowanie oddzielone od syntetycznego ledger test.
- Krytyczny zastany konflikt: publiczny exchange obsługuje tylko jedną nogę PLN
  i wylicza to_amount. A8/A9 mają jawny trusted bank path zachowujący oba actual legs,
  bez osłabienia globalnej precyzji i bez fikcyjnych rachunków. Refund jest expense-credit,
  nie dodatkowym income; zakres poprawnego importu obejmuje tę klasę danych.
- Kontrakty A1/A8/A9 konsumowane w A10 i B nazwane identycznie. Dokładne wygenerowane
  rewizje migracji są uzupełniane z wyniku narzędzia, nie wymyślane w planie.
- Dokument jest planem do wykonania; żadna lista testów powyżej nie oznacza, że je uruchomiono.
