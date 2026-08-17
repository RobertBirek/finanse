# CRUD kont i kategorii z dezaktywacją — specyfikacja

## Cel

Domknąć CRUD kont i kategorii: tworzenie, edycja, dezaktywacja/aktywacja i
usuwanie. Reguła nadrzędna użytkownika: encji z zapisami/powiązaniami **nie
można usunąć** — można ją tylko zdezaktywować i ukryć z list wyboru; encje bez
zapisów można usunąć twardo.

## Zasada usuwania

- Konto z postingami lub pozycjami schedulera → `409` z komunikatem
  „zdezaktywuj zamiast usuwać"; bez zapisów → `204`.
- Kategoria z postingami, pozycjami schedulera, budżetami lub kategoriami-dziećmi
  → `409`; bez powiązań → `204`.
- Referencja `payday_account_id` (FK `SET NULL`) nie blokuje usunięcia.

## Backend

1. Migracja: `is_active` (`Boolean`, `server_default=true`) na `categories`.
2. Schematy: `CategoryUpdate.is_active`; `CategoryResponse.is_active`.
3. Serwis:
   - `delete_account` / `delete_category` — sprawdzają powiązania (postingi,
     scheduler, budżety, dzieci) i zwracają/blokują zgodnie z zasadą;
   - `update_category` zapisuje `is_active`.
4. Router: `DELETE /accounts/{account_id}` i `DELETE /categories/{category_id}`
   → 204 / 404 (brak/cudza) / 409 (ma zapisy).
5. Walidacja wejścia: tworzenie transakcji, pozycji schedulera i budżetu z
   **nieaktywnym** kontem lub kategorią → 422.

## Frontend

1. Nowa podstrona `/finances/accounts` (link „Konta" w sidebarze): zarządzanie
   kontami i kategoriami — tworzenie, edycja (nazwa/typ/budżetowe, kategorie:
   nazwa/typ/rodzic), przełącznik aktywności, usuwanie (błąd 409 pokazany z
   komunikatem o dezaktywacji).
2. Hooki: `useUpdateAccount`, `useDeleteAccount`, `useUpdateCategory`,
   `useDeleteCategory` (istnieje nieużywany `useCreateAccount`).
3. Filtrowanie nieaktywnych w listach/selectach (formularz transakcji, scheduler,
   budżety, konto wypłaty, lista kont na `/finances`); nieaktywne widoczne
   wyłącznie na stronie zarządzania.

## Poza zakresem

- Przywracanie kont przez re-import Actual; historia raportów obejmuje nadal
  nieaktywne kategorie (dezaktywacja nie wymazuje przeszłości).

## Testy

Backend: blokada usuwania przy postingach/schedulerze/budżecie/dzieciach,
usunięcie pustych, 404 cudze, `is_active` kategorii, 422 dla nieaktywnych na
wejściu. Frontend: hooki, strona zarządzania, filtrowanie selectów.
