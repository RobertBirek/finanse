# Transaction Annotations Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Bezpieczna ręczna edycja własnego opisu, notatki, tworzonych na miejscu tagów i opcjonalnego projektu transakcji.

**Architecture:** Nakładka opisowa PostgreSQL oddzielona od źródłowego opisu i księgi. Dedykowana komenda owner/version/snapshot/idempotency/audit, bez poszerzania uprawnień kategorii. Projekt używa istniejącego project_id, odczyty są batched.

**Tech Stack:** FastAPI/Pydantic/SQLAlchemy/Alembic/PostgreSQL; React18/TypeScript/TanStackQuery; pytest/vitest/Playwright.

**Spec:** `docs/superpowers/specs/2026-11-12-transaction-annotations-design.md` (zatwierdzony zakres w czacie, techniczne defaults autora do przeglądu).

## Global Constraints

- Najpierw zakończyć poprzedni plan kategoryzacji, fullsuite/review/cleanup i localcommit; nie zmieniać jego zamrożonego kodu.
- Kwoty, konta, daty, oryginalne opisy, postings i referencje importu pozostają. Projekt tylko w FinancialTransaction.project_id, bez duplikatu.
- Tagi tworzone podczas edycji, ponownie używane; rollback/anulowanie nie tworzy słownika. UnicodeNFC/strip/collapse-whitespace/casefoldkey.
- Wszystkie własne typy/źródła mogą mieć nakładkę; nie uzyskują nowych uprawnień do księgi/kategorii. Bez reguł/AI writes.
- Addytywna migracja na własnym testPG; preflight nieprawidłowego project_id kończy się błędem, nie czyszczeniem danych.
- Konfigurowalne defaults: opis200/notatka5000/tag60/20tagów; klient korzysta z limitów serwera. Tekst bez HTML.
- Bez nowych zależności, produkcyjnych mutacji, merge/push/deploy. Zachować unrelateddirtydocs/audity.

## Review Focus

1. Dwa równoległe pierwsze zapisy tej samej transakcji/tagu nie tworzą duplikatów ani nie gubią zmian; test Task2.
2. Oznaczenie protectedloan/FX/importu nie otwiera edycji kategorii ani źródłowego opisu przez legacyPATCH; test Task2.
3. Usunięcie projektu lub zmiana transakcji po otwarciu wymaga odświeżenia, nie zapisuje osieroconego linku; test Task2.
4. Nowe odczyty/wyszukiwanie nie ujawniają obcych tagów/projektów, nie dublują wyników i nie powodują N+1; test Task3.
5. Wyczyszczenie nakładki/retry409/anulowanie nie kasuje bankowego opisu, nie tworzy tagów i zachowuje dane formularza; test Task4.

---

### Task 1: Modele nakładki, tagów i migracja

**Files:** Create `backend/app/finance/annotation_models.py`, `backend/app/finance/annotation_schemas.py`, `backend/migrations/versions/transaction_annotations.py`, `backend/tests/test_finance/test_annotation_models.py`; modify `backend/app/config.py`, `backend/app/finance/models.py`, `backend/migrations/env.py`, odpowiedni rejestr modeli w `backend/tests/conftest.py`/`backend/app/main.py` jeśli wymagany.

**Interfaces:** TransactionAnnotation(transaction_id,user_id,display_description?,note?,version>0); FinanceTag(id,user_id,name,normalized_name) unique(user_id,normalized_name); TransactionTag(transaction_id,user_id,tag_id) unique(transaction_id,tag_id), owner-safeFK. FinancialTransaction.annotations relacja uselistFalse/selectin, finance_taglinks selectin. Nie dodawać osobnego project_id do annotations. `AnnotationResponse` zawiera display_description:str|null,note:str|null,tags:list[AnnotationTag{id:UUID,name:str}],project_id:UUID|null,version:int,context_snapshot:str,limits; `AnnotationUpdate` strict/extra-forbid wymaga display_description:str|null,note:str|null,tags:list[str] (nazwy istniejących lub nowych),project_id:UUID|null,expected_version:int>=0,expected_context_snapshot:str. GET bez wiersza zwraca version0, puste overlay/tags i istniejącyproject_id; nie tworzy DBrow.

