# Osoby i darowizny — Implementation Plan

Etap A wykonany lokalnie (kod79011bc,2026-11-13): backend2468,frontend677,
UI201PASS/1planowyskip. Niezależny review i fix RED→GREEN zakończone. Pełny Ruff
ma3 zastane DTZ007; zmieniony kod lint/typecheck PASS. Brak zgody na merge/push/deploy
i jakiekolwiek produkcyjne zapisy. A2/B nie zostały wykonane. Szczegółowy odbiór:
`docs/audits/2026-11-13-people-gifts-verification.md`; checkboxy poniżej to pierwotny
plan, wykonanie i odchylenia zapisano w ledgerze/raporcie, bez udawania zgody na A2.

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Powiązać rzeczywiste przychody z osobą i pokazać historię darowizn bez
duplikowania pieniędzy; pozostawić zgodny punkt rozszerzenia dla pożyczkodawcy.

**Architecture:** FinancePerson jest osobną ewidencją, nie kontem finansowym.
PersonTransactionLink wskazuje istniejący income; summary wyliczany jest z jednej
nogi bankowej ledger. Kontrolowane komendy domenowe zachowują istniejącą księgę.
Pożyczki wykorzystają dotychczasowe LoanAgreement/LoanInstallment w osobnym etapie.

**Tech Stack:** Python3.12+, FastAPI/Pydantic2, SQLAlchemy2 async, Alembic/PostgreSQL16;
React18/TypeScript, TanStack Query, Tailwind, Vitest/Playwright.

**Spec:** `docs/superpowers/specs/2026-11-12-finance-people-gifts-design.md`

## Global Constraints

- Etap A zaakceptowany do implementacji; nie wdrażać i nie mutować produkcji teraz.
- PostgreSQL source of truth; kwoty BIGINT w najmniejszych jednostkach; baza PLN.
- Każda transakcja minimum2postings, signed debit+ / credit−, suma0.
- Profile osób nie są Account i nie uczestniczą w istniejących sumach majątku/budżetu.
- Same link/unlink: zero zmian transakcji, postingów, źródłowych opisów i importrefs.
- Etap A obsługuje wyłącznie gift_received; pożyczki, zwroty darowizn i alokacje
  wieloosobowe poza tym wdrożeniem. Nie przekształcać darowizn w transfery.
- Kod /opt/finanse oddzielony od infra /docker/finanse; wdrożenie i korekta historii
  są osobnymi zgodami, nie konsekwencją zatwierdzenia planu.
- Natywne `/test`, `/lint`, `/typecheck`, `/migration`, `/migrate`, `/docs` zamiast
  ręcznego odtwarzania komend; testy tylko w testowym środowisku, nigdy produkcyjne fixtures.
- Bez nowych zależności, sekretów i rzeczywistych danych finansowych w repo/tests.

## Review Focus

1. Dwóch właścicieli i identyczne nazwy osób — dostęp tylko do własnych UUID (T1/T2).
2. Dwa równoległe przypisania/archiwizacja/delete — jeden wynik, brak osierocenia (T2/T3).
3. Import z błędną kategorią expense — czytelne odrzucenie bez automatycznej korekty (T2/T5).
4. Summary większe niż jedna strona, różne waluty i podwójny join — liczyć gift raz (T4).
5. Stare konto ze skrótem nie jest osobą ani saldem darowizn — stare total bez zmian (T1/T4/T5).

## Stan zastany i granice etapów

Sprawdzone: `annotation_models.py` dostarcza opis/tagi, nie tożsamość kontrahenta;
`reporting.py` zlicza income wg transaction.date, expense wg purchase_date;
`queries._account_rows` zlicza credit dodatnio, debit ujemnie dla wszystkich typów kont.
`balance_all_pln` obejmuje aktywne off-budget. Nie zmieniać tego globalnie.

`loan_schemas.py` ma raty principal/interest/fees, ale LoanPaymentCreate przyjmuje tylko
transaction_id. `loans.py` dopuszcza wyłącznie prosty transfer spłaty. To nie jest
gotowe księgowanie rozbicia rat. Etap B ma osobne kryteria na końcu tego planu.

