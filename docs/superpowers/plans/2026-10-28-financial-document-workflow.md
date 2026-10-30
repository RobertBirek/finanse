# Financial Document Workflow Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Faktura lub zdjęcie paragonu trafia do sprawdzenia i rejestru, następnie do Nadchodzących albo do jawnego powiązania z istniejącą płatnością, bez podwójnego kosztu.

**Architecture:** Rozszerzamy istniejące domeny documents i finance w modularnym monolicie. Documents zachowuje prywatny oryginał, wykonuje ograniczoną konwersję/OCR i przechowuje wersjonowane propozycje; finance jest właścicielem rejestru, alokacji i projekcji do cashflow. Żadna faza odczytu lub zatwierdzenia faktury nie zapisuje ledger; tylko osobna potwierdzona akcja płatności używa obecnego serwisu księgi.

**Tech Stack:** Python3.12, FastAPI, SQLAlchemy async/PostgreSQL16, Alembic, ARQ/Stirling, Pillow+pillow-heif; React18/TS/Vite/TanStack Query, Vitest, Playwright.

**Spec:** `docs/superpowers/specs/2026-10-28-financial-document-workflow-design.md`

## Stan realizacji — 2026-10-30

Checkboxy w opisach niżej pochodzą z zaakceptowanej instrukcji implementacji;
nie zastępują poniższego statusu i dowodów kolejnych review.

- [x] Task1 — HEIC/HEIF, oryginał i podgląd; review po poprawkach.
- [x] Task2 — modele i migracja; rzeczywisty test Alembic, review po poprawkach.
- [x] Task3 — propozycje, retry/recovery OCR; review po poprawkach.
- [x] Task4 — rejestr, źródła i duplikaty; review po poprawkach.
- [x] Task5 — alokacje i płatności PLN; review po poprawkach.
- [x] Task6 — guardy księgi/metadanych/Actual; review po poprawkach.
- [x] Task7 — projekcja, coverage i konflikty; review po poprawkach.
- [x] Task8 — upload i review UI; review po poprawkach.
- [x] Task9 — rejestr, rozliczenia i source union UI; review po3rundach poprawek.
- [x] Task10 — końcowy gate oprogramowania i task-review po poprawkach;941backend/
  278frontend/75E2E+1skip PASS, parserDocker i syntetyczna migracja/restore PASS.
- [x] Całościowy przegląd gałęzi —4Important domknięte jedną poprawką0524cb9;
  scopedreview clean, finalgate949backend/279frontend/75E2E+1skip PASS.
- [ ] Certyfikacja aparatu/galerii Android/iPhone — **BLOCKED**, brak urządzeń.
- [ ] Deploy/import/przygotowanie dokumentów użytkownika — poza zgodą i poza tą realizacją.

Dowody: `docs/audits/2026-10-28-financial-document-workflow-verification.md`.
Brak zgody na push/merge, migrację produkcji, deploy lub rzeczywiste importy.

## Global Constraints

- Tylko dodawanie w aplikacji, bez Google Drive i innych integracji.
- W pierwszym wydaniu: faktury zakupowe dodatnie i paragony, upload PDF/JPEG/PNG/HEIC/HEIF.
- PostgreSQL jest źródłem prawdy; kwoty BIGINT w najmniejszej jednostce, bez float.
- Rejestr PLN/EUR/USD, alokacje i nowe płatności tylko PLN; brak domyślnego FX.
- Upload/OCR/rejestracja faktury NIE tworzą postingów i nie zmieniają sald/budżetu.
- Oryginały prywatne i bez nadpisywania; HEIC→JPEG lokalnie, w ograniczonym procesie.
- Istniejące uploady bez automatycznego backfill/OCR/LLM w migracji; ręczne dane działają bez LLM.
- Każda mutacja owner-scoped, walidowana, audytowana, idempotentna; nowe expense min2 postings/suma0.
- Bez nowych integracji bankowych, wysyłania przelewów, podatków, korekt/zwrotów/rat faktur lub Q7 w tym wydaniu.
- Brak deployu/migracji na produkcji/importu/korekt danych bez osobnej zgody użytkownika.
- To plan do przeglądu przed implementacją; żaden checkbox nie oznacza wykonanego kodu.

## Review Focus

1. Telefon zgłasza pusty/generic MIME lub image/heif dla .heic, zawiera EXIF orientation i GPS: rozpoznać treść, zachować oryginał, nie ujawnić GPS w pochodnej (Task1).
2. Foto i PDF tej samej faktury, równoległe zatwierdzenie oraz stary processed Inbox: jeden zakup, jawne ostrzeżenia, brak przepisywania historii i kosztu (Tasks3–4).
3. Jedna płatność pokrywa dwie faktury w dwóch sesjach DB: suma alokacji nigdy nie przekracza postingu, retry nie tworzy drugiego kosztu (Task5).
4. Faktura zastępuje regułę cykliczną, jest częściowo zapłacona albo zaległa sprzed kilku miesięcy: dokładnie jedna pozostałość i brak potwierdzenia starą ścieżką (Task7).
5. Awaria OCR/LLM, duży lub uszkodzony HEIC, brak FX/konta/terminu: jawny stan/wyłączenie z prognozy, brak fałszywego „opłacono” lub pełnej płynności (Tasks1,3,7,9).

---

## Workspace, komendy i zakres plików

Przed realizacją użyć using-git-worktrees. Obecna gałąź ma niezacommitowane dokumenty
audytów/specyfikacji: nie przenosić/commitować ich bez sprawdzenia, nie stashować
automatycznie. Odizolowany worktree ma zawierać zatwierdzony spec i ten plan oraz
ostatni uzgodniony kod, nie prywatne pliki bankowe. Bazowy HEAD potwierdzić przed pracą.

