# Edycja i usuwanie transakcji — specyfikacja

## Cel

Umożliwić korektę i usunięcie transakcji bezpośrednio z listy transakcji, bez
nowych modeli ani migracji. Edycja obejmuje opis i datę; usunięcie usuwa
transakcję wraz z postingami (kaskada).

## Backend

- `delete_transaction(db, user_id, transaction_id) -> bool`: usuwa wyłącznie
  własną transakcję; postingi usuwane kaskadowo przez FK `ondelete=CASCADE`.
- `DELETE /transactions/{transaction_id}` → 204; brak/cudza → 404.
- Istniejący `PATCH /transactions/{transaction_id}` (opis, data) pozostaje
  wykorzystany do edycji.

## Frontend

- Hooki `useUpdateTransaction` (PATCH opis/data) i `useDeleteTransaction`
  (DELETE); invalidacja transakcji, kont, podsumowań.
- Lista transakcji `TransactionList` w `AccountTransactions` dostaje per wiersz:
  - edycję inline opisu i daty (przycisk „Edytuj" → formularz z polami opis/data,
    „Zapisz"/„Anuluj");
  - usunięcie z `window.confirm` (treść z opisem transakcji), disabled podczas
    pending, błąd inline.

## Ograniczenia

- Zmiana kwoty/konta/kategorii pozostaje poza zakresem (usuń + dodaj ponownie
  formularzem ręcznym).
- Edycja opisu transakcji zaimportowanej z Actual (prefiks `[actual:{uuid}]`)
  usuwa znacznik idempotentności re-importu — udokumentowane, nie blokowane.

## Testy

Backend: usunięcie własnej transakcji i kaskada postingów; cudza/brak → False/404.
Frontend: hooki, edycja inline (opis/data), usunięcie z potwierdzeniem i
pending-disable.
