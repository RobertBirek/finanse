# Miesięczne budżety z limitami — specyfikacja

## Cel

Umożliwić kontrolę wydatków przez miesięczne limity na kategorie wydatkowe i
porównanie planu z faktycznym wykonaniem w wybranym miesiącu. Budżet jest
rekomendacją i limitem orientacyjnym, nie mechanizmem blokującym księgowanie.

## Model

`CategoryBudget`: `user_id`, `category_id` (FK RESTRICT), `amount_pln`
(BIGINT > 0), unikalne `(user_id, category_id)`. Budżet jest cykliczny
miesięcznie — domyślny limit na każdy miesiąc, bez kolumny miesiąca. Nadpisania
per miesiąc pozostają poza zakresem.

## API

Wszystkie endpointy wymagają autoryzacji i filtrują po `user_id`:

- `GET /finance/budgets` — lista limitów użytkownika.
- `POST /finance/budgets` — utwórz `{category_id, amount_pln}`; walidacja:
  kategoria należy do użytkownika, typ `expense`, kwota dodatnia.
- `PATCH /finance/budgets/{id}` — zmiana kwoty własnego budżetu.
- `DELETE /finance/budgets/{id}` — usunięcie własnego budżetu.
- `GET /finance/budget-status?month=&year=` — per budżetowana kategoria: nazwa,
  `parent_id`, limit, wydane, pozostało. Wydane dla kategorii-grupy to suma
  wydatków jej potomków; kategoria z limitem i zerowymi wydatkami jest nadal
  zwracana z wartością zero.

Wyliczenie wydatków używa wyłącznie postings wydatków na kontach budżetowych
(analogicznie do `category-summary`) w zadanym miesiącu. Wyniki nie są wyliczane
przez LLM.

## Frontend

`/finances/budgets` pokazuje listę budżetowanych kategorii z limitem (edycja
inline), wydaną kwotą, pozostałością i paskiem postępu (czerwony przy
przekroczeniu). Dodawanie budżetu wybiera kategorię `expense` bez istniejącego
budżetu i kwotę w PLN. Osobna sekcja „Wydatki bez budżetu" zachowuje widok
faktycznych wydatków kategorii. Wybór miesiąca pozostaje.

## Poza zakresem

- Nadpisania budżetu per miesiąc i rollover niewykorzystanych środków.
- Budżety przychodów i integracja limitów z prognozą płynności.
- Blokowanie księgowania po przekroczeniu limitu.

## Testy

Backend: własność kategorii i budżetu, tylko typ `expense`, kwota > 0,
unikalność, roll-up grupy, zero-wydatki nadal widoczne, pełny CRUD.

Frontend: hooki, pasek postępu i stan przekroczenia, dodawanie/edycja/usuwanie,
sekcja kategorii bez budżetu.