Komendy projektu `/test`, `/lint`, `/typecheck`, `/migration`, `/migrate`, `/docs`;
ich definicje są w `.opencode/command/`. Uruchamiać dla WYBRANEGO worktree, nie
przypadkiem `/opt/finanse` zamiast edytowanej gałęzi. Gdy harness nie wystawia komendy,
wykonać jej udokumentowaną treść w worktree i jawnie odnotować fallback. RED oznacza
porażkę nowego testu z oczekiwanej przyczyny, nie awarię środowiska lub brak PostgreSQL.
Przed każdym commitem implementacji `/lint`, `/typecheck`, `/test`; dla integracji
nie akceptować skipów zamiast działania lokalnej bazy `finanse_test`. Nie używać produkcji.

Mapa odpowiedzialności:
- `documents/image_process.py`, `images.py`: parser/konwerter oraz ograniczony async transport;
- `documents/models.py`, `review_schemas.py`, `review_service.py`, `review_router.py`: propozycje i ręczne ponowienie;
- `finance/models.py`: nowe modele rejestru, źródeł, alokacji, coverage i idempotencji;
- `finance/bills_schemas.py`, `bills.py`, `bill_payments.py`, `bill_coverage.py`, `bills_router.py`: wyłącznie logika faktur/paragonów;
- `finance/document_guards.py`: wspólna ochrona istniejących rekordów ledger/reguł;
- `finance/bill_forecast.py` plus obecny `cashflow.py`: jedna projekcja do Nadchodzących;
- `frontend/src/api/bills.ts`, `pages/FinanceDocuments.tsx`, `components/documents/*`, `components/finance/bills/*`: UI;
- istniejące modele/serwisy/worker/routery zmieniać wąsko; nie przepisywać całego documents/finance.

## Zamrożone kontrakty między zadaniami

API pod `/api/finance/bills` (nazwa techniczna, UI „Faktury i paragony”). `id` to UUID.
`GET` list/detail/candidates nie zmienia żadnych danych. `POST/PATCH/DELETE` używa
CSRF i `Idempotency-Key`; w body mutacji istniejącego rekordu `expected_version:int`.
Przy błędzie wersji/payloadu/konkurencji409; cudzy ID404; domenowa walidacja422;
limity413; nieudostępnione parsery503. Brak SQL/treści OCR w błędach.

Wspólne typy w `bills_schemas.py`:
- `BillKind=invoice|receipt`, `BillReview=draft|approved|rejected`;
- `PaymentDeclaration=unknown|payable|declared_paid`, `BillLifecycle=active|archived|cancelled`;
- `ReconciliationState=none|partial|full` i `paid_minor`, `remaining_minor` są wyliczane,
  nie edytowane swobodnie. Draft może mieć nieznany typ/kwotę/walutę, approved musi mieć
  dodatnią `total_minor:int <=9007199254740991`, currency PLN/EUR/USD, supplier/description.
- `BillApprove`: version, kind, supplier_name, optional supplier_tax_id/number/issue_date/
  sale_date/due_date/payee_iban/category_id/payment_account_id, total_minor, currency,
  declaration; receipt domyślnie declared_paid. `iban` propozycja, bez zlecenia przelewu.
- `BillResponse`: powyższe + lifecycle/review/version, paid/remaining/reconciliation,
  sources[], allocations[], extraction_revision_id?, coverage?, forecast_exclusion_reasons[].
- `AllocationCreate`: version, posting_id, amount_minor; `BillPaymentCreate`: version,
  account_id, category_id, payment_date, amount_minor, description, confirm_new_payment:true.
- `CoverageDecision`: version, choice=replace|separate, scheduled_item_id?, occurrence_date?.
- `BillCandidate`: transaction_id, posting_id, date, account, amount_minor, unallocated_minor,
  reasons[], legacy_inbox_reference?, recurring_conflicts[]. Nie auto-paid.
- `BillUpdate`: edytowalne pola BillApprove opcjonalne + wymagane expected_version;
  pominięcie!=null, kind/currency/total/supplier nie mogą być null w approved.
  `BillPage` i `BillCandidatePage`: items[], total:int, limit:int, offset:int.
  `BillFilters`: kind?, review?, declaration?, lifecycle?, due_from?, due_to?, query?.
  `ReviewSuggestion`/`ReviewResponse` w review_schemas.py: typ dokumentu (w tym
  unsupported/multiple), extracted fields nullable + provenance per field, status/error_code,
  revision:int, id:UUID, document_id:UUID; bez storage_path i sekretów LLM.
- `MutationContext`: idempotency_key:str, performed_by:str='human'; zdefiniowany w
  `bills_schemas.py`. API bierze klucz z nagłówka; serwisy nigdy nie commitują samodzielnie.

Idempotencja zapisywana w `FinanceCommandReceipt`: owner+action+key unique,
request hash oraz wynik (`entity_id`, `result_ids`, wersja i snapshot publicznego
response_json), bez pełnego OCR/ścieżek storage. Replay oddaje zapisany rezultat,
nie aktualny stan po późniejszych operacjach; klient po sukcesie odświeża GET.
Każdy router mutation wywołuje serwis z context i zapisuje commit raz z audytem;
ten sam klucz/payload daje ten sam rezultat także po crash po commicie.
Funkcje zadań przyjmują `db:AsyncSession`, `user_id:UUID` jako pierwsze dwa argumenty.

### Task 1: Bezpieczne zdjęcia z telefonu i autoryzowany oryginał

**Files:** Create `backend/app/documents/images.py`, `backend/app/documents/image_process.py`,
`backend/tests/test_documents/test_images.py`, `backend/tests/test_documents/test_originals.py`.
Modify `validation.py`, `validation_process.py`, `router.py`, `schemas.py`, `service.py`, `worker.py`,
`backend/app/config.py`, `backend/pyproject.toml`, `backend/requirements.txt`.