### Task 1: Model osoby, powiązanie i addytywna migracja

**Files:**
- Create: `backend/app/finance/person_models.py`, `backend/app/finance/person_schemas.py`
- Modify: `backend/app/finance/models.py` (rejestracja modeli, Account composite unique)
- Create via `/migration`: `backend/migrations/versions/<generated>_finance_people.py`
- Test: `backend/tests/test_finance/test_person_models.py`

**Interfaces:**
- Produces: `FinancePerson`, `PersonTransactionLink`, pola/ograniczenia ze spec.
- Schemas (extra=forbid): `PersonCreate(name: str, reference_account_id: UUID|None)`,
  `PersonUpdate(expected_version: int, name?: str, is_active?: bool,
  reference_account_id?: UUID|None)`; tylko reference_account_id dopuszcza jawne null.
- `PersonResponse(id, name, is_active, version, reference_account_id)`;
  `PersonPage(items: list[PersonResponse], total: int, limit: int, offset: int)`.

- [ ] RED: foreign owner person/txn/account FKs odrzucają commit; duplicate txn link
  i duplicate reference_account odrzucone; usunięcie linked txn RESTRICT; osoby
  o tej samej nazwie dozwolone. Uruchom `/test` na kopii testowej, potwierdź te porażki.
- [ ] GREEN: modele i schematy, Check kind='gift_received', version>0;
  unique(id,user_id) na FinancePerson i Account, composite owner-safe FK.
  Dodać rejestrację w finance.models zgodnie z istniejącym wzorcem annotation_models.
- [ ] `/migration "finance people and gift links"`; obejrzeć SQL. Tylko nowe tabele,
  indeksy/constraints, bez backfillu osób, historii, kont ani kategorii.
- [ ] `/migrate` wyłącznie na izolowanej bazie. Porównać hash starych tabel przed/po;
  `/test`, `/lint`, `/typecheck`: PASS. Commit `feat: modele osób i darowizn`.

### Task 2: Owner-safe polecenia i kontekst transakcji

**Files:**
- Create: `backend/app/finance/people.py`, `backend/app/finance/person_context.py`
- Modify: `backend/app/finance/person_schemas.py`, `backend/app/finance/service.py`
- Test: `backend/tests/test_finance/test_people.py`

**Interfaces:** wszystkie serwisy przyjmują `db: AsyncSession`, `owner: UUID`, nie commitują.
- `create_person(db, owner, data: PersonCreate) -> PersonResponse`.
- `update_person(db, owner, person_id: UUID, data: PersonUpdate) -> PersonResponse`.
- `get_person_link_context(db, owner, transaction_id: UUID) -> PersonLinkContext`:
  `transaction_id`, `snapshot` (sha256), `person: PersonResponse|None`, `eligible: bool`,
  `reason: str|None`. Snapshot to canonical columns transaction + sorted postings +
  date_metadata + protected-ref IDs; użyć categorization_context.columns/digest.
- `GiftLinkRequest(person_id: UUID, expected_transaction_snapshot: str)`;
  `GiftUnlinkRequest(expected_transaction_snapshot: str)`.
- `link_gift(db, owner, transaction_id: UUID, data: GiftLinkRequest, *,
  idempotency_key: str) -> PersonLinkContext` i analogiczny `unlink_gift(...,
  data: GiftUnlinkRequest, *, idempotency_key: str) -> PersonLinkContext`.
- Błędy domenowe z kodem/status: foreign/missing404, invalid422, conflict409.

- [ ] RED: poprawny manual/imported income PLN i poprawny EUR gift; identyczna nazwa
  foreign person →404. Nieaktywny person →409 dla nowego linku, unlink nadal działa.
  Expense-category income, pending, transfer/FX/refund, loan/doc protected →422;
  wszystkie odmowy zachowują pełne hashe danych. Syntetyczny gift10000: saldo banku
  i raporty przed/po link i unlink IDENTYCZNE, summary później będzie10000, nie20000.
