# Document/payment Matching 5A Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Wyjaśnić i uporządkować istniejące podpowiedzi płatności PLN na podstawie kwoty, jawnych dat i ostrożnej wskazówki nazwy, bez zmiany księgi.

**Architecture:** Rozszerzenie obecnego GET candidates i jego dialogu. Czyste funkcje budują dowody/klucz kolejności, istniejący serwis nadal odpowiada za owner scope, kwalifikacje i pojemność. Alokacja pozostaje dotychczasowym, ręcznie zatwierdzanym poleceniem.

**Tech Stack:** Python 3.12+, FastAPI/Pydantic v2/SQLAlchemy async/PostgreSQL, React 18/TypeScript/TanStack Query, pytest/Vitest/Playwright; bez nowych zależności runtime.

**Spec:** `docs/superpowers/specs/2026-11-07-document-payment-matching-design.md` — zakres zatwierdzony przez usera „tak” 2026-11-07. **Plan i wykonanie natywne zatwierdzone: „tak, natywnie”.** Bez zgody na produkcję i operacje infrastrukturalne poza dotychczasowym zakresem.

**Odbiór lokalny:** wykonano Task1–4; wyniki, decyzje wykonawcze (harmonogram pełnych gate, venv, osobna macierz testów UI) i końcowy review w `docs/audits/2026-11-07-document-payment-matching-local.md`. Brak wdrożenia. Checklist poniżej zachowuje oryginalny plan; wynik wykonania jest w raporcie i commitach.

## Global Constraints

- „nadal tylko PLN dla rozliczenia”; „Bez nowych tabel, migracji, trwałych scoringów, cache'u będącego źródłem prawdy”.
- „Bez nowych postings/transakcji/zmian kwot, kategorii, dat, walut lub Actual mappings” w ścieżce sugestii/linkowania istniejącej płatności.
- „Brak wstępnie zaznaczonego zwycięzcy”; „Nie ustawiamy automatycznie kwoty jako min(pozostałość, pojemność)”.
- „Metadata innego ownera nie jest dowodem i nie trafia do odpowiedzi”; brak metadanych nie potwierdza daty zakupu ani księgowania.
- Zachować `_eligible`, lock graph, owner/capacity/loan/pending/future/FX/coverage guards, receipt/retry/audyt i oddzielny tryb tworzenia expense.
- GET pozostaje read-only, bez rezerwacji/snapshot tokena. Bez autolinków, AI/OCR/providerów, importów lub batchu historii, zmiany oryginalnych plików i działań produkcyjnych.
- Nowe pola addytywne z domyślnym brakiem. Zachować `date`, IDs, amounts, `reasons`, recurring warnings oraz `total/limit/offset`.
- `BILL_PAYMENT_CANDIDATE_DATE_WINDOW_DAYS` pozostaje jedyną konfiguracją szerokości okna. Istniejące okno jest **jednostronne**; nie zwężać go do ±W.
- „Nie zwiększać liczby zapytań per kandydat dla nowych pól”; istniejąca relacja `date_metadata` już jest selectin. Bez refaktoru całego query engine.
- Plan nie upoważnia do deploy, migracji, dotykania produkcyjnych kontenerów ani prywatnych dokumentów. Testy wyłącznie na syntetycznych danych.

## Review Focus

1. Nazwa tylko w `[actual:...]`, pusta/interpunkcyjna nazwa lub HTML w opisie: brak fałszywego dowodu; tekst bez wykonania HTML. Testy Task1/3.
2. Granica W i różnica między starym jednostronnym oknem a nowym ±W zakupu: dawniej widoczne wyniki nie znikają; daty filtrów nadal dotyczą zapisu. Testy Task1/2.
3. Opóźniony wynik poprzednich filtrów oraz refetch identycznych danych: stary radio/checkbox nie odżywa i nie umożliwia POST. Testy Task3.
4. Timeout po potencjalnie skutecznej alokacji: ponowienie identycznej decyzji zachowuje klucz receipt; nie powstaje nowy expense. Testy Task3/4.
5. Metadane obcego ownera i wiele źródeł dokumentu: brak wycieku/dublowania wyników i brak zmian danych po GET. Testy Task2.