**Interfaces:** `images.normalize_image(content:bytes, mime:str, *, thumbnail:bool=False)->bytes`
async, zwraca JPEG; `detect_document_mime_type` zachowuje obecny kontrakt, rozszerza typy.
`GET /api/documents/{id}/original` i `/preview`: właściciel, `no-store,nosniff`,
oryginał jako attachment; PDF preview autoryzowany inline, obraz preview to JPEG.

- [ ] **RED:** dodać testy `test_heic_original_unchanged_and_preview_jpeg`,
  `test_phone_generic_mime_detected_not_filename_trusted`, `test_orientation_without_gps`,
  `test_conversion_timeout_keeps_saved_original`, `test_oversized_pixels_rejected`,
  `test_foreign_owner_cannot_read_original`. Syntetyczne JPEG/PNG/HEIC, żadnych dokumentów bankowych.
  Asercje: SHA original przed=po, JPEG magic, prawidłowe wymiary orientacji, brak EXIF GPS;
  obcy user404 i brak storage_path; malformed pod etykietą HEIC422/400 bez zapisów.
- [ ] **RUN RED:** `/test`; nowe testy muszą wskazać brak obsługi/endpointów, nie timeout bazy.
- [ ] **IMPLEMENT:** `pillow-heif==1.8.1` w obu deklaracjach zależności (PyPI28.10:
  Python>=3.10, cp312 Linux x86_64/aarch64 wheels). W tasku sprawdzić podatności
  i kompatybilność z Pillow przed instalacją; jeśli niedostępne/niebezpieczne, zatrzymać,
  nie kompilować dowolnego kodeka w produkcji. Plugin rejestrować tylko w procesie
  parsera (`register_heif_opener(thumbnails=False)`), nie w procesie FastAPI.
- [ ] **IMPLEMENT:** HEIC/HEIF rozpoznawane po kontenerze/dekoderze, kanoniczne
  `image/heif`; dopuszczalne aliasy image/heic/image/heif. Pusty lub octet-stream MIME
  przyjąć tylko gdy ograniczony parser wykryje dopuszczony obraz/PDF, nigdy po nazwie.
  Zadeklarowany sprzeczny konkretny MIME nadal odrzucić. Nie przyjmować AVIF/SVG/GIF/RAW.
  `store_document` zapisuje wykryty kanoniczny MIME zwrócony przez walidator, nie
  niezaufaną wartość nagłówka. Nazwa `blob`/brak rozszerzenia z kamery nie blokuje uploadu.
- [ ] **IMPLEMENT:** osobny proces z obecnymi RLIMIT/timeout/semaforem, brak DB/env
  aplikacji, ograniczone wyjście binarne do `DOCUMENT_IMAGE_OUTPUT_MAX_BYTES` (domyślnie
 20MiB), IPC nie używa obecnego limitu4096 z małego JSON parsera. Walidator nadal
  zwraca tylko mały JSON. JPEG quality konfigurowane `DOCUMENT_JPEG_QUALITY=90`,
  preview max edge `DOCUMENT_PREVIEW_MAX_EDGE=1600`, max piksele obecne25M z settings.
  EXIF transpose, RGB na białym tle, bez EXIF/XMP w pochodnej; bez zmiany oryginału.
  HEIF używa jawnego primary image; pomocnicze depth/thumbnail nie są inną fakturą;
  sekwencje/animacje bez jednoznacznego primary odrzucić czytelnym błędem.
- [ ] **IMPLEMENT:** pochodna tylko ograniczona pamięć/tmp0700 z cleanup, bez trwałego
  drugiego archiwum/quota drift. `/preview` ma limit żądań i rozmiaru, brak publicznego
  cache, filename bez header injection. Worker konwertuje JPEG→PDF zamiast HEIC→Stirling.
- [ ] **GREEN:** `/test`, `/lint`, `/typecheck`; test parsera w zbudowanym lokalnym
  obrazie Python3.12 (nie tylko venv), brak wycieku subprocess/tmp i stderr; niezależny review obrazów.
- [ ] **COMMIT:** wyłącznie Task1, `feat: obsłuż zdjęcia HEIC i prywatny podgląd dokumentów`.

### Task 2: Relacyjny rejestr i addytywna migracja

**Files:** Modify `backend/app/finance/models.py`, `backend/app/main.py`,
`backend/app/documents/models.py`; Create
`backend/app/finance/bills_schemas.py`, `backend/app/documents/review_schemas.py`,
`backend/tests/test_finance/test_bill_models.py`, `backend/tests/test_documents/test_review_models.py`,
`backend/tests/test_finance/test_bill_migration.py`; nowa migracja przez `/migration`.

**Interfaces:** modele `FinancialDocument`, `FinancialDocumentSource`,
`DocumentPaymentAllocation`, `RecurringOccurrenceCoverage`, `FinanceCommandReceipt`
w finance/models.py i `DocumentExtractionRevision` w documents/models.py;
typy z sekcji kontraktów. `BillResponse` nie zawiera ścieżek storage ani tekstu OCR.

- [ ] **RED:** `test_source_unique_even_after_archive`, `test_allocation_positive_and_unique`,
  `test_coverage_occurrence_unique`, `test_bill_amount_safe_integer`,
  `test_migration_preserves_old_rows_without_backfill`; approved bez kwoty/waluty
  nie przechodzi walidacji, draft może być niekompletny. DDL w integration test na lokalnym DB.