- [ ] RED: idempotent replay, zmieniony payload/key409, przypisanie do drugiej osoby409,
  stale snapshot409; concurrent link/link i link/archive nie tworzą niespójnego stanu.
- [ ] GREEN: owner document mutation lock → person row → transaction row, stabilne
  sortowanie UUID gdy więcej wierszy, odświeżenie po oczekiwaniu. Unlink najpierw
  ustala person_id z owner-scoped linku, potem po lockach weryfikuje ponownie.
  Walidacja kształtu i istniejące ledger validators, bez autofixu. Receipt akcje
  `link_person_gift_v1`, `unlink_person_gift_v1`; replay przed sprawdzaniem już zmienionego
  snapshotu. Audit tworzenia/edycji osoby oraz link/unlink z old/new metadata.
- [ ] Sprawdzić account owner/off-budget oraz CAS person version przy zmianie skrótu;
  jawny null odpina. Brak hard delete osoby. Archiwizacja nie kasuje linków.
- [ ] `/test`, `/lint`, `/typecheck`: PASS; commit `feat: powiązania darowizn z osobą`.

### Task 3: Ochrona powiązanej historii przed innymi ścieżkami zapisu

**Files:**
- Create: `backend/app/finance/person_guards.py`
- Modify: `backend/app/finance/transactions.py`, `backend/app/finance/transaction_dates.py`,
  `backend/app/finance/entities.py`
- Test: `backend/tests/test_finance/test_person_guards.py`

**Interfaces:**
- `guard_person_gift_change(db: AsyncSession, owner: UUID, transaction_id: UUID,
  changes: set[str]) -> None`; odrzuca delete/date/pending/financial, jeśli istnieje link.
- `guard_person_reference_account_change(db: AsyncSession, owner: UUID,
  account_id: UUID, changes: dict[str, object]) -> None`; blokuje delete i przejście
  na budget=True przy istniejącym reference_account_id; archive dozwolone.

- [ ] RED: linked txn nie można skasować ani zmienić daty/pending w obu edytorach.
  Własny opis, notatka, tagi i projekt nadal działają; source opis importu nadal chroniony.
  Unlink przywraca poprzednią edytowalność, nie omija import/loan/doc guardów.
- [ ] RED: link/delete i link/date concurrency; account reference/delete i budget-toggle
  concurrency zachowują FK i regułę off-budget. Archiwizacja osoby i konta niezależna.
- [ ] GREEN: dołączyć guards do istniejących serwisów bez zmiany publicznego PATCH
  kwot/kont/type (nadal niedostępne). Person mutations i account mutations wspólnie
  serializowane istniejącym owner lock; nie wprowadzać nowej odwrotnej kolejności.
- [ ] `/test`, `/lint`, `/typecheck`: PASS wraz z dotychczasowymi loans/import/refund;
  commit `fix: ochrona historii powiązanych darowizn`.

### Task 4: Paginowana historia, agregaty i API

**Files:**
- Create: `backend/app/finance/person_reads.py`, `backend/app/finance/person_router.py`
- Modify: `backend/app/finance/person_schemas.py`, `backend/app/finance/router.py`,
  `backend/app/finance/service.py`
- Test: `backend/tests/test_finance/test_person_reads.py`, `test_person_api.py`

**Interfaces:**
- `PersonSummary(person_id: UUID, gift_count: int, received_gifts_pln: int,
  received_by_currency: dict[str, int])`.
- `PersonGiftPage(items: list[TransactionResponse], total: int, limit: int, offset: int)`.
- `list_people(db, owner, *, include_archived: bool=False, reference_account_id:
  UUID|None=None, limit: int=50, offset: int=0) -> PersonPage`.
- `get_person_summary(db, owner, person_id: UUID) -> PersonSummary`;
  `get_person(db, owner, person_id: UUID) -> PersonResponse`;
  `get_person_gifts(db, owner, person_id: UUID, *, limit: int=50,
  offset: int=0) -> PersonGiftPage`; brak osoby404, archiwalna dostępna.
- `/api/finance/people`: GET/POST; `/{person_id}` GET/PATCH;
  `/{person_id}/summary` GET; `/{person_id}/gifts` GET.
