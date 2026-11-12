# Bill Declaration Without Transaction Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Rozliczyć całą pozostałą kwotę faktury deklaracyjnie, bez transakcji, z auditem i undo.

**Architecture:** Wykorzystać istniejące `FinancialDocument.declaration` i version/idempotency receipt. Dodać wąską komendę domenową/API, poprawić projekcję prognozy i odrębny opis płatności/uzgodnienia w UI. Bez migracji bazy lub zmian ledgeru.

**Tech Stack:** FastAPI/Pydanticv2/SQLAlchemyasync/PostgreSQL; React/TypeScript/TanStackQuery; pytest/vitest.

## Wynik wykonania — 2026-11-12

- [x] Task 1: komenda, audit, undo, guardy i prognoza. Commit `01cf1dd`.
- [x] Task 2: akcje/status/dialog, retry/409, testy i instrukcja użytkownika.
- [x] Wszystkie poniższe kroki RED/GREEN i bramki wykonane; pierwotne checkboxy
  pozostawiono jako zapis briefu. Backend2351PASS/0fail/error/skip/23proxyexcluded,
  frontend631PASS/E2E28PASS, lint/types/buildPASS. Jedno review bez uwag.
- [x] Cleanup własnych środowisk. Bez zmian produkcji, merge/push/deploy.

Odchylenia i koszty: existinglinkedworktree zamiast zagnieżdżonego, frontend podczas
bramek backendu, pełny backend w8niezależnych shardach i zapis taskdone z rzeczywistego
wyniku bez zbędnego powtórzenia całej komendy. Pełny zapis oraz odrzucone próby:
`docs/audits/2026-11-12-bill-declaration-local.md`.

**Spec:** `docs/superpowers/specs/2026-11-12-bill-declaration-without-transaction-design.md` (zakres zatwierdzony w rozmowie, szczegóły techniczne proponowane przez agenta).

## Global Constraints

- PostgreSQL źródłem prawdy; bez nowych JSONstore, Supabase lub fikcyjnych transakcji.
- Brak nowych tabel, migracji lub zmiany znaczenia `paid_minor/remaining_minor/reconciliation`.
- Deklaracja dotyczy całej pozostałej kwoty, nie częściowego opłacenia.
- DeklaracjePLN/EUR/USD bez FX; późniejsze linkowanie transakcji nadal tylkoPLN.
- Wszystkie zapisy owner-scoped/versioned/idempotent/audited; istniejące auth/CSRF bez zmian.
- Syntetyczne, własne środowisko testowe; żadnych produkcyjnych mutacji, deployu lub push.
- Obecny worktree ma niezwiązane lokalne docs/audity: zachować je bez stasha/resetu/force.

## Review Focus

- Pełne rozliczenie deklaracyjne nigdy nie udaje pełnego uzgodnienia z księgą; test Task1 `test_declaration_never_creates_ledger_or_allocation` i Task2 prezentacji.
- Częściowe/pełne późniejsze powiązanie i odłączenie nie dubluje kwoty; test Task1 `test_real_allocations_replace_declared_remainder_without_double_count`.
- Deklaracja bez konta lub zEUR/USD nie wymaga pozornej transakcji/FX; test Task1 `test_declaration_without_payment_account_all_currencies`.
- Cofnięcie po częściowym powiązaniu i istniejące coverage nie tworzą drugiej prognozy; Task1 `test_undo_and_coverage_preserve_single_remaining_cashflow`.
- Równoległy dialog,409 lub błądHTTP nie wysyła ukrytego nowego zamiaru; Task2 `test_conflict_requires_refresh_and_new_decision` i `test_retry_reuses_declaration_intent`.

---

## Setup and evidence

- [x] Przeczytano4requiredhostdocs, spec i plan; `using-git-worktrees` — potwierdzony istniejący linked worktree od1b43f0d; ruling w ledgerze, bez zagnieżdżania izolacji i ruszania cudzych dirtydocs/auditów.
- [x] Ledger planu zapisany. Dane istniejącej faktury nietknięte. Wszystkie testy na syntetycznych fixture.
- [x] Definicje `/test`, `/lint`, `/typecheck` przeczytane; Python3.12 w zgodnym runnerze, własny no-port scratchPostgreSQL.

### Task 1: Komenda deklaracji, audyt i projekcja

**Files:**
- Create: `backend/app/finance/bill_declarations.py`
- Modify: `backend/app/finance/bills_schemas.py`, `backend/app/finance/bills_router.py`
- Modify: `backend/app/finance/bills.py` (guard zmianykwoty/waluty), `backend/app/finance/bill_forecast.py`
- Create: `backend/tests/test_finance/test_bill_declarations.py`
- Extend: `backend/tests/test_finance/test_bill_routes.py`, `test_bill_forecast.py`, `test_bill_workflow.py`

