# Ręczny zwrot wydatku

## Approved description / Spec

Użytkownik zatwierdził w czacie: opcja „Zwrot wydatku” w transakcjach, konto,
kategoria wydatkowa i dodatnia kwota. Zwiększa saldo i zmniejsza wydatki kategorii,
nie przychody. Zwrot częściowy bez wskazania zakupu. Testy sald/raportów/budżetów.
Implementacja lokalna, bez wdrożenia, merge lub push.

## Global Constraints

- Existinglinkedworktree feat/financial-document-workflow, base d09ee8a; zachować
  unrelateddirtydocs/audity. main ma tylko nowszą dokumentację0a3cb5b.
- PostgreSQL źródłem prawdy, groszeBIGINT, dwie przeciwstawne dodatnie postings.
- Nie dodawać typuDB: zwrot to expense z odwróconymi kierunkami jak import/card.
- Oddzielny mały endpoint ze ścisłym schema; postings/directions/source powstają
  wyłącznie na serwerze. Nie osłabiać walidacji zwykłych transakcji lub importów.
- Tak jak ręczny wydatek: aktywne kontoPLN i aktywna kategoriaexpense. Nie rozszerzać
  zakresu na FX, automatyczne reguły, linkowanie zakupu, przebudowę raportów.
- Data zwrotu określa miesiąc rozliczenia. Brak limitu do konkretnego zakupu, bo
  użytkownik jawnie wybrał zwrot bez powiązania. Samodzielny zwrot jest dozwolony.
- Testy backendu tylko we własnym PostgreSQL bez portów produkcyjnych (runner
  w jego namespace), role migration zgodne z istniejącym safetyguard.

## Review Focus

- Brak możliwości ominięcia owner/type/active/PLN/positiveamount i zwykłych guardów.
- Saldo wzrasta, income bez zmian, expenses/category/budgetmaleją, nonbudget flags
  serwerowe. Cykle miesięczne, częściowe/nadwyżkowe zwroty, storno/usunięcie.
- Refund nie wpada do nowychexpensesautocategorization/LLM lub dopasowań zapłaty.
- Frontend nie wysyła ręcznych postings dla zwrotu, reset selection po zmianie
  typu, pending/error/invalid kwota/refreshcache. Nie udawać nowegoAPI na produkcji.

### Task 1: Serwerowa komenda ręcznego zwrotu

**Interfaces:** POST /finance/transactions/expense-refund
`{account_id,category_id,amount_minor,transaction_date,description}` -> TransactionResponse.
StrictInt0<amount<=MAX_SAFE, extra forbid, trimmed nonblankdescription/date required.
Service create_manual_expense_refund tworzy expense/manual przez zaufaną ścieżkę
allow_manual_refund; categoryexpense i accountcredit/categorydebit; auditcreate.

- [x] RED test endpoint i odwrócenia kierunków, sald/summary/category/budget, schema,
  owner/active/currency/income denial, brak efektów ubocznych, ordinaryrouteguard.
  Expected:404missingendpoint, nie błędy środowiska.
- [x] GREEN minimalne schema/service/router + trustedvalidation, audit i wykluczenie
  nowychrefund z eventów automatycznej kategoryzacji. Expected:focusedPASS.
- [x] Ruff/mypy, pełny backend w niezależnych shardach z exacttestcount/JUnit/sourcehash,
  bezskip/error, proxy jawnie odrębne. Expected:PASS.

### Task 2: Opcja zwrotu w istniejącym formularzu

**Interfaces:** useCreateExpenseRefund, sam identyczny POSTpayload; cache refresh przez
invalidateFinanceLedger, sessionVersionguard. Form typexpense_refund tylko w UI.

- [x] RED formularz wybór kategoriiexpense, dodatnia kwota, właściwypayload, pending/error,
  reset oraz APIhook/cache. Expected:missingoption/hook lub zwykłyexpensepayload.
- [x] GREEN hook i nowy typ formularza, opis skutku „Pomniejsza wydatki kategorii;
  nie jest przychodem”. Data/description jak zwykły wpływ, bez purchase-date.
- [x] Frontendpełnyvitest/lint/tsc/build, syntetyczny Playwright desktop/mobile.
  Expected:PASS, brak mutacji realAPI i overflow.
- [x] Jedno freshreview całości, ewentualny jeden TDDfixpass, dokumentacja i localcommit.
  Expected:0Critical/Important, brak wdrożenia. Minor jawnie odłożyć.