## Mapa plików i interfejsów

Create:
- `backend/app/finance/bill_candidate_evidence.py` — czyste dowody dat/tekstu i klucz kolejności, bez DB/I/O.
- `backend/tests/test_finance/test_bill_candidate_evidence.py` — unit bez PostgreSQL.
- `backend/tests/test_finance/test_bill_candidates.py` — integracyjne GET/kwalifikacje/read-only; wykorzystuje istniejące syntetyczne factory z `test_bill_payments.py`.
- `frontend/src/components/finance/bills/BillCandidateSummary.tsx` — prezentacja pojedynczego kandydata; nie wybiera/nie zapisuje.
- `frontend/src/components/finance/bills/BillCandidateSummary.test.tsx` — prezentacja/kompatybilność/escaping.

Modify:
- `backend/app/finance/bills_schemas.py:161-186` — addytywny kontrakt dowodów i niedostępności.
- `backend/app/finance/bill_payments.py:get_payment_candidates` — tylko odczyt, kwalifikacje i sortowanie; mutatory bez zmian.
- `frontend/src/api/bills.ts:58-76` — zgodne typy odpowiedzi. Hook/klucze mutacji pozostają.
- `frontend/src/components/finance/bills/BillPaymentDialog.tsx` oraz `.test.tsx` — stany listy i wybór powiązany z aktualnym odczytem.
- `frontend/e2e/financial-document-fixtures.ts` i `frontend/e2e/financial-documents.spec.ts` — rozszerzenie istniejącego hermetycznego scenariusza.
- `docs/{CHANGELOG,TASKS,JOURNAL}.md` i nowy `docs/audits/2026-11-07-document-payment-matching-local.md` — rzeczywiste wyniki lokalnego odbioru, bez deklaracji wdrożenia.

Bez zmian modeli, migracji, `bills_router.py`, `allocate_payment`, `unlink_payment`, `record_bill_payment`, loadera oryginałów i mechanizmu idempotencji.

## Uruchamianie i granice środowiska (dla przyszłego wykonania)

Nie uruchamiano testów produktu podczas pisania planu. Przed wykonaniem użyć `using-git-worktrees` do weryfikacji izolacji obecnego worktree; nie tworzyć kolejnego bez potrzeby i nie zabierać istniejących zmian Velo/Q7.

Używać workflow `/test`, `/lint`, `/typecheck`, `/docs`; nie uruchamiać `/migrate`, `/migration`, `/deploy`. Definicje w `.opencode/command/` wskazują hostowe `/opt/finanse`: **nie testować przez to innego checkoutu**. Jeżeli harness nie ma wywołania slash, wykonać równoważny workflow z cwd bieżącego worktree, z udokumentowanym powodem. Dopuszczalne polecenia zawężone dla cykli RED/GREEN podano w zadaniach; pełne gate przed każdym commitem kodu.

Backend: interpreter Python3.12+ i zależności z istniejącego środowiska; `TEST_DATABASE_URL` wyłącznie własna, jednorazowa `finanse_test` na localhost/127.0.0.1:5432 lub55432, bez konfliktu z innymi sesjami. `tests/conftest.py` tworzy i usuwa schema tej bazy! Bez dostępnej bezpiecznej bazy testy integracyjne są BLOCKED, nie PASS przez skip; nie zmieniać guards ani łączyć się z produkcją. Nie zakładać zgody na operacje infra.

Polecenia `python -m pytest …` poniżej mają cwd `backend`; `npm …` cwd `frontend`. Pełne gate: `/lint`, `/typecheck`, `/test`, dodatkowo `npm run build` i `npm run test:e2e` (istniejące fixtures serwują build w pamięci, bez realnego API). Logi w `/tmp/opencode/payment-matching-5a/`, nie w repo. Testy nie naprawiają niezwiązanych starych błędów bez uzgodnienia.

---

### Task 1: Addytywny kontrakt i czyste dowody dopasowania