- [ ] **RUN RED:** `/test`, sprawdzić przyczyny brakujących modeli, bez skipów integracji.
- [ ] **IMPLEMENT:** FinancialDocument fields zgodnie z kontraktem, category/account nullable
  FK RESTRICT; review/declaration/lifecycle rozdzielone, wersja>=1. Source FK RESTRICT
  na Document i rejestr, document_id UNIQUE w całym lifetime. Allocation amount>0,
  FK posting i bill RESTRICT, unique(bill_id,posting_id). Coverage unique(user,item,date),
  unique(bill_id) i choice separate jako decyzja rekordu bez coverage. Command receipt
  unique(owner,action,key); extraction revision unique(document_id,revision), status
  pending/processing/ready/incomplete/error, data JSON propozycji+pole provenance+wersja parsera.
  Wszystkie tabele user_id, FK-owner sprawdzane także w serwisach, indeksy user/date/status.
- [ ] **IMPLEMENT:** model import registration w main/migrations; DB CHECK sum/enum,
  integer signed JS-safe przy zatwierdzeniu i alokacji; kasowania źródeł i postingów
  nie kaskadują historii. Zero kopii w ScheduledFinanceItem, zero tabel sald wyliczanych.
- [ ] **GENERATE:** `/migration "financial documents and payment allocations"`
  na pustej lokalnej bazie odpowiadającej aktualnemu head (obecnie c2d7e9a4f801).
  Wygenerowano w Task2: `backend/migrations/versions/7f8ce92bda94_financial_documents_and_payment_.py`,
  revision7f8ce92bda94, predecessor c2d7e9a4f801. Review wykonania jeszcze w toku. Review autogenerate:
  tylko addytywne tabele/indeksy/checks, żadnych DROP/UPDATE/LLM/OCR.
- [ ] **GREEN:** migracja lokalnie przez `/migrate`, rollback test wyłącznie w disposable
  DB, hash starych synthetic rows przed/po; `/lint`, `/typecheck`, `/test`.
- [ ] **COMMIT:** `feat: dodaj modele rejestru dokumentów i rozliczeń`.

### Task 3: Wersjonowane rozpoznanie i obsługa istniejących uploadów

**Files:** Create `backend/app/documents/review_service.py`, `review_router.py`,
`backend/tests/test_documents/test_review.py`, `test_review_worker.py`;
Modify `extractor.py`, `worker.py`, `router.py`, `backend/app/config.py`, `backend/app/main.py`.

**Interfaces:** async `prepare_review(db,user_id,document_id:UUID,*,refresh:bool,context:MutationContext)->DocumentExtractionRevision`;
async `get_review(db,user_id,document_id:UUID)->ReviewResponse|None`;
`extract_review_data(text:str)->ReviewSuggestion` async bez dostępu do DB.
`GET /api/documents/{id}/review`, `POST /{id}/review/prepare`, `POST /{id}/retry-ocr`.

- [ ] **RED:** `test_existing_done_upload_uses_saved_text`, `test_llm_error_is_visible_not_no_invoice`,
  `test_reextract_preserves_approved_fields`, `test_statement_or_multibill_never_single_expense`,
  `test_legacy_processed_inbox_not_rewritten`, `test_missing_text_requires_explicit_ocr_retry`.
  Asercje: revision+1 na jawne refresh; brak ledger i brak nowego równoległego Inbox expense;
  LLM timeout daje error/incomplete, ręczne review nadal dostępne; obcy doc404.
- [ ] **RUN RED:** `/test` z kontrolowanym fake LLM/OCR, żadnych zewnętrznych wywołań.
- [ ] **IMPLEMENT:** schemat rozpoznaje invoice/receipt/statement/loan_schedule/other/multiple;
  kwoty jako dokładny decimal-string źródłowy + currency, parsowanie do cents deterministyczne.
  Brak danych=null; daty ścisłe ISO; obce instrukcje w OCR pozostają danymi. Wynik zbyt
  długi/niezgodny schematem=incomplete, nigdy silent detected=false z done jako sukces biznesowy.
- [ ] **IMPLEMENT:** dedykowany ARQ job `prepare_document_review` z blokadą i recovery
  pending revision, bez network przy locku globalnego upload quota. Nowe OCR przygotowuje
  revision, nie Inbox expense; wyjątki financial extraction nie zmieniają OCR done,
  ale mają osobny widoczny stan. Obecne `create_inbox_from_document` zostaje dla zgodności
  starych odczytów/testów, nie jest równoległą ścieżką nowych faktur.
- [ ] **IMPLEMENT:** explicit prepare starych PDF używa zapisanego tekstu; retry OCR
  jedynie na żądanie i z limitami obecnego workera. Brak masowego backfill i automatycznego
  retry wyczerpanych plików przy liście/GET. LLM model/key z config, informacja o dostawcy
  do UI; nie wdrażać nowej usługi OCR. Historyczny processed Inbox zachować, odsyłacz
  tworzony przy rejestracji w Task4, target tylko kandydat do Task5.
- [ ] **GREEN:** `/lint`, `/typecheck`, `/test`; retry revision po awarii nie dubluje
  propozycji, źródła pozostają identyczne SHA. Ręczna ścieżka działa bez klucza LLM.
- [ ] **COMMIT:** `feat: przygotuj wersjonowane propozycje dokumentów do sprawdzenia`.

### Task 4: Zatwierdzanie rejestru, źródła i duplikaty biznesowe

**Files:** Create `backend/app/finance/bills.py`, `bills_router.py`,
`backend/tests/test_finance/test_bills.py`, `test_bill_sources.py`, `test_bill_routes.py`;
Modify `bills_schemas.py`, `backend/app/finance/router.py`, `backend/app/documents/service.py`.