**Interfaces:**
- Consumes: `bills._bill`, `_response`, `_run_bill_command`, `lock_document_mutations`, `MutationContext`, `BillResponse`; istniejące allocate/unlink usługi bez nowej semantyki paid_minor.
- Produces: `BillDeclarationChange(expected_version, declaration, confirm_forecast_effect)`; `async set_bill_payment_declaration(db: AsyncSession, user_id: uuid.UUID, bill_id: uuid.UUID, data: BillDeclarationChange, *, context: MutationContext) -> BillResponse`.
- API: `POST /finance/bills/{bill_id}/payment-declaration` z istniejącymprefixAPI i `Idempotency-Key`.

- [ ] **Step1 — RED: testy komendy.** Fixture `setup_bill(amount=10000)` i `create_owner` z test_bill_payments. Test `test_declaration_never_creates_ledger_or_allocation`: po oznaczeniu declaration=declared_paid, paid_minor=0, remaining_minor=10000, reconciliation=none; counts/hashes Accounts/Transactions/Postings/Allocations identyczne, audit old/newdeclaration i version+1. `test_idempotency_and_owner_version_guards`: replay ten samkey bez nowychauditów/receipts, zmienionypayload409, owner404, stale409. `test_lifecycle_and_request_guards`: draft/rejected/archived/cancelled/fullyallocated422, poleamount/falseconfirmation422.

```python
before = await db_session.scalar(select(func.count(Posting.id)))
response = await set_bill_payment_declaration(
    db_session, owner, bill.id,
    BillDeclarationChange(expected_version=2, declaration="declared_paid", confirm_forecast_effect=True),
    context=MutationContext(idempotency_key="declare-one"),
)
assert (response.declaration, response.paid_minor, response.remaining_minor, response.reconciliation) == (
    "declared_paid", 0, 10000, "none",
)
assert response.version == 3
assert await db_session.scalar(select(func.count(Posting.id))) == before
```

- [ ] **Step2 — RED: testy późniejszego rozliczenia/prognozy.** `test_real_allocations_replace_declared_remainder_without_double_count`:10000declaration→allocate4000 daje paid4000/remaining6000/partial, declaration nadal pokrywa całąresztę; allocate6000→paid10000/remaining0/full, brak dodatkowej transakcji. `test_undo_and_coverage_preserve_single_remaining_cashflow`:undo→payable, prognoza6000 raz, coveragezachowane i bezpowrotu recurringestimate. `test_declaration_without_payment_account_all_currencies`:PLN/EUR/USD bezkontakategorii; żadnych ledgerwrites. `test_declared_document_amount_change_requires_clear`:genericBillUpdate total/currency422 dopóki declared_paid; po explicitundo normalne reguły.
- [ ] **Step2a — RED: nieobchodzenie komendy i walut.** `test_generic_update_cannot_bypass_payment_declaration`: zatwierdzonyBillUpdate(declaration=declared_paid/payable) zmieniający aktualny stan→422,bez nowegoauditu/version; approve szkicu nadal pozwala początkowo wybraćdeklarację. `test_foreign_declaration_does_not_enable_foreign_allocations`:markEUR/USD działa, lecz candidates i allocate nadal zwracają istniejący unsupportedcurrency bez zmian ledgeru.
- [ ] **Step3 — obejrzeć RED.** `/test` w wariancie focusedpytest dla nowych testów i billforecast/routes/workflow, na własnejDB. Expected: brak schema/command/route lub błędna projekcja declaredpaid. Błąd środowiska nie jest RED.
- [ ] **Step4 — minimalny backend.** Schema extra=forbid,StrictInt>=1,target declared_paid/payable,confirmTrue. Komenda korzysta ze standardowych locków/receipt i audit before/after; bez mutacji księgi/coverage. Undo jawnie ustawia payable. Same-state po versionchecknoop; brakfraud fullreconciliation. ZgodneAPIerror/rollback. `project_bill_cashflows` pomija declared_paid w entries/daychanges/exclusions, ale covered_occurrences zachowuje; `_response` nadal zwraca rzeczywiste alokacje. Guard wupdate_bill blokuje rzeczywistą zmianę total/currency, gdy bieżąca declaration=declared_paid, oraz zmianędeclaration zatwierdzonego dokumentu z pominięciem nowej komendy. Początkowy wybórdeclaration wapprove nie zmieniony.
- [ ] **Step5 — GREEN i regresje.** Uruchomić nowe testy, wszystkie `test_bill*.py` i testy cashflow/receipt workflow. Expected:PASS bez niespodziewanych zmian nativeforecastexclusions dla nieopłaconych dokumentów. Sprawdzić noop/retry i rollbackauditreceipt.
- [ ] **Step6 — commit po lint/types/test gate.** `feat: dodaj deklaracyjne rozliczanie dokumentów bez transakcji`; stage wyłącznie pliki Task1 i plan/spec, żadnych prywatnych źródeł.

### Task 2: Akcje w rejestrze, status i bezpieczny dialog

**Files:**
- Modify: `frontend/src/api/bills.ts`, `frontend/src/pages/FinanceDocuments.tsx`
- Modify: `frontend/src/components/finance/bills/BillDetail.tsx`, `BillRegister.tsx`
- Create: `frontend/src/components/finance/bills/BillDeclarationDialog.tsx`, `billPaymentPresentation.ts`
- Create: `frontend/src/components/finance/bills/BillDeclarationDialog.test.tsx`, `billPaymentPresentation.test.ts`
- Extend: `frontend/src/api/bills.integration.test.tsx`, `frontend/src/pages/FinanceDocuments.test.tsx`, `frontend/src/components/finance/bills/BillDetail.test.tsx`, `frontend/e2e/financial-documents.spec.ts`

