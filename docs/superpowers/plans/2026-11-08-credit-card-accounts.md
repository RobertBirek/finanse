# Typ konta „Karta kredytowa” i przegląd wielu kart — implementation plan

> **For agentic workers:** Use executing-plans, implement inline with TDD and one whole-branch review.

**Goal:** Warunki karty są częścią tworzenia/edycji konta, a zakładka kart jest przeglądem wielu niezależnych kart.
**Architecture:** Nowy typ `credit_card`, istniejące profile/ledger/rozliczenia bez duplikowania. Jeden zapis konta z opcjonalnym zagnieżdżonym `credit_card` (CardConfig) w tej samej transakcji. Zbiorczy odczyt lekkich podsumowań kart; szczegóły dotychczasowych rozliczeń oddzielnie.
**Tech Stack:** FastAPI, SQLAlchemy/PostgreSQL, Alembic, React/TypeScript, TanStack Query, istniejące komponenty i tokeny UI.
**Spec:** Zatwierdzony sześciopunktowy plan w rozmowie (user „tak”, potem Build „ok, działaj”). Niniejszy dokument utrwala jego szczegóły wykonawcze, nie rozszerza zakresu.

## Global Constraints
- Lokalna implementacja; brak merge/push/deploy/produkcyjnej migracji lub konfiguracji Velo bez osobnej zgody.
- „Kredytowe” (`credit`) pozostaje odrębnym typem; migracja zmienia tylko konta powiązane z istniejącym profilem karty.
- Karty nadal tylko PLN; historia/postings/salda bez zmian; transfer nie jest kosztem.
- Jeden profil per konto, wiele kart per użytkownik; właściciel, blokady i wersja profilu zachowane.
- Warunki planów niezależne; istniejące odsetki/spłaty/wyciągi/estymacje bez zmiany semantyki.
- Tylko własny nowy PostgreSQL network=none/noports, po jawnej zgodzie użytkownika; cleanup tylko jego ID/volume.
- Istniejące dwa robocze raporty Velo/Q7 pozostają nietknięte i poza commitami.

## Review Focus
- Niepoprawne warunki/stara wersja: ani konto ani profil nie zapisują się częściowo (Task1).
- Zwykłe konto kredytowe bez profilu nie staje się kartą; migracja nie odgaduje typu po nazwie (Task1).
- Dwie karty i inny właściciel: brak przecieku/stanu wspólnego, błędy/nieaktywność nie są zerowym saldem (Task1–3).
- PATCH koloru/nazwy istniejącej karty nie wymaga przesyłania jej warunków i nie zmienia ich wersji (Task1–2).
- Linki/reload/back i stare `?account=` nadal prowadzą do właściwej karty (Task3).

## Task 1 — atomowy zapis, typ, zbiorczy odczyt i migracja
**Files:** backend/app/finance/{schemas.py,entities.py,router.py,credit_cards.py,credit_card_schemas.py}; backend/migrations/versions/ (nowa migracja po00a9); backend/tests/test_finance/test_credit_card_accounts.py; istniejące test_credit_cards.py (oczekiwany typ).
**Interfaces:** AccountCreate/Update.credit_card: CardConfig | None; AccountResponse.credit_card: CardSettings | None; CardSettings=warunki+version, bez historii. Brak pola w PATCH zachowuje profil, null nie usuwa. Nowy typ wymaga profilu przy create/konwersji. create_account/update_account zachowują sygnatury i zwracają Account. Błędy wersji trafiają w409, nie w500.
**Summary:** GET `/api/finance/credit-cards`, list[CardSummary], owner-scoped, tylko typcredit_card (także inactive z flagą); account_id/name/is_active + limit/debt/available/pending/overpayment/overlimit. Agregacja ledger dla wszystkich kart na dziś, bez list planów/wyciągów i bez detail()perrow.
- [ ] RED: tworzenie i konwersja konta z profilem, dwie niezależne karty, brak/niepoprawny profil, niePLN/loanlink, staleversion/atomowość, PATCHkolor bez zmiany profilu, owner404/anon401, zbiorcze kwoty/filtrowanie/nieaktywne.
- [ ] GREEN: nowe schematy, wspólna blokada mutacji przed lockiem konta, istniejący configure(), jeden commit zależności get_db; private transient profile response/property bez dodatkowej kolumny.
- [ ] RED→GREEN migracji: zmień typ tylko JOIN credit_cards(account_id,user_id), zachowaj wiersze/profil/ledger i genericcredit; downgrade nie kasuje danych profilu.
- [ ] focused backend + ruff/mypy PASS; commit backend po zielonym gate.