**Files:** Create evidence helper + jego unit test; Modify `backend/app/finance/bills_schemas.py`.

**Interfaces:**
- `BillDateSource = Literal['manual','bank','document','import']`.
- `BillCandidateDateComparison(BaseModel)`: `transaction_basis: Literal['purchase','booking','legacy']`, `transaction_date: date`, `document_basis: Literal['sale','due','issue','today']`, `document_date: date`, `delta_days: int` (transaction minus document), `within_window: bool` (abs(delta)≤W).
- `BillCandidateEvidence(BaseModel)`: `description: str`, `currency: Literal['PLN']`, nullable `purchase_date`, `booking_date`, `purchase_date_source`, `booking_date_source`; `date_comparison: BillCandidateDateComparison`; `supplier_name_in_description: bool`; `planned_account_matches: bool | None`; `legacy_date_before_window: bool`; `purchase_within_window: bool`.
- `BillCandidate.evidence: BillCandidateEvidence | None = None`.
- `BillCandidatePage.unavailable_reason: Literal['document_inactive','document_unapproved','currency_unsupported','document_reconciled'] | None = None`.
- `supplier_name_in_description(supplier_name: str | None, description: str) -> bool`.
- `build_candidate_evidence(bill: FinancialDocument, transaction: FinancialTransaction, posting: Posting, *, today: date, window_days: int) -> BillCandidateEvidence`.
- `candidate_sort_key(candidate: BillCandidate, total_minor: int) -> tuple[int, int, int, int, str, str]`; consumed by Task2. Only sorts new candidates with evidence; never silently generates evidence for a legacy response.

- [ ] **1. RED tests:** Implement `test_legacy_candidate_schema_defaults` using an existing valid candidate payload; assert `evidence is None`, page `unavailable_reason is None`, and legacy fields unchanged. Add parametrized `test_date_pair_precedence` with all five spec rows (including no dates→today), explicit `today=date(2026,11,7)`, W=2. Pin the Friday example:
  ```python
  assert e.purchase_date == date(2026, 10, 30)
  assert e.booking_date == date(2026, 11, 2)
  assert e.date_comparison.transaction_basis == 'purchase'
  assert e.date_comparison.document_basis == 'sale'
  assert e.date_comparison.delta_days == 0
  assert e.date_comparison.within_window is True
  ```
  `test_unknown_and_foreign_metadata_are_not_evidence`: omit/attach wrong-owner metadata; assert both projected dates/sources None, basis legacy and original transaction date unchanged. `test_text_signal_is_whole_normalized_phrase`: assert Supplier `ŻÓŁĆ, Sp. z o.o.` matches `zapłata żółć sp z o o terminal`; `ABC` does not match `XABCD`; whitespace, punctuation-only, `[actual:ABC] unrelated` and absent names returnFalse; no accent stripping/alias matching. Check NFKC+casefold (including composed/decomposed Unicode) and a surviving real description after the prefix. `test_evidence_window_edges`: ±W true, ±(W+1) false for purchase/comparison; legacy flag only tests `txn.date < (due or issue or today)-W`. `test_sort_priority_and_account_information`: assert legacy→amount difference→name→abs(days)→txnID→postingID; planned-account None/True/False does not alter ordering.
- [ ] **2. RED run:** `python -m pytest tests/test_finance/test_bill_candidate_evidence.py -v`; expected assertion/import failures for the new contract/helpers, not environment failures.
- [ ] **3. Implement:** Add schema types above, nullable date/source fields defaultNone. Helpers take only preloaded models. Accept metadata only when its transaction_id and user_id match the owned transaction/bill; never synthesize dates or sources. Choose the first available date-pair row from spec§5; fallback transaction basis booking only if matching explicit booking date confirms txn.date, otherwise legacy. NFKC→casefold→sequences of Unicode letters/numbers (punctuation/whitespace separate); contiguous token subsequence only, strip leading technical `[actual:…]` segment(s) from description before matching. Empty token lists cannot match. Use `bill.payment_account_id == posting.account_id` only when a plan exists. No SQL, fuzzy matching, source rewrites or runtime dependencies.
- [ ] **4. GREEN run:** same unit command; all assertions PASS. Run schema regressions/full `/lint`, `/typecheck`, `/test` before commit; don't claim skipped integrations PASS.
- [ ] **5. Commit:** stage only Task1 files, `feat: dodaj jawne dowody dopasowania płatności`.

