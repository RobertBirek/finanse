# Actual Budget Import — Design Spec

Data: 2026-08-11 | Status: approved

## Overview

Jednorazowy skrypt CLI migrujący dane z Actual Budget (SQLite) do Personal Advisor (PostgreSQL, double-entry ledger). Skrypt odpala się z kontenera backendu PA.

**Zakres:** 18 kont, 54 kategorie, 866 transakcji (2025-2026).

## Architecture

```
backend/scripts/migrate_actual.py   ← skrypt CLI
backend/app/finance/service.py      ← istniejące serwisy PA (używane do zapisu)
backend/app/finance/models.py       ← istniejące modele SQLAlchemy
```

**Przebieg (3 fazy):**

1. **Odczyt** — rozpakowanie ZIP z `.blob` Actual, odczyt `db.sqlite` przez `sqlite3`
2. **Mapowanie** — Actual accounts/categories/transactions → PA accounts/categories/transactions+postings
3. **Zapis** — INSERT przez istniejące serwisy PA, z walidacją double-entry invariant

Flagi: `--dry-run` (tylko walidacja i raport) vs `--execute` (zapis do DB).

## Data Sources (Actual SQLite)

Tabele odczytywane z `db.sqlite`:

| Tabela | Kolumny |
|--------|---------|
| `accounts` | id, name, offbudget, closed, tombstone |
| `categories` | id, name, is_income, cat_group, tombstone |
| `category_groups` | id, name |
| `transactions` | id, isParent, isChild, parent_id, acct, category, amount, description, notes, date, transferred_id, tombstone |
| `payees` | id, name, transfer_acct |
| `payee_mapping` | id, targetId, payeeId |

Filtrujemy `tombstone=0`. Daty w formacie `YYYYMMDD` INTEGER → `datetime.date`.

## Mapping Rules

### Accounts

1:1 mapowanie. Identyczna nazwa. Typ wnioskowany z `offbudget`:
- `offbudget=0` → `checking`
- `offbudget=1` → `savings`

Waluta wykrywana z nazwy konta:
- "Revolut EU" lub zawiera "EU" → `EUR`
- "Revolut USD" lub zawiera "USD" → `USD`
- Pozostałe → `PLN`

### Categories

1:1 mapowanie. Typ z `is_income`:
- `is_income=0` → `expense`
- `is_income=1` → `income`

Category groups z Actual ignorowane (brak odpowiednika w PA).

### Transactions

**Przypadek 1: Zwykła transakcja (expense/income)**

Filtrujemy: `isParent=0`, `isChild=0`, `transferred_id IS NULL`.

```
financial_transaction:
  type = "expense" jeśli amount < 0, inaczej "income"
  description = nazwa payee z payee_mapping + ewentualne notes

Posting 1: account_id=konto_źródłowe, category_id=NULL, direction=credit, source_amount=|amount|
Posting 2: account_id=konto_źródłowe, category_id=kategoria, direction=debit, source_amount=|amount|
```

**Przypadek 2: Transfer wewnętrzny**

Wykrywamy: dwie transakcje Actual z tym samym `transferred_id` (jedna ujemna, jedna dodatnia).

```
financial_transaction:
  type = "transfer"
  description = "Transfer: [konto_źródłowe] → [konto_docelowe]"

Posting 1: account_id=konto_źródłowe, direction=credit, source_amount=|amount|
Posting 2: account_id=konto_docelowe, direction=debit, source_amount=|amount|
```

**Przypadek 3: Split transaction**

Wykrywamy: `isParent=1` → jedna transakcja PA z N postingami.

```
financial_transaction:
  type = "expense"
  description = wspólny opis ze wszystkich childów

Posting 1: account_id=konto, direction=credit, source_amount=suma_childów
Posting 2..N: account_id=konto, category_id=kategoria_childa, direction=debit, source_amount=kwota_childa
```

### FX Rates

Dla transakcji w EUR/USD:

- NBP API: `https://api.nbp.pl/api/exchangerates/rates/A/{waluta}/{data}/`
- `base_amount_pln` = `source_amount` × kurs NBP (zaokrąglone do groszy)
- `fx_rate_source = 'nbp'`
- Cashowanie: ten sam dzień i waluta pobierane raz

Dla PLN: `fx_rate=1.0`, `base_amount_pln=source_amount`.

Przy błędzie NBP: `fx_rate_source='nbp_error'`, `base_amount_pln=source_amount` (log WARNING).

## Idempotency

Każda transakcja PA dostaje `source='actual'` i oryginalny Actual UUID w polu `description` z prefixem `[actual:{uuid}]`. Żadnych nowych kolumn — `description` to Text, pomieści prefix + oryginalny opis.

Przed importem każdej transakcji: sprawdzenie `SELECT 1 FROM financial_transactions WHERE source='actual' AND description LIKE '[actual:{uuid}]%'`. Jeśli istnieje → pomiń.

## Error Handling

| Błąd | Akcja |
|------|-------|
| Brak kategorii w mapowaniu | WARNING, pomiń transakcję |
| Brak konta w mapowaniu | ERROR, zatrzymaj migrację |
| Błąd NBP API | WARNING, `fx_rate_source='nbp_error'`, kontynuuj |
| Split z sumą childów = 0 | WARNING, pomiń |
| Double-entry invariant naruszony | ERROR, zatrzymaj migrację |

## Output Files

| Plik | Zawartość |
|------|-----------|
Pliki zapisywane do `backend/scripts/output/` (tworzonego automatycznie):

| Plik | Zawartość |
|------|-----------|
| `migration_log.json` | Pełne mapowanie Actual ID → PA ID, lista błędów/ostrzeżeń, statystyki |
| `migration_report.txt` | Raport czytelny dla człowieka |

## Dry-run Mode

`--dry-run` wykonuje fazy 1 i 2 (odczyt + mapowanie), sprawdza wszystkie invarianty, wypisuje pełny raport — ale NIE zapisuje nic do bazy PA.

## Excluded Data

Świadomie pomijane w v1 migracji:
- `payees` (nazwy są w `description` transakcji)
- `rules` (brak odpowiednika auto-kategoryzacji w PA)
- `schedules` (brak cyklicznych transakcji w PA)
- `zero_budgets` (brak budżetów kopertowych w PA)
- `tags` (brak tagów w PA)
