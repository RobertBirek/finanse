# Ręczne księgowanie transakcji — specyfikacja

## Cel

Umożliwić ręczne wprowadzanie transakcji przychodu, wydatku i transferu między
kontami przez interfejs, bez nowych tabel ani migracji. Transakcja trafia do
księgi podwójnego zapisu przez istniejący serwis domenowy finance.

## Zakres

Formularz na `/finances/transactions` tworzy:

- **przychód** — konto + kategoria typu `income`, kwota PLN;
- **wydatek** — konto + kategoria typu `expense`, kwota PLN;
- **transfer** — konto źródłowe i docelowe, kwota PLN, bez kategorii.

Każda transakcja zapisywana jest przez `POST /finance/transactions` z dwoma
postingami; serwis `create_transaction` zachowuje invariant sumy zero.

## Konwencja kierunków

Zgodnie z konwencją księgi `balance = credit − debit`:

- przychód: posting konta `credit`, posting kategorii `debit`;
- wydatek: posting konta `debit`, posting kategorii `credit`;
- transfer: konto źródłowe `debit`, konto docelowe `credit`.

Kierunki buduje wyłącznie frontendowy helper `buildTransactionPostings`,
zgodny z tą konwencją i pokryty testami jednostkowymi.

## Walidacja

- kwota dodatnia w PLN (grosze), konwersja `parsePlnToGrosze`;
- konto aktywne w walucie PLN; dla transferu dwa różne konta;
- kategoria wymagana dla przychodu/wydatku, zgodna z typem;
- data domyślnie dzisiaj (lokalnie), możliwa zmiana; opis wymagany.

## Frontend

Komponent `TransactionForm` na stronie Transakcje: selektor typu, pola zależne
od typu, kwota, data, opis; przycisk submit disabled podczas mutacji; błąd API
inline; po sukcesie reset formularza i komunikat. Brak optimistic updates.

## Poza zakresem

- Przewalutowanie (exchange), kwoty w EUR/USD i kursy FX;
- edycja i usuwanie istniejących transakcji;
- masowy import i integracje bankowe.

## Testy

Frontend: `buildTransactionPostings` dla trzech typów (kierunki, kwoty, suma
zero); formularz (przełączanie typów, filtrowanie kategorii, budowa postingów,
walidacja, submit i reset). Backend bez zmian — istniejące testy księgi
pokrywają `create_transaction`.