**Interfaces:** async `prepare_bill(db,user_id,document_id:UUID,*,context)->BillResponse`;
`approve_bill(db,user_id,bill_id:UUID,data:BillApprove,*,context)->BillResponse`;
`update_bill(db,user_id,bill_id:UUID,data:BillUpdate,*,context)->BillResponse`;
`get_bill`, `list_bills(...,limit:int,offset:int,filters:BillFilters)->BillPage`;
`find_duplicate_bills(...,data:BillApprove)->list[DuplicateCandidate]`;
`attach_source(...,bill_id,document_id,expected_version,*,context)->BillResponse`;
`set_bill_lifecycle(...,bill_id,lifecycle,expected_version,*,context)->BillResponse`.

- [ ] **RED:** `test_approve_invoice_has_zero_posting_delta`,
  `test_receipt_declared_paid_not_reconciled`, `test_photo_pdf_attach_one_purchase`,
  `test_two_sessions_prepare_same_source_one_bill`, `test_processed_legacy_target_preserved`,
  `test_archive_reopen_reuses_record`, `test_linked_original_delete_rejected`.
  Asercje: invoice10000=>paid0/remaining10000; source count2 przy attach dwu plików;
  duplicate warning nie scala automatycznie; drugi owner nie widzi candidates.
- [ ] **RUN RED:** `/test`; odróżnić rollback błędu od asercji stanu rejestru.
- [ ] **IMPLEMENT:** record draft+source jeden lifetime, prepare idempotentny;
  approved waliduje daty/kwoty/owner links, kontroluje optymistyczną version i audyt.
  Business duplicate candidates: znormalizowany NIP+numer+waluta+kwota/data; słaby
  fallback supplier+kwota/data wyłącznie ostrzega. Dowolny nowy record mimo ostrzeżenia
  wymaga w body `duplicate_decision=separate`; attach to istniejący purchase to osobna akcja.
- [ ] **IMPLEMENT:** przeniesienie źródła tylko z draft/rejected bez alokacji/coverage;
  lock obu bill UUID w porządku, źródło odpięte i przypięte atomowo. Nie zabierać ostatniego
  źródła approved, nie scalać dwóch opłaconych rekordów. Archive/cancel zachowuje źródła,
  linki i coverage; aktualizacja waluty/kwoty poniżej paid przy alokacjach422.
- [ ] **IMPLEMENT:** idempotency helper `_run_bill_command(db:AsyncSession,user_id:UUID,
  action:str,key:str,payload:dict[str,object],operation:Callable[[],Awaitable[BillResponse]])->BillResponse`
  w bills.py: owner-scoped advisory command lock, canonical payload hash, replay result
  z CommandReceipt,409 dla innego payloadu. Actor i identyfikatory w audit, bez całego OCR.
  Dokument DELETE i istniejący router używają guard source; legacy Inbox json pozostaje
  bez przepisywania statusu processed, odsyłacz przechowuje rejestr jako osobną relację.
- [ ] **GREEN:** `/lint`, `/typecheck`, `/test`; puste numery/datę można poprawić ręcznie,
  nie zatwierdzić bez kwoty/waluty; powtórzony command wraca do tego samego wyniku.
- [ ] **COMMIT:** `feat: dodaj rejestr faktur i paragonów bez księgowania`.

### Task 5: Jawne częściowe rozliczanie i nowa płatność PLN

**Files:** Create `backend/app/finance/bill_payments.py`,
`backend/tests/test_finance/test_bill_payments.py`, `test_bill_payment_concurrency.py`;
Modify `bills_router.py`, `bills_schemas.py`.

**Interfaces:** async `get_payment_candidates(db,user_id,bill_id:UUID,*,limit:int,offset:int)->BillCandidatePage`;
`allocate_payment(db,user_id,bill_id,data:AllocationCreate,*,context)->BillResponse`;
`unlink_payment(db,user_id,bill_id,allocation_id:UUID,expected_version:int,*,context)->BillResponse`;
`record_bill_payment(db,user_id,bill_id,data:BillPaymentCreate,*,context)->BillResponse`.
PUT/POST na `/bills/{id}/allocations`, DELETE `/allocations/{id}`, POST `/payments`.

- [ ] **RED:** dodać test z fixtures bill10000 i expense10000:
  `allocate4000=>paid4000/remaining6000`, drugi posting6000=>full, unlink=>partial;
  posting7000 użyty w dwóch fakturach równolegle5000+5000=>jeden sukces/drugi409/422,
  suma<=7000. Parametryzować pending/future/transfer/FX/income/other-owner=>odrzucenie.
- [ ] **RED:** `test_record_payment_retry_one_expense`, `test_audit_failure_rolls_back_payment`,
  `test_bank_card_purchase_not_repayment_transfer`, `test_legacy_target_candidate_only`,
  `test_hidden_cross_owner_capacity_not_exposed`; euro bill nie dopasowuje PLN postingu.
- [ ] **RUN RED:** `/test` na prawdziwych osobnych AsyncSession, commit-aware race,
  bez monkeypatcha `with_for_update`; timeout testu jest porażką, nie PASS.
- [ ] **IMPLEMENT:** tylko expense z jednym kontowym debetem PLN, data<=local_today,
  nie pending, balanced, kategorie mogą być podzielone; historical inactive account
  można linkować, nowy expense wymaga aktywnego PLN. Pojemność source_amount==base_amount_pln,
  fx_rate1 i brak loan links. Candidate kolejność: jawny legacy target, potem kwota/date
  blisko terminu (okno z config), paginacja i reasons; użytkownik może wyszukać starszy.
- [ ] **IMPLEMENT:** wspólny porządek blokad: owner command advisory → owner bill
  allocation advisory (dla wszystkich bill mutation jednego ownera) → bill UUID ASC →
  FinancialTransaction UUID ASC → Posting UUID ASC. Task6 ledger mutatory biorą ten
  sam owner allocation advisory PRZED row lockami. Po lockach refresh ORM i liczenie
  sum ponownie, w tej transakcji DB. Nie wyliczać pojemności z cache/GET.