- `/api/finance/transactions/{transaction_id}/person-link`: GET/PUT/DELETE;
  PUT/DELETE wymagają `Idempotency-Key` i odpowiedniego body z T2.

- [ ] RED: gift10000PLN + gift200EUR z base90000PLN → summary100000PLN,
  source map PLN10000/EUR20000 (kwoty source w minor; fixture EUR20000), count2;
  dodatkowe tagi nie mnożą sum; limit1 pokazuje1wiersz, summary nadal2.
  Paginacja stabilna dla równych dat, pusty profil0, archiwalny zachowuje historię.
- [ ] RED: foreign owner404, auth/CSRF, walidacja limit/offset422; list filter
  reference_account i include_archived; summary nie zmienia account totals ani raportów.
- [ ] GREEN: grouped SQL po jednej poprawnej nodze account credit; metadata adnotacji
  istniejącymi batch helpers, bez N+1 per transakcja. Ścieżki wpiąć w finance.router
  tak, by dziedziczyły auth/CSRF. Pydantic responses nie serializują lazy relacji ORM.
- [ ] `/test`, `/lint`, `/typecheck`: PASS; commit `feat: API historii darowizn osoby`.

### Task 5: Profil osoby i przypisywanie kolejnych darowizn

**Files:**
- Create: `frontend/src/api/people.ts`, `frontend/src/pages/FinancePeople.tsx`,
  `frontend/src/pages/FinancePersonDetails.tsx`,
  `frontend/src/components/finance/PersonGiftDialog.tsx`
- Modify: `frontend/src/App.tsx`, `frontend/src/components/Layout.tsx`,
  `frontend/src/components/finance/AccountTransactions.tsx`,
  `frontend/src/components/finance/TransactionDetail.tsx`
- Test: analogiczne `.test.tsx`, `frontend/e2e/people-gifts.spec.ts`

**Interfaces:** TanStack hooks `usePeople`, `usePerson`, `usePersonSummary`,
`usePersonGifts`, `usePersonLinkContext`, `useCreatePerson`, `useUpdatePerson`,
`useLinkGift`, `useUnlinkGift`; typy dokładnie jak API T4, kwoty bez float obliczeń.
Trasy `/finances/people`, `/finances/people/:personId`.

- [ ] RED: lista/utworzenie osoby/archiwizacja, profilempty i błąd sieci; wybór osoby
  przy income, link/unlink, stale409 wymaga odświeżenia, brak samoczynnego retry mutacji.
- [ ] RED: historyczny income z kategorią expense wyświetla powód odmowy i nie robi
  PATCH kategorii; po zatwierdzonej korekcie można go przypisać normalnie.
- [ ] RED: konto informacyjne ze skrótem otwiera profil, lecz saldo i account
  transactions pozostają ledgerowe. Osoba bez konta ma pełną historię. Summary nie
  liczy tylko bieżącej strony; konto aktywne/archiwalne nie ukrywa profilu osoby.
- [ ] GREEN: osobne DTO osoby i Account; przycisk do historii, nie zastąpienie salda.
  Dialog tylko dla istniejących transakcji, kontekst ładować po otwarciu, nie N+1
  per wiersz. Inwalidować people/context/history queries po zapisie; brak wysyłania
  kwot, dat i postingów przy linkowaniu. Projekt wizualny zgodny z istniejącym UI.
- [ ] E2E syntetyczne: income → link → profile history → unlink, dwie darowizny od
  tej samej osoby; po drodze salda i reports unchanged, mobile/desktop nawigacja.
- [ ] `/test`, `/lint`, `/typecheck` i docelowe Playwright PASS; commit
  `feat: profile osób i historia darowizn`.

### Task 6: Odbiór kodu i projekt osobnej korekty historycznej

**Files:**
- Create: `docs/audits/<execution-date>-people-gifts-verification.md`
- Modify: `docs/CHANGELOG.md`, `docs/TASKS.md`, `docs/JOURNAL.md`
- Prywatny operator/manifest/snapshot/receipt: poza repo, owner-bound, bez sekretów w logach.