## Task 2 — warunki w formularzu tworzenia i edycji konta
**Files:** frontend/src/api/finance.ts; frontend/src/api/creditCards.ts; frontend/src/components/finance/{accountSettings.ts,AccountSettingsRow.tsx,CreditCardFields.tsx}; frontend/src/pages/FinanceAccounts.tsx; odpowiadające testy.
**Interfaces:** Account.credit_card: CardSettings | null (optional for old fixtures); AccountCreateInput/AccountUpdateInput.credit_card?: CardConfig; useAccounts zawiera tylko małe warunki profilu. Shared pola mapują pieniądze przez istniejący parser groszy, APR jako string, wersję z serwera; brak domyślnych bankowych warunków.
- [ ] RED: nowa opcja typu; pola tylko dla karty, poprawny jeden payload create/PATCH, edit istniejących wartości, cancel/reopen/reset, błąd zachowuje wpisy, PLN/required/decimal, zwykłe konto bez zagnieżdżonych pól.
- [ ] GREEN: wspólny komponent pól draft+validation używany w obu formularzach; waluta zablokowanaPLN dla karty; całe konto zapisuje się jednym żądaniem.
- [ ] vitest focused + eslint/tsc PASS.

## Task 3 — przegląd kart i oddzielne rozliczenia
**Files:** frontend/src/pages/{FinanceCreditCards.tsx,FinanceCreditCardDetails.tsx}; frontend/src/App.tsx; frontend/src/components/finance/{AccountTransactions.tsx,CardAccountSummary.tsx}; frontend/src/api/creditCards.ts; testy + frontend/e2e/credit-cards.spec.ts.
**Interfaces:** useCreditCards() summary query; list route `/settings/finances/cards`; detail route `/settings/finances/cards/:accountId`; edit link `/settings/finances/accounts?edit=:accountId`; legacy `cards?account=` redirect detail.
- [ ] RED: dwie karty, brak innych kont, trzy kwoty na kartę, nieaktywność, empty/error/loading; list bez konfiguracji i fetchy fullhistory; poprawne linki/samodzielnyreload szczegółów oraz queryedit właściwego konta.
- [ ] GREEN: przenieś istniejące rozliczenia do szczegółów, usuń Profile z listy/szczegółów; istniejące funkcje rozliczeń zachowane; gate podsumowania przy transakcjach zmieniony zcredit nacredit_card.
- [ ] Vitest, lint, tsc, build i E2E desktop/mobile/light/dark/Axe PASS; commit frontend.

## Task 4 — odbiór i dokumentacja
- [ ] Pełny pytest (integration na własnej bazie), vitest, lint/typecheck, build, E2E; potwierdź zero nieoczekiwanych skips/failures, zachowaj źródła/logi.
- [ ] Jeden niezależny whole-branch review; Important/Critical popraw w jednej rundzie RED→GREEN i ponów właściwy suite; minors odnotuj.
- [ ] Zaktualizuj CHANGELOG/TASKS/JOURNAL i instrukcję kart, raport odbioru z ograniczeniami; docscommit.
- [ ] Po dowodach usuń tylko własny PG i jego anonimowy wolumen po porównaniu DockerID. Zostaw gałąź lokalnie, bez wdrożenia.