- [ ] RED: `test_annotations_are_owner_scoped_and_optional`, `test_tags_have_one_normalized_identity`, `test_project_fk_preserves_transaction_on_delete`, `test_annotation_schema_rejects_ledger_fields` — literalne null/empty/version0 i obceIDs, duplicateFK/unique guards. ExpectedFAIL: brak modeli/schematów.
- [ ] GREEN: dodać modele/schematy/config, relacje/registerimports i addytywną migrację. Nazwa pliku powyżej, revision wygenerowane przez dostępną komendę `/migration`, nie zgadywać rewizji rodzica. Preflight sprawdza missing/foreignprojectrefs i jawnie zatrzymuje upgrade. Dodać FKproject→projects.id SETNULL bez kopiowania danych źródła.
- [ ] VERIFY: `/migrate` wyłącznie we własnym runnerPG, upgrade z poprzedniego head i świeży upgrade; testy modeli, `/lint`/`/typecheck` backend. Gdy slashcommands niedostępne, udokumentowane równoważne komendy w izolowanym runnerze. ExpectedPASS bez zmian starych wierszy/referencji.
- [ ] COMMIT tylko tego taska: `feat: dodaj modele opisowych oznaczeń transakcji`.

### Task 2: Wersjonowana komenda ręczna i ochrona źródła

**Files:** Create `backend/app/finance/annotations.py`, `backend/app/finance/annotation_router.py`, `backend/tests/test_finance/test_annotations.py`, `backend/tests/test_finance/test_annotation_races.py`; modify `backend/app/finance/router.py`, `backend/app/finance/transactions.py`.

**Interfaces:** Consumes modele/schematy Task1. Produces `get_annotations(db:AsyncSession,owner:UUID,transaction_id:UUID)->AnnotationResponse`, `update_annotations(db,owner,transaction_id,data:AnnotationUpdate,*,idempotency_key:str)->AnnotationResponse`, `list_annotation_tags(db,owner,*,q:str,limit:int)->list[AnnotationTag]`. Routes GET/PUT `/api/finance/transactions/{id}/annotations`, GET `/api/finance/tags?q=` (ownerbound, fixed capped page). PUT wymaga Idempotency-Key; receipt action`update_transaction_annotations`, audit old/new, 404owner,409snapshot/keyconflict,422validation. Snapshot wiąże rowversion+txnid+updated_at+project_id; projekt walidowany/lockowany.

- [ ] RED: `test_import_annotation_preserves_original_payment_and_provenance`, `test_annotation_allowed_for_protected_sources_without_ledger_authority`, `test_annotation_clearing_restores_original_title`, `test_annotation_validation_rolls_back_new_tags`. Assertliteralopis/notatka/tag/projekt, exactpostings/date/evidence/mapping/receipt/originaldescription; accountbalance/report unchanged; niepowstają ruleevents/AIjobs; APIrejects kwota/data/source fields.
- [ ] RED: `test_duplicate_retry_returns_receipt_without_rewriting_newer_annotation`, `test_stale_annotation_rejected_without_partial_write`, `test_parallel_first_annotations_only_one_wins`, `test_concurrent_normalized_tag_creation_reuses_one_id`, `test_project_deleted_after_open_conflicts`, `test_foreign_tags_and_project_are_invisible`, `test_legacy_patch_cannot_rewrite_imported_original_description`. Drugie rzeczywiste połączenie; nie zastępować race samą sekwencją requestów.
- [ ] GREEN: implementować ownerlock→transactionrow→annotationrow, projekt w kontrolowanej kolejności, tagupsert/uniqueness i atomowy zapis+audit+receipt. Cały formularz ma replace semantics; whitespace-onlytitle/note→null; no-op bez nowego audytu/wersji, receipt nadal idempotentny. Dołożyć wąski guard legacyPATCH tylko dla zmiany oryginalnego opisu chronionych importów, bez zmiany ręcznych wpisów.
- [ ] VERIFY: focusedpytest annotations/races + categorization/imports/dates/receipt/loans, backend lint/mypy. ExpectedPASS, zero częściowych zapisów/masowych operacji.
- [ ] COMMIT `feat: zapisuj opis notatkę tagi i projekt bez zmiany księgi`.

### Task 3: Projekcje i wyszukiwanie oznaczeń

**Files:** Create `backend/app/finance/annotation_reads.py`, `backend/tests/test_finance/test_annotation_search.py`; modify `backend/app/finance/queries.py`, `backend/app/finance/schemas.py`, `backend/app/finance/transactions.py` odczyty zwracające TransactionResponse.

**Interfaces:** Consumes Task1+2. Produces `attach_annotations(db,owner,transactions:list[FinancialTransaction])->list[FinancialTransaction]`, optional`TransactionResponse.annotations`, `effective_description:str` (własnytytuł or source), bez zastępowania description. `q` szuka źródła + nakładki + własnych tagów/projektu, zachowuje dotychczasowe pola/parametry/pagination.

