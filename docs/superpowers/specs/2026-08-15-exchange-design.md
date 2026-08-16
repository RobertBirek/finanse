# Przewalutowanie (exchange) PLN↔EUR/USD — specyfikacja

## Cel

Umożliwić ręczne przewalutowanie między kontem PLN a kontem EUR/USD z kursem
NBP (automatycznym) lub ręcznym, zapisując obie rzeczywiste kwoty i rzeczywisty
kurs jako transakcję typu `exchange` w księdze podwójnego zapisu.

## Zakres

Formularz na `/finances/transactions` z typem „Przewalutowanie": konto źródłowe,
konto docelowe (różna waluta, jedno z nich PLN), kwota w walucie źródłowej,
opcjonalny kurs ręczny (domyślnie NBP), data, opis.

## Backend

- `POST /finance/transactions/exchange` z ciałem `{from_account_id, to_account_id,
  from_amount, fx_rate?, transaction_date?, description}`.
- Walidacja: konta należą do użytkownika, aktywne, różne, różne waluty; dokładnie
  jedno konto jest PLN (przewalutowania krzyżowe EUR↔USD poza zakresem).
- Kurs: ręczny `fx_rate` (źródło `manual`) albo NBP (`nbp` /
  `nbp_previous_business_day`); brak kursu → 422.
- Wyliczenie: `base = round(from_amount × fx_rate_from)`, `to_amount =
  round(base / fx_rate_to)`. Postingi: źródło `debit`, cel `credit`, obie nogi z
  tym samym `base_amount_pln` (suma zero zachowana), `fx_rate` per waluta nogi
  (PLN = 1.0).
- Serwis buduje postingi i deleguje do istniejącego `create_transaction`.

## Frontend

- Hook `useCreateExchange` → POST `/finance/transactions/exchange`.
- W `TransactionForm` czwarty typ „Przewalutowanie": pola konto „z"/„do"
  (aktywne, różna waluta, jedno PLN), kwota, opcjonalny kurs ręczny, data, opis.
  Submit wywołuje hook exchange zamiast `buildTransactionPostings`.

## Poza zakresem

- Przewalutowania krzyżowe EUR↔USD; prowizja jako osobny koszt (osobna
  transakcja wydatku); automatyczne podpowiadanie kursu przed zapisem.

## Testy

Backend: walidacja kont/walut, wyliczenie kwot i sumy zero, kurs NBP vs ręczny,
brak kursu → błąd. Frontend: hook, pola formularza, submit exchange.