- [ ] **IMPLEMENT:** unlink alokacji audytowany, nie usuwa expense. Record payment
  buduje TransactionCreate poprzez `transactions.create_transaction`, source
  `document_payment`, min2 postings (konto debit/kategoria credit), kwota i data jawne;
  replay chroniony receipt Task4, rollback obejmuje expense+alokację+audit. Nie zleca przelewu.
- [ ] **GREEN:** `/lint`, `/typecheck`, `/test`; property test wielu sekwencji alokacji,
  niezmienność ledger przy samym allocate/unlink. Nie zmieniać budżetowości kont.
- [ ] **COMMIT:** `feat: rozliczaj faktury istniejącymi płatnościami bez duplikatów`.

### Task 6: Ochrona istniejącej księgi i metadanych

**Files:** Create `backend/app/finance/document_guards.py`,
`backend/tests/test_finance/test_bill_guards.py`; Modify `transactions.py`, `entities.py`,
`currency_correction.py` i znalezione istniejące mutatory importera Actual (najpierw grep),
`bills.py`, `bill_payments.py`. Nie uruchamiać operatorowej korekty walut.

**Interfaces:** async `lock_document_mutations(db,user_id:UUID)->None` (advisory z Task5);
`guard_allocated_transaction_change(db,user_id,transaction_id:UUID,changes:dict)->None`;
`guard_bill_account_change(db,user_id,account_id:UUID,changes:dict)->None`.

- [ ] **RED:** `test_linked_expense_delete_rejected`, `test_date_pending_posting_change_rejected`,
  `test_same_value_patch_idempotent`, `test_currency_correction_refuses_allocated_posting`,
  `test_race_delete_vs_allocate_has_no_dangling_link`; audit/history unchanged po odmowie.
- [ ] **RUN RED:** `/test`; test każdego faktycznego istniejącego mutatora znalezionego grep,
  nie tylko REST. Nie wymyślać nowego endpointu edycji postingów.
- [ ] **IMPLEMENT:** wymagane blokady przed istniejącymi locks, RESTRICT FK jako drugi
  mur; guard przed kasowaniem/zmianami dat/pending/kwot/walut/kierunku/konta. Description
  może się zmienić, nie tożsamość wydatku. Account/category DELETE RESTRICT gdy użyte
  przez rejestr, update waluty konta zablokowany przy referencji. Bez odmowy historycznego
  linku tylko dlatego, że konto jest inactive. Czysty upload/GET nie bierze tych blokad.
- [ ] **GREEN:** `/lint`, `/typecheck`, `/test`, istniejące testy loan guards/currency/Actual
  bez regresji; jawna lista przeszukanych mutatorów w notatce review.
- [ ] **COMMIT:** `fix: chroń płatności powiązane z dokumentami`.

### Task 7: Jedna pozostałość w Nadchodzących i pokrycie reguły

**Files:** Create `backend/app/finance/bill_coverage.py`, `bill_forecast.py`,
`backend/tests/test_finance/test_bill_forecast.py`, `test_bill_coverage.py`;
Modify `cashflow.py`, `schemas.py`, `bills_router.py`, `bills_schemas.py`.

**Interfaces:** async `decide_coverage(db,user_id,bill_id,data:CoverageDecision,*,context)->BillResponse`;
`get_coverage_candidates(db,user_id,bill_id)->list[CoverageCandidate]`;
`unlink_coverage(...,bill_id,expected_version,*,context)->BillResponse`;
`project_bill_cashflows(db,user_id,*,today:date,horizon_end:date)->BillProjection`.
BillProjection: entries[], day_changes_pln:dict[date,int], exclusions[], covered_occurrences:set[(UUID,date)].

- [ ] **RED:** `test_bill10000_vs_schedule10000_replace_once`,
  `test_invoice12000_replaces_estimate10000_only_this_occurrence`,
  `test_paid4000_forecast6000`, `test_old_overdue_once_today`,
  `test_unknown_date_account_fx_excluded_with_reason`,
  `test_legacy_confirm_covered_occurrence_refuses`, `test_archive_keeps_coverage_tombstone`.
  Jawne daty2026-10-31,2026-08-01, today2026-10-28; listopadowa reguła niezmieniona.
- [ ] **RUN RED:** `/test`; nie aktualizować fixtures globalnie, aby ukryć regresję cashflow.
- [ ] **IMPLEMENT:** konkretna date occurrence, eligible candidates tego samego ownera,
  typu expense, wskazanego konta/kategorii i miesiąca terminu (nie wymaga równej kwoty).
  `replace` suppress tylko jeden item/date; `separate` jawna decyzja z wersją. Gdy kandydaci
  i brak decyzji: invoice entry excluded, powód coverage_unresolved; nie blokować samego
  rejestru. Pokryte occurrence nie potwierdza się starym endpointem. Guard update/delete
  reguły przy coverage; świadome unlink pokazuje przywrócenie estymaty. Archive/cancel
  pozostawia coverage z jawnym statusem source w odpowiedzi, nie cichy zanik.
- [ ] **IMPLEMENT:** forecast source discriminated union: recurring ma scheduled_item_id,
  financial_document ma financial_document_id i oba mają source_key, due_date nullable,
  currency, amount_minor, amount_pln nullable, included_in_forecast, exclusion_reasons.
  Zachować istniejące recurring pola/statusy; wszystkie konsumujące komponenty aktualizuje
  Task9. Jednorazowe faktury nie iterują miesięcznie. Zaległe od dowolnego miesiąca raz na dziś,
  PLN payable approved active positive remaining z kontem active budget PLN; inne widoczne
  z powodem. declared_paid/unknown nie odjąć w prognozie. Future poza horyzontem nie w sumach.