**Interfaces:**
- Consumes: komenda/API Task1 i niezmieniony `BillResponse`.
- Produces: `useSetBillPaymentDeclaration()` (billId, expected_version, declaration, confirm_forecast_effect:true, idempotencyKey); helper `billPaymentPresentation(bill: Pick<BillResponse,"declaration"|"remaining_minor"|"reconciliation">)` → `{ payableMinor:number, unlinkedMinor:number, statusLabel:string, declared:boolean }`.
- `BillDeclarationDialog({bill, declaration, onClose})`: wyłącznie potwierdzenie pozostałej kwoty/waluty, bez account/category/amount/date inputów.

- [ ] **Step1 — RED: prezentacja.** Helper: declared+none10000→payable0/unlinked10000/status dokładny zespec; declared+partial6000→payable0/unlinked6000/statusczęściowy; full→"Rozliczona z księgą"; payable+partial6000→payable6000. Rejestr bez czerwonego"Zaległe" dla deklaracji, historyczny dokument pozostaje widoczny.

```typescript
expect(billPaymentPresentation({
  declaration: "declared_paid", remaining_minor: 10000, reconciliation: "none",
})).toEqual({
  payableMinor: 0, unlinkedMinor: 10000, declared: true,
  statusLabel: "Opłacona deklaracyjnie — bez powiązania z księgą",
});
expect(billPaymentPresentation({
  declaration: "payable", remaining_minor: 6000, reconciliation: "partial",
}).payableMinor).toBe(6000);
```

- [ ] **Step2 — RED: flow/UI/API.** Potwierdzenie nowej akcji wysyła tylko poprawnyversion/target/confirm/key; brak endpoints payments/allocations/transactions. Undo pokazuje przywrócenie reszty do zapłaty bez cofania przelewów. Busy blokuje submit, błądniezamyka, retryidenticalkey.409 wymaga refetch i nowejdecyzji; zmiana billId/session w otwartym dialogu nie wysyła poprzedniej intencji. Test helpera/hooks/dialogu i FinanceDocuments na syntetycznychfixture.
- [ ] **Step3 — obejrzeć RED.** `/test` wariantfocusedvitest nowych/zmienionych plików. Expected: brakuje helpera/akcji/hooka lub istniejący widok pokazuje pozostale10000/zaległe; nie błąd setup.
- [ ] **Step4 — minimalny frontend.** Hook korzysta ze standardowego serializedintentkey i invalidacji bills/cashflow/documents, bez ledgerinvalidacji. Dodać akcjęmark/undo doBillDetail i osobnydialog. WBillRegister pokazać"Do zapłaty"zhelpera, wdetail oddzielić ją od"Pozostało do powiązania z księgą". Alokacje/sources pozostają bez zmian; pełnaalokacja ma pierwszeństwo nad deklaracją. Nie straszyć spodziewanym wykluczeniem zprognozy deklaracji. Zachowaćaktywny/lifecycle/version/approved guards i styleobecnegoUI.
- [ ] **Step5 — GREEN/E2E.** FocusedfrontendPASS, następnie fullvitest. Syntetyczny E2E:znakuj→0dozapłaty/ledgerbez zmian→reload→powiążistniejącąpełną→statusuzgodniony; osobnouundo po częściowejalokacji→reszta raz wprognozie. Desktop/mobile bezoverflow, żadnych endpointówbankowych lub produkcyjnych danych.
- [ ] **Step6 — bramki końcowe.** `/test`, `/lint`, `/typecheck`, frontendbuild, testy backend/API/prognozy zTask1. Expected:wszystkoPASS, explicitexcludedproxy odnotowane; testów nie zastępować jedną sumą wcześniejszych wyników. Jedno świeże review całej gałęzi; Important/Critical naprawićTDD, bez niejawnego rozszerzenia zakresu.
- [ ] **Step7 — docs i commit.** Zaktualizować CHANGELOG/TASKS/JOURNAL i instrukcję dokumentów; `feat: udostępnij oznaczanie faktur jako opłaconych bez księgowania`. Pozostawić realne dane użytkownika nietknięte. Merge/push/deploy wyłącznie po odrębnej zgodzie.

## Self-review

Zakres czatu pokryty Task1+Task2. Schemat danych i ledger bez migracji. Semantyka
częściowego powiązania, pełnego uzgodnienia, undo i chronionej kwoty jawnie określona;
każdy ReviewFocus ma przypisany test. Fixture istniejące, żaden prywatnyJSON nie jest
źródłem prawdy lub payloadem testowym. Wykonanie i metoda implementacji czekają na decyzję.
Builder-check spec uwzględniony: guardgenericPATCH oraz jawny brak rozszerzenia
walutowych alokacji. Nie uruchamiać drugiego review planu lub implementacji na etapie planowania.