- [ ] RED: `test_annotations_return_on_list_account_detail_search`, `test_search_finds_source_and_overlay_without_duplicate_count`, `test_annotation_read_is_batched_and_owner_scoped`, `test_source_rules_and_actual_replay_ignore_user_labels`. Oryginalne%/_ traktowane literalnie; wiele tagów daje1wynik; total i offset poprawne; projekty innych użytkowników niewidoczne.
- [ ] GREEN: batch/selectin projection bez domyślnego lazyIO w serializacji; EXISTS wyszukiwania, bez joinmnożącego transakcje. Projektlabel pochodzi z work.Project, nie jest kopiowany do finance. Ani finansowe raporty, ani input reguł/AI/importów nie używają effective_description zamiastsource.
- [ ] VERIFY: focusedread/search/originaltransactionsearch/ruleevents/Actualhistorytest. ExpectedPASS; liczba query nie rośnie liniowo z liczbą transakcji.
- [ ] COMMIT `feat: wyświetlaj i wyszukuj oznaczenia transakcji`.

### Task 4: Edytor, regresje i odbiór całości

**Files:** Create `frontend/src/api/transactionAnnotations.ts`, `frontend/src/api/transactionAnnotations.test.tsx`, `frontend/src/components/finance/TransactionAnnotationsDialog.tsx`, `frontend/src/components/finance/TransactionAnnotations.test.tsx`, `frontend/e2e/transaction-annotations.spec.ts`; modify `frontend/src/api/finance.ts`, `frontend/src/components/finance/AccountTransactions.tsx`, `frontend/src/components/finance/AccountTransactions.test.tsx`, `docs/CHANGELOG.md`, `docs/TASKS.md`, `docs/JOURNAL.md`; create `docs/audits/2026-11-12-transaction-annotations-local.md`.

**Interfaces:** `useTransactionAnnotations(id:string|null)`, `useUpdateTransactionAnnotations()`, `useAnnotationTags(q:string)` konsumują exactHTTP Task2; istniejący useProjects bezstatusfilter. Dialog props`{transactionId:string,onClose:()=>void}`, akcja „Opis i oznaczenia”, oryginalnyopis readonly, optionaltitle/note/tagpicker/projectselect, Zapisz/Anuluj. Wprowadzone tagi lokalne aż doPUT. Idempotencykey dla danej intencji zachowany po niepewnej odpowiedzi; zmiana formularza tworzy nową intencję.

- [ ] RED: frontend`import opens descriptive editor without money fields`, `creates and reuses tags without writes before Save`, `cancel and409 preserve original and user draft`, `clear overlay restores source`, `loan annotations do not enable categories`; testmutation payload ma wyłącznie annotations/version/snapshot. Nie dezaktywować starego niezależnego edytora dat podczas zastąpienia inlineopis UI.
- [ ] GREEN: istniejący styl dialogów bez redesignu aplikacji; efektywna nazwa w wierszu, oryginał w edytorze, tagbadges/projectlabel. Limity zserwera, polskie etykiety/keyboard/a11y, bez HTML. Zapis invaliduje list/detail/search/annotations, bez niepotrzebnych write innych domen.
- [ ] VERIFY: pełnevitest/ESLint/tsc/build i Playwright375/1440 annotations+categorization; syntetyczne manual/import/loan, screensreview i zero realAPI. ExpectedPASS; istniejący chunkwarning jawny.
- [ ] VERIFY: pełnepytest na własnym no-portPG; poprawnakolekcja conftest, exactJUnitunion/sourcehash; jedno niezależne review całości, jedno TDDfixpass ważnych uwag. Expected0Critical/Important, zero pominiętych testów (proxyinfra osobno udokumentowane).
- [ ] DOCS/localcommit po bramkach; cleanup wyłącznie własnych idle testresources. `feat: edytuj opisowe oznaczenia transakcji`. Bez merge/push/deploy.

## Self-review

Zakres użytkownika pokrywa Tasks1–4. Interfejsy Task1→2→3→4 jawne; oryginalny
opis i project_id nie są duplikowane. Wszystkie5ReviewFocus mają testownera.
Migracja/FK istniejących projektów wymaga preflight i zatwierdzenia planu, nie
zgody na automatyczną naprawę danych. Domyślne limity i wyszukiwanie to propozycje
autora, nie przypisane użytkownikowi wymagania. Wykonanie natywne proponowane;
bez implementacji przed akceptacją planu.