- [ ] **IMPLEMENT:** jawne coverage ma pierwszeństwo nad matcherem. `_matching_actuals`
  nie używa transakcji z alokacją dokumentową; ostrzeżenie konfliktu przy candidates/allocate
  z Task5 zawiera skutek przed/po. W read-only GET nie zapisywać oceny konfliktu.
  Forecast dodaje `has_excluded_obligations`/reasons; safe limit opisany jako niepełny
  przy pominiętych kwotach, bez udawania pełnego bezpieczeństwa. Zmiany wymagają integration
  regression dla istniejących scheduled items/Today/Advisor używających schematu forecast.
- [ ] **GREEN:** `/lint`, `/typecheck`, `/test`; otwarcie salda i raport wydatków bez zmian,
  allocation już w ledger nie odejmowany drugi raz. PLN/EUR nigdy sumowane.
- [ ] **COMMIT:** `feat: uwzględnij faktury w nadchodzących bez podwójnych estymat`.

### Task 8: Upload z telefonu i sprawdzanie starych/nowych dokumentów

**Files:** Modify `frontend/src/api/documents.ts`, `components/DocumentUpload.tsx`,
`DocumentList.tsx`, `DocumentViewer.tsx`, `pages/Documents.tsx`, `pages/Inbox.tsx`;
Create `components/documents/DocumentReview.tsx`, `DocumentSources.tsx`,
`frontend/src/api/bills.ts`, `components/documents/DocumentReview.test.tsx`;
Modify `frontend/src/pages/Documents.test.tsx`.

**Interfaces:** TanStack hooks `useDocumentReview(id)`, `usePrepareDocumentReview()`,
`usePrepareBill()`, `useApproveBill()`, `useAttachBillSource()` z kontraktami backend;
`DocumentReview({documentId:string,onClose:()=>void})` bazuje na Dialog.

- [ ] **RED (Vitest):** `camera_requests_environment_and_accepts_heic`,
  `multi_upload_shows_per_file_success_failure`, `old_pdf_can_prepare_without_upload`,
  `review_shows_llm_error_and_manual_fields`, `approve_has_no_payment_copy`,
  `inbox_legacy_refers_to_document_without_enabling_transaction_conversion`.
  Asercje: kilka files=>sekwencyjne request per plik, pending nie gubi wyboru, ponowienie
  tylko błędnego; data/kwota preview porównana z autoryzowanym oryginałem, input nie ufa nazwie.
- [ ] **RUN RED:** `/test`; zachować istniejące upload/list/error tests.
- [ ] **IMPLEMENT:** kamera accept JPEG/PNG/HEIC/HEIF + capture environment; galeria
  i multiple file chooser osobne, CSV nie jest akceptowany w tym uploadzie faktur.
  Nie konwertować HEIC przez canvas przed uploadem (utrata oryginału). Limity pokazane
  z API/config capability endpoint, nie nowy hardkod zmienny między klientem/serwerem.
- [ ] **IMPLEMENT:** oryginał fetch authenticated blob + revoke object URL na close,
  HEIC pokazuje JPEG preview, nie wymaga przeglądarkowego dekodera. Usunąć storage_path
  z publicznych typów DocumentResponse/DocumentData; UI pobiera blob przez ID. OCR i review status
  osobno; edycja pełnych pól z walidacją, provenance OCR/ręcznie, kategoria/konto opcjonalne.
  Duplikat daje attach/separate, nie automerge. Odrzucone/unknown/multiple poza rejestrem
  finansowym z instrukcją. Button „Sprawdź dane”, nie „Zaksięguj”; wyjaśnienie zewnętrznego
  LLM i manual fallback, zero raw technical prompt. Żadne approve nie wywołuje /payments.
- [ ] **GREEN:** `/lint`, `/typecheck`, `/test`; a11y klawiatura/dialog focus, dark/light,
  viewport375/1440, brak tokenów w URL i publicznego cache oryginału.
- [ ] **COMMIT:** `feat: dodaj sprawdzanie faktur i zdjęć z telefonu`.

### Task 9: Rejestr, rozliczanie i akcje w Nadchodzących

**Files:** Create `frontend/src/pages/FinanceDocuments.tsx`, `.test.tsx`,
`frontend/src/components/finance/bills/BillRegister.tsx`, `BillDetail.tsx`,
`BillPaymentDialog.tsx`, `BillCoverageDialog.tsx`, `BillPaymentDialog.test.tsx`;
Modify `frontend/src/api/bills.ts`, `api/finance.ts`, `App.tsx`,
`components/finance/FinanceTabs.tsx`, `pages/FinanceCashflow.tsx`,
`components/finance/CashflowForecast.tsx`, `pages/FinanceCashflow.test.tsx`.

**Interfaces:** route `/finances/documents`, optional `?bill=<UUID>` otwiera detail;
DocumentReview linkuje do tego rejestru. `useBills(filters)`, `useBill(id)`,
`useBillCandidates(id)`, `useAllocateBillPayment()`, `useUnlinkBillPayment()`,
`useRecordBillPayment()`, `useBillCoverage()`; invalidacja documents/review/bills,
cashflow i transactions/budgets po nowym expense, nie tylko lista faktur.

- [ ] **RED:** `register_separates_declared_paid_from_reconciled`,
  `partial_payment_updates_remaining_and_forecast`, `record_is_not_send_bank_transfer`,
  `recurring_source_only_opens_legacy_confirm`, `bill_source_opens_bill_not_schedule`,
  `unknown_currency_total_not_rendered_as_pln`, `stale_version_requires_refresh`.
- [ ] **RUN RED:** `/test`; `canConfirmSuggestion` oraz source_key unikalne również
  dla tej samej reguły w dwóch miesiącach i wielu faktur (nie key undefined).
