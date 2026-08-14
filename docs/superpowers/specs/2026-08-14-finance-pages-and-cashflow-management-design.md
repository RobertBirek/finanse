# Strony finansowe i zarządzanie płynnością — specyfikacja

## Cel

Udostępnić kompletny, kontrolowany przez użytkownika interfejs finansowy:
zarządzanie cyklem wynagrodzenia i miesięcznym harmonogramem, prognozę płynności
oraz użyteczne podstrony finansów. Actual Budget pozostaje źródłem danych
historycznych, a księga Personal Advisor pozostaje źródłem prawdy aplikacji.

## Zakres tras

- `/finances` jest przeglądem: miesięczne podsumowanie, konta budżetowe i
  pozabudżetowe oraz skrócona karta płynności z przejściem do szczegółów.
- `/finances/transactions` pokazuje historię transakcji według wybranego konta.
- `/finances/cashflow` jest centrum cyklu wynagrodzenia, prognozy i harmonogramu.
- `/finances/budgets` pokazuje rzeczywiste wydatki wybranego miesiąca według
  kategorii i grup. Nie przedstawia limitów, ponieważ model limitów budżetowych
  nie istnieje.
- `/finances/reports` pokazuje dla wybranego miesiąca przychody, wydatki, bilans
  oraz zestawienie kategorii.

Konfiguracja kontekstowego sidebara wskazuje wyłącznie powyższe istniejące trasy.
Pozycje bez implementacji zachowują oznaczenie „Wkrótce”.

## Centrum płynności

### Ustawienia

Użytkownik zapisuje dzień spodziewanej wypłaty (1–28), docelowe konto budżetowe,
horyzont prognozy (1–90 dni) oraz tolerancję opóźnienia (0–14 dni). Formularz
wyświetla konta budżetowe jako możliwe konto wypłaty. Backend pozostaje
autorytatywny dla walidacji własności, statusu konta i waluty.

### Harmonogram

Użytkownik może utworzyć, zmienić, dezaktywować lub usunąć miesięczną pozycję
przychodu albo wydatku. Formularz wymaga nazwy, typu, konta budżetowego,
kategorii, waluty, dnia miesiąca (1–28) i metody kwoty:

- `fixed`: dodatnia kwota w PLN, zapisywana jako całkowita liczba groszy;
- `last_actual`: kwota odczytana z ostatniej zgodnej rzeczywistej transakcji.

Interfejs pokazuje wyłącznie kategorie zgodne z wybranym typem pozycji. Kwoty są
wprowadzane i formatowane jako PLN, natomiast API otrzymuje grosze. Dezaktywacja
nie usuwa historii; usunięcie jest jawną, osobną akcją z potwierdzeniem.

### Prognoza i sugestie

Prognoza pokazuje następny termin wypłaty, saldo przed nim, najniższe saldo,
bezpieczny limit dzienny i listę dziennych wartości w granicach ustawionego
horyzontu. Nie obejmuje kont pozabudżetowych.

Każda sugestia zachowuje istniejące statusy `due`, `overdue`,
`overdue_uncertain`, `matched_actual` i `amount_unknown`. Akcja potwierdzenia
jest dostępna tylko dla `due` albo `overdue` z wyliczoną kwotą. Przed zapisem
użytkownik widzi konto, kategorię, kwotę, datę i opis tworzonej transakcji.
Nie ma automatycznego księgowania.

## API i zasady zapisu

Istniejące odczyty oraz `PATCH /cashflow/settings`, `POST /cashflow/items` i
`PATCH /cashflow/items/{item_id}` pozostają bez zmiany znaczenia. Dodane zostaną:

- `DELETE /cashflow/items/{item_id}` do jawnego usunięcia pozycji użytkownika;
- `POST /cashflow/items/{item_id}/confirm` do zatwierdzenia bieżącej sugestii.

Endpoint potwierdzenia ponownie wylicza sugestię po stronie serwera. Odrzuca
nieistniejącą, cudzą, nieaktywną, niekwalifikującą się lub nieznaną kwotowo
pozycję. Zatwierdzona transakcja jest tworzona wyłącznie przez serwis domeny
finance z dwoma zbilansowanymi postingami. Nie przyjmuje od klienta kwoty,
konta ani kategorii, więc nie może rozminąć się z zaakceptowaną sugestią.
Ponowne wywołanie po księgowaniu nie tworzy dubla: ponownie wyliczona sugestia
ma status `matched_actual` i jest odrzucana.

Podsumowanie kategorii przyjmie opcjonalne parametry miesiąca i roku, używane
przez widoki Budżet i Raporty. Wyniki nie są wyliczane przez LLM.

## Struktura frontendu

`Finances.tsx` zostanie ograniczony do strony przeglądu. Widoki będą wydzielone
do stron w `frontend/src/pages/`, a współdzielone karty, formularze i wiersze
do komponentów finansowych. Warstwa `frontend/src/api/finance.ts` dostanie
typy i hooki ustawień, mutacji schedulera, potwierdzenia sugestii oraz
parametryzowanych raportów.

Po udanej mutacji TanStack Query unieważnia dane zależne: harmonogram,
prognozę, konta, transakcje oraz właściwe podsumowania. Interfejs nie stosuje
optymistycznego zapisu dla operacji księgowych. Błędy HTTP 422 są przedstawiane
przy formularzu, a błąd ładowania nie ukrywa dostępnych części strony.

## Testy

Backend obejmie co najmniej:

- usuwanie wyłącznie własnej pozycji schedulera;
- walidację konta budżetowego, kategorii i waluty;
- potwierdzenie tylko kwalifikującej się sugestii;
- brak podwójnego księgowania przy ponowieniu potwierdzenia;
- invariant sumy postingów równy zero dla utworzonej transakcji;
- filtrowanie zestawienia kategorii według miesiąca i roku.

Frontend obejmie trasy i stan aktywny sidebara, formularze ustawień i
schedulera, invalidację danych po mutacjach, brak akcji potwierdzenia dla
niekwalifikujących się sugestii oraz prezentację błędów walidacji.

## Poza zakresem

- Limity budżetowe, koperty i automatyczne rekomendacje wydatków.
- Automatyczne księgowanie lub autonomiczne tworzenie transakcji.
- Cykle inne niż miesięczne i terminy po 28. dniu miesiąca.
- Integracje bankowe i import nowych danych z Actual Budget.