**Interfaces:** A2 opisany w spec; NIE uruchamiać dawnego `approved_income_to_transfer_v1`.
Do przygotowania korekty nowa mała komenda domenowa z dokładnymi ID/pinami i testami;
nie dodawać obejścia istniejących publicznych API. Każdy jej zapis wymaga nowej zgody.

- [ ] Odczyt końcowego diffu i jeden niezależny przegląd całości, w szczególności
  composite owners, idempotency, foreign protections i brak modyfikacji księgi przez link.
- [ ] `/test`, `/lint`, `/typecheck`, migracja/odczyt na klonie oraz E2E: zachować dowody.
  Opisać dokładnie znane ograniczenia i oddzielić oldaccount balance od person summary.
- [ ] Przygotować readonly propozycję A2 dla zatwierdzonych gift incomes: category
  income Darowizna, type income bez zmiany, link do jawnej osoby, zero nowych transakcji.
  Porównać zmiany raportów miesięcznie według obu osi dat, nie zakładać neutralności.
- [ ] Osobno poprosić o zgodę na merge/push/deploy/migrację. Dopiero po wdrożeniu
  i zatwierdzeniu preview można planować wykonanie A2 (backup/restore/rehearsal/review).
- [ ] `/docs`, commit dokumentacji. Handoff zawiera NO FINANCIAL WRITES, dopóki A2
  faktycznie nie przejdzie osobnej akceptacji i weryfikacji.

## Etap B: pożyczki i raty — roadmapa, NIE zadania do wykonania w tym planie

1. Dodać owner-safe lender_person_id do istniejącego LoanAgreement i osobny link
   wypłaty do TEJ SAMEJ transakcji bankowej. NULL zachowuje stare umowy bez osoby.
2. Specyfikacja komendy wypłaty: nie income; bank credit/debt debit, zero signed sum,
   nowe vs już zaimportowane wpływy rozdzielone, jawne uzgodnienie reklasyfikacji.
3. Specyfikacja alokacji rzeczywistej spłaty: principal/interest/fees osobno, brak
   kopiowanego ręcznego salda. Suma allocation=payment; jedno obciążenie banku.
   Powiązać z existing installments bez uznawania samego planu za zapłatę.
4. Najmniejsza pierwsza wersja B: PLN, pożyczka otrzymana, jawnie ustalone raty,
   częściowe płatności, jeden przelew do jednej raty; nadpłaty i wieloratowe przelewy
   wymagają świadomej decyzji, nie automatycznego zgadywania.
5. Osobny plan i TDD: loan120000minor/12×10000, po pierwszej racie debt−110000,
   income0/expense0; split payment12000 → principal10000, expense2000. Pożyczka
   i darowizna tej samej osoby nie sumują się w „Otrzymane darowizny”. Testy
   regresji Q7, stare transfery nadal requires_accounting_review=True.
6. Profil osoby otrzyma pożyczki z odnośnikiem do umów, pozostałym kapitałem z
   uzgodnionej księgi i kolejną ratą. Dług wpływa na majątek; nie jest ukrytą statystyką
   darczyńcy. Import/FX/pożyczki udzielane/umorzenia nie rozszerzają zakresu samoczynnie.

## Self-review i przekazanie

- [x] Model osoby neutralny wobec gift/loan; jedna informacja w wielu widokach.
- [x] T1–T5 pokrywają FK/owner, receipts/locks, mutatory, agregaty i przyszłe gifts.
- [x] Review Focus przypisany do testów konkretnych zadań.
- [x] Builder check projektu: `ses_e2e1a50d3ffeRhrgtmvHnGodBt`: nothing important left.
- [x] B jawnie roadmapą; brak obietnicy obecnego księgowania rat i ukrytych podatków.
- [x] Akceptacja projektu i planu przez użytkownika; wybrał wykonanie natywne.

Rekomendowane wykonanie A: natywne w izolowanym worktree z jednym niezależnym
przeglądem całości; osobne pełne bezpieczeństwo operacji A2. Ten dokument nie jest
zgodą na deploy ani zmianę historii użytkownika.