- [ ] **IMPLEMENT:** tabela/karty rejestru: sprzedawca/numer/data/termin/waluta/total/
  pozostało/deklaracja/uzgodnienie; filtry i paginacja, wyraźne zaległe i brak terminu.
  Detail: sources original/preview, częściowe allocation history, audited archive/reopen,
  conflict warnings. Kwoty per waluta, nie jedna suma PLN ze wszystkiego.
- [ ] **IMPLEMENT:** podstawowa akcja „Powiąż płatność”; tworzenie expense osobna
  „Zarejestruj płatność”, pokazanie istniejących candidates i „nie zleca przelewu”.
  EUR/USD przyciski wyłączone z uzasadnieniem, konto karty/gotówka prawidłowo opisane.
  Każda mutacja ma stabilny idempotency key dla retry, nowy klucz dla nowej decyzji;
 409 nie gubi pól, wymaga reload porównania, nigdy cichy retry z innym payloadem.
- [ ] **IMPLEMENT:** cashflow discriminated union z Task7, link źródła/rozliczenia,
  przyczyny pominięcia, brak bezpiecznej obietnicy daily limit przy incomplete.
  Coverage dialog dokładne occurrence+kwota estymaty vs faktury, tylko jedno replacement,
  preview skutków unlink/cancel, brak uruchomienia starego confirm dla bills.
- [ ] **GREEN:** `/lint`, `/typecheck`, `/test`; regression FinanceOverview/Today/Advisor
  i istniejących komponentów forecast, synthetic fixtures source discrimination.
- [ ] **COMMIT:** `feat: połącz rejestr faktur z płatnościami i nadchodzącymi`.

### Task 10: Gate całego obiegu, urządzenia i dokumentacja wydania

**Files:** Create `frontend/e2e/financial-documents.spec.ts`,
`frontend/e2e/financial-document-fixtures.ts`, `backend/tests/test_finance/test_bill_workflow.py`,
`docs/audits/2026-10-28-financial-document-workflow-verification.md`;
Modify `docs/CHANGELOG.md`, `docs/TASKS.md`, `docs/JOURNAL.md` i ten plan/checklisty.

**Interfaces:** pełne kontrakty poprzednich tasks; fixtures wyłącznie syntetyczne.

- [ ] **RED:** E2E 375/1440: stary PDF→manual review→invoice100PLN→forecast100→link40→60
  →link60→zero upcoming; photo HEIC tego samego zakupu attach bez kosztu, receipt paid
  bez fake allocation; schedule100 i invoice120=>jeden120 po decyzji. LLM/OCR błąd widoczny,
  manual działa. Brak praw do cudzego original i duplicate concurrent approval backend.
- [ ] **RUN RED:** `/test` + Playwright wg istniejącego `frontend/package.json`
  w izolowanym środowisku testowym. Bez płatności/mutacji realnej produkcji.
- [ ] **IMPLEMENT:** tylko poprawki integracji ujawnione powyższymi testami (osobne
  małe commity). Uruchomić lokalny docker build nowej zależności i parser contract test.
  Restore/rehearsal migracji na disposable kopii wg zgody; nie uruchamiać upgrade
  produkcji. Sprawdzić iż migracja nie odpala OCR i zachowuje wszystkie stare kolumny.
- [ ] **DEVICE CHECK:** rzeczywisty Android i iPhone: aparat i galeria, JPEG/HEIC,
  pion/poziom, tekst, odczyt, błędny/za duży obraz, limit pamięci. Jeżeli urządzenia
  niedostępne, odnotować BLOCKED; emulacja viewport nie zastępuje certyfikacji aparatu.
- [ ] **GREEN:** `/lint`, `/typecheck`, `/test`, frontend build/E2E i review bezpieczeństwa
  całej gałęzi. Raport podaje rzeczywiste count/skip/ograniczenia, nie dziedziczy starych PASS.
- [ ] **DOCS/COMMIT:** `/docs`, aktualizacja checklist/spec i oddzielny commit dokumentacji.
  Przedstawić wynik użytkownikowi. Release/deploy oraz przygotowanie jego starych PDF
  to osobne zatwierdzenia, nie automatyczny ostatni krok taska.

## Self-review planu (wykonane podczas pisania)

- Spec1–4: Constraints + Tasks1–4; spec5–6: Tasks2–4/8–9; spec7: Tasks7/9;
  spec8: Tasks5–6; spec9: Tasks3–4/8; spec10: Tasks1–6; spec11: Tasks1–10;
  spec12–13: izolacja/gate/przekazanie. HEIC zaakceptowany po builder check ma Task1
  i device gate, nie tylko rozszerzenie `accept`.
- Read-only queries nie robią implicit prepare/backfill; tworzenie draft/approve/expense
  są trzema rozdzielnymi komendami. OCR done i reconciliation nie mają wspólnego enum.
- `BillResponse`/`AllocationCreate`/`BillPaymentCreate`/`CoverageDecision` są definiowane
  przed użyciem, mutation boundaries/idempotency i row lock order wspólne dla Tasks4–7.
- Pięć Review Focus ma wskazane testy i tasks; brak świadomie pominiętych wymagań spec.
- Granice: nie obsługiwać zwrotów/FX settlement, nie odblokować ogólnego Inbox→transaction,
  nie przenosić Q7/wyciągów do modelu faktury, nie importować obecnych dokumentów.

## Handoff

Plan zapisany, jeszcze niewykonywany. Użytkownik wybiera realizację:
**subagent-driven** (rekomendowana: niezależne implementacje/review każdego taska,
bo błędy alokacji/prognozy zmieniają decyzje finansowe) lub **native** (jeden wykonawca
w tej sesji i niezależne review całej gałęzi na końcu). Najpierw przegląd planu
i potwierdzenie metody; następnie using-git-worktrees i odpowiedni skill realizacji.