### Task 2: Integracja dowodów z obecnym GET candidates

**Files:** Modify `backend/app/finance/bill_payments.py:get_payment_candidates`; Create `backend/tests/test_finance/test_bill_candidates.py`; existing tests `test_bill_payments.py`, `test_bill_payment_concurrency.py`, `test_bill_guards.py` are regression gates.

**Interfaces:** Consumes Task1 schemas, `build_candidate_evidence(...)`, `candidate_sort_key(...)`. Produces unchanged signature `get_payment_candidates(db, user_id, bill_id, *, limit, offset, query=None, date_from=None, date_to=None, include_older=False) -> BillCandidatePage`; router and mutation payloads unchanged.

- [ ] **1. RED tests:** Mark integration+asyncio, reuse `create_owner`, `setup_bill`, `expense` from `tests.test_finance.test_bill_payments`; add source/date metadata via synthetic ORM fixtures only. Freeze `_local_today` at2026-11-07 and W=2. Named cases and exact assertions:
  - `test_candidate_has_owned_evidence_and_preserves_amounts`: expense10000 split across categories, allocation4000 to another bill; candidate `amount_minor==10000`, `unallocated_minor==6000`, currencyPLN, correct dates/sources. Nothing sums to20000.
  - `test_purchase_window_adds_without_narrowing_legacy`: bill saleOct30/dueNov30, txn dateNov2/purchaseOct30. It appears through new purchase window. No metadata with txn date after reference+W still appears via old one-sided rule. Explicit `date_from=Nov3` excludes the Nov2 candidate despite purchase match. Old≥cutoff results remain; parameterize W boundaries and include_older/query/legacy exceptions, respecting explicit date bounds and text match.
  - `test_order_and_pages_use_global_stable_rank`: known UUIDs/identical amounts/different names+dates; assert exact concatenated IDs across limit1 pages equals full ranked list, legacy reference first. Account mismatch remains visible with false evidence and can still be allocated by existing rules.
  - `test_document_unavailable_priority`: lifecycle before review before currency before remaining; each returns empty/total0/reason, same limit/offset. Own draft/archived/cancelled/rejected/EUR/USD/fullyallocated cases; foreign/missing bill retains404 route contract.
  - `test_evidence_never_relaxes_eligibility`: supplier/date exact matches cannot admit pending, future, transfer, income, FX, loan, unbalanced or other-owner records; reuse existing fixture patterns. No new refund classifier.
  - `test_foreign_metadata_and_multiple_sources_are_read_only`: attach mismatched metadata owner and two document sources; assert no leaked dates/sources and one candidate/posting. Capture transaction/posting/date metadata, document versions, allocations, receipts/audit counts before/after GET; assert identical. New metadata must add no per-candidate SQL (count metadata SELECTs for1 versus10 eligible transactions; allow selectin batch, don't assert total legacy query count).
- [ ] **2. RED run:** `python -m pytest tests/test_finance/test_bill_candidates.py -v`; expected new fields/availability/ranking assertions FAIL, PostgreSQL tests actually execute.
- [ ] **3. Implement:** After owner-scoped bill lookup, apply unavailable checks in defined order. Compute remaining from current sum of `DocumentPaymentAllocation.amount_minor` for this bill (one request-level aggregate, same arithmetic as existing bill response). Keep ownership404 and pagination. Preserve hard eligibility, capacity, loan, recurring warnings and existing source discovery. Build evidence from loaded relations, retain all old reasons. Existing window pass is `not legacy_date_before_window or include_older or normalized_query or legacy`; additionally allow `purchase_within_window`. Explicit date bounds/text remain mandatory. Add `purchase_date_within_window` reason only when that evidence is true; render legacy date reasons with explicitly legacy labels later. Sort the full eligible list with Task1 key **before slicing**. New fields add no DB writes and no per-item read queries. Do not edit mutators or deduplicate transactions by description/amount.
- [ ] **4. GREEN/regression:** `python -m pytest tests/test_finance/test_bill_candidates.py tests/test_finance/test_bill_payments.py tests/test_finance/test_bill_payment_concurrency.py tests/test_finance/test_bill_guards.py -v`; all PASS with no integration skips. Then full `/lint`, `/typecheck`, `/test`.
- [ ] **5. Commit:** stage Task2 files, `feat: ulepsz odczyt kandydatów płatności bez zmian księgi`.

### Task 3: Czytelny dialog i wybór związany z aktualnym odczytem

**Files:** Modify `frontend/src/api/bills.ts`, `BillPaymentDialog.tsx` i `.test.tsx`; Create `BillCandidateSummary.tsx` i `.test.tsx` w `frontend/src/components/finance/bills/`.

**Interfaces:**
- TS `BillCandidateDateComparison` i `BillCandidateEvidence` dokładnie odpowiadają Task1 (dates stringISO, sources literal union). `BillCandidate.evidence?: BillCandidateEvidence | null`; `BillCandidatePage.unavailable_reason?:` Task1 union `| null`. Optional fields support older API/fixtures without fabricated facts.
- `BillCandidateSummary({ candidate }: { candidate: BillCandidate }): JSX.Element` — tylko prezentacja, żadnych hooków mutacji.
- Hook `useBillCandidates` zachowuje query key/filters/GET. Istniejące `useAllocateBillPayment` i `useSerializedIntentKey` bez zmiany interfejsu/semantyki. Ochrona wyboru lokalna w dialogu.

- [ ] **1. RED presentation:** `test_shows_dates_provenance_amounts_and_reasons`: total/remaining dokumentu w nagłówku, pierwotna/wolna kwota płatności w wierszu; dane Task1 Fridayexample, account, PLN, źródła manual/bank/document/import i para zakup↔sprzedaż oraz różnica dni. `test_legacy_payload_does_not_invent_dates`: bez evidence pokaż `Data zapisu — znaczenie nieustalone`, bez przypisywania source/purchase/booking. `test_untrusted_text_and_unknown_reasons`: `<img src=x onerror=…>` jako tekst, brak elementuimg; nieznane reasons pomiń, nie renderuj jako HTML/kod. Trafienie nazwy pokaż dokładnie „Nazwa sprzedawcy z dokumentu występuje w opisie płatności”; false nie jest błędem kontrahenta. Różne planowane konto to uwaga, nie disabled radio. Stare date reasons opisuj jako okno daty zapisu, nie dowód zakupu.
- [ ] **2. RED interaction:** Rozszerz istniejące testy dialogu z QueryClientem i kontrolowanymi deferred promises, bez sleep:
  - `test_loading_error_empty_unavailable_are_distinct`: status ładowania, erroralert+`Spróbuj ponownie`, empty `Brak płatności w wybranych filtrach.`, cztery przyczyny niedostępności jako polskie etykiety; żaden stan nie przełącza trybu na rejestrację. Retry wysyła te same parametry.
  - `test_filter_page_retry_and_identical_refetch_clear_decision`: wybór radio+recurring checkbox, następnie każda zmiana filtrów/strony/refetch usuwa oba, pozostawia amount. Opóźniona odpowiedź poprzedniego query nie odtwarza wyboru. Nawet identyczny response JSON po refetch wymaga ponownego radio, nie polegaj wyłącznie na referencji `data`.
  - `test_submit_handler_rejects_stale_or_invalid_selection`: podczas fetching/error/unavailable/invalid daterange lub gdy posting nie należy do aktualnego odczytu, wymuszone kliknięcie/submit nie wywołujePOST. Złe kwoty/daty nie omijają handler guard. Potwierdzenie recurring musi dotyczyć bieżącego wyboru.
  - `test_409_requires_refresh_and_reselection`: zachowaj amount, fetch bill/version, usuń stary radio/checkbox, wymagaj nowej jawnej decyzji i ponownego wyboru; nowy POST używa nowej wersji. Zaktualizuj istniejący test, który dziś dopuszcza zachowanie starego radio po409.
  - `test_uncertain_retry_preserves_receipt_key`: pierwszy allocationPOST rzuca timeout bez odpowiedzi; jeśli odczyt nie był odświeżony, retry identycznego payloadu ma identyczny `Idempotency-Key`. Jeżeli wykonano refresh, wymagaj ponownego wyboru; dla identycznego payloadu nie resetuj keyFor. Nie dodawaj epoch/time do intent. Żaden przypadek nie wywołuje `/payments` ani endpointu tworzącego transakcję. Zachowaj osobne stare testy jawnej rejestracji expense.
- [ ] **3. RED run:** `npm run test -- src/components/finance/bills/BillCandidateSummary.test.tsx src/components/finance/bills/BillPaymentDialog.test.tsx`; oczekiwane braki nowej prezentacji/guards, nie niezwiązane błędy setup.
- [ ] **4. Implement presentation:** Dodaj TS types i komponent summary. Używaj escaped JSX, kontrolowanej mapy etykiet reasons/source/basis; formatuj date-only bez UTC→lokalnego przesuwania dnia. Dane porównania tylko z backendu; nie zgaduj z `date`. Zachowaj konto/radio, opis z łamaniem długich słów i warning recurring. Daty filtrów nazwij zakresem daty zapisu w historii; sprzedawca i daty dokumentu jako kontekst, osobno od dat płatności. Kwoty wszystkie jawnie PLN. Etykieta linkowania: „Powiązanie nie tworzy transakcji i nie zmienia księgi.”
- [ ] **5. Implement guards:** Utrzymuj lokalny monotoniczny numer odczytu/wyboru; zmiana filtrów/offset, rozpoczęcie refetch/retry oraz nowe przyjęte `dataUpdatedAt` unieważniają wybór/checkbox. Zapisany wybór jest ważny wyłącznie dla bieżącego fingerprintu filtrów i udanego, niepobieranego odczytu. Handler ponownie sprawdza query state, token/ID, conflict acknowledgement i amount>0/date bounds. Nie polegaj tylko na efekcie, który może wykonać się po renderze; guards porównują aktualny odczyt bezpośrednio. Zachowaj 409/receipt intent, nie resetuj `useSerializedIntentKey` przy wyczyszczeniu zaznaczenia. Lista może zniknąć przy pobieraniu; potwierdzenie nigdy nie korzysta ze starej listy. Zmiana tego wyboru nie zmienia domyślnej kwoty ani oddzielnego trybu record.
- [ ] **6. GREEN/regression:** powyższy command oraz `npm run test -- src/api/bills.integration.test.tsx src/components/finance/bills/BillDetail.test.tsx`; potem pełne `/lint`, `/typecheck`, `/test`. Stare optional payloads przechodzą, nowe read-side nie trafia do POST ani intent key.
- [ ] **7. Commit:** stage wyłącznie Task3 files, `feat: wyjaśnij dopasowanie płatności i chroń aktualność wyboru`.

### Task 4: Odbiór całej ścieżki, regresje i dokumentacja

**Files:** Modify `frontend/e2e/financial-document-fixtures.ts`, `frontend/e2e/financial-documents.spec.ts`, trzy główne docs; Create lokalny audit wskazany w mapie. Ewentualne poprawki wyłącznie do zakresu Task1–3 i z nowym RED testem.

**Interfaces:** Consumes finalny JSON Task1/2 oraz UI Task3. Fixtures zachowują dotychczasowy domyślny scenariusz; dodatkowe opcje kontrolują dane candidates i opóźnienia/błędy lokalnego GET. Wszystkie żądania routowane przez istniejące fixtures; `api.mutations` i `api.assertClean()` pozostają źródłem asercji requestów.

- [ ] **1. RED E2E:** Dodaj `matching evidence and stale selection never creates a transaction` dla viewport375/1440: invoice100PLN, expense100PLN, zakupOct30/bookingNov2/saleOct30, jawny powód i źródła, brak zaznaczenia początkowo; wybierz→zmień filtr→przytrzymaj GET→brak POST/disabled; odpowiedz→ponowny wybór→alokacja4000 z wersją dokumentu. Assert lista mutations zawiera **tylko jeden POST allocations**, nie `/payments`/transactions/transfer; kwota4000, IDs zgodne z wybranym wierszem. Dodatkowy scenariusz failure→retry→empty odróżnia te stany i nigdy nie przełącza trybu. Zachowaj istniejący test dwóch części40/60 i prognozy. Sprawdź brak horizontaloverflow i etykiety radio/status/alert na mobile.
- [ ] **2. RED run:** `npm run build`, potem `npm run test:e2e -- financial-documents.spec.ts`; nowe scenariusze muszą wykazać brakujący szczegół, jeśli wszystkie już przechodzą, zapisz je jako acceptance/regression, nie fałszywe RED. Nie podmieniaj realnych danych w aplikacji, używaj tylko fixture routes.
- [ ] **3. Minimalne dopięcie:** Dodaj brakującą opcję fixture/etykietę/guard, jeżeli test to wykazał. Zachowaj Task1 types i payloady alokacji. Uruchom focused E2E ponownie, oczekuj PASS na obu viewportach; to nie certyfikuje fizycznych Android/iPhone.
- [ ] **4. Full gate:** `/lint`, `/typecheck`, `/test`, `npm run build`, `npm run test:e2e`; żaden skip nowego scope nie może ukryć BLOCKED. Zachowaj logi i dokładną rewizję/build w lokalnym audicie; nie przenoś dawnych518/145 wyników jako nowych. Potwierdź `git diff --check` i brak zmian backendmodels/migrations/infra/providerów. Zweryfikuj, że GET i allocation nie zmieniają ledgeru/metadanych w nowych testach; istniejące replay/concurrency/audit/unlink regresje PASS.
- [ ] **5. Whole-branch review:** Invoke `requesting-code-review`, jeden świeży reviewer po wszystkich zadaniach, zakres od bazowego commitu implementacji do finalnego diffu; fokus na owner/legacy dates/okno/receipt/stale guards. Popraw znalezione błędy w zakresie, dodaj test i ponów dotknięte oraz pełne gate po zmianie kodu. Nie rozszerzaj samodzielnie specyfikacji.
- [ ] **6. Docs + commit:** Workflow `/docs`: rzeczywiste wyniki/ograniczenia/następny krok w audit/CHANGELOG/TASKS/JOURNAL; nie oznaczaj deploy done. Po świeżych gate commit `test: odbierz lokalnie dopasowanie dokumentów i płatności`. Pozostaw produkcję, schemat i oryginały dokumentów bez zmian; przekazanie wyników użytkownikowi, wdrożenie wyłącznie po oddzielnej zgodzie na dokładną rewizję.

## Self-review planu (2026-11-07, nie odbiór produktu)

- Spec§1–3/8: granice zgody/globalconstraints i mapa; §4 kwoty/availability/eligibility Task2; §5 daty/okno Task1/2; §6 nazwa/konto/ranking Task1/2; §7 kontrakt/UI/stale/receipt Task1/3; §9 wszystkie scenariusze Task1–4; §10 decyzje wykonawcy doprecyzowane interfejsami.
- Typy evidence/unavailable wspólne backend/TS; porównanie ma podpisane delta i abs-window, zachowane legacydate i osobny flag starego jednostronnego okna. Nie mieszać tych dwóch okien.
- Każdy punkt ReviewFocus ma nazwany test w zadaniu właściciela; nie ma nowej funkcji zależnej od nieopisanej usługi/tabeli. Zadania są sekwencyjne: 1→2→3→4; nie wykonywać równoległych zmian tych samych kontraktów.
- Następny krok: użytkownik czyta plan i wybiera wykonanie native lub subagent-driven. Rekomendacja: native + jeden końcowy świeży reviewer, bo cztery zadania współdzielą mały kontrakt i istniejące mutatory pozostają bez zmian. Plan sam w sobie nie upoważnia do kodu ani wdrożenia.
