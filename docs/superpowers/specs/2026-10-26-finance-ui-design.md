# Finance UI — zatwierdzony projekt

Użytkownik zaakceptował makietę `/makieta/`, plan opisany w rozmowie oraz realizację
w osobnym worktree. Nie zatwierdził publikacji nowego UI na produkcję: najpierw podgląd.

## Zakres

- Jeden sidebar na desktopie, dolna nawigacja na mobile, jasny/ciemny motyw.
- Wspólny wygląd całej aplikacji; głęboka przebudowa w tej iteracji dotyczy finansów.
- Finanse: przegląd, transakcje, budżet, nadchodzące, raporty. Konfiguracja tylko
  w `/settings/finances/{accounts,categories,budgets,schedules,forecast}`.
- Stare adresy zachowują działanie/przekierowanie. Profil w ustawieniach pozostaje.
- Konta: opcjonalne bank_name, account_holder, iban, bic, notes. Polski NRB → IBAN,
  walidacja sumy i długości, maskowanie w UI, pokaż/kopiuj. Bez zmiany waluty konta.
- Wielopoziomowe drzewo, ścieżki w pickerach, dodawanie/przenoszenie/archiwizacja.
  Historia i ID kategorii/mapowania Actual zachowane; aktywne dzieci widoczne pod
  nieaktywnym rodzicem. Zmiana rodzica zmienia grupowanie historycznych raportów,
  ale nigdy nie przepisuje postingów. Istniejące blokady cykli pozostają.
- Raport zawiera kwoty bezpośrednie i rollup gałęzi obliczone na backendzie.
  Filtr kategorii może obejmować potomków. Transfer nie jest przychodem/wydatkiem.
- Zatwierdzona zasada: limit dziecka jest podlimitem rodzica; w podsumowaniu całego
  budżetu i prognozy liczymy tylko najwyższy z limitów na danej gałęzi.
- Saldo źródłowe konta plus księgowa równowartość PLN; bez sugerowania bieżącej wyceny.
- Przegląd i wykres prognozy z prawdziwego API; żadnych fikcyjnych kwot w aplikacji.
- Historia: filtry/paginacja/detail w URL, zachowanie przewijania i powrotu, czytelne
  transfery/exchange/splity. Formularze mutują wyłącznie istniejącymi serwisami.
- Reguły automatyczne, nowe integracje i recategoryzacja zaksięgowanej operacji
  wymagają osobnej iteracji. Nie prezentować ich jako działających funkcji.

## Constraints

React 18/Vite/TS/Tailwind/TanStack Query/Zustand; Python 3.12/FastAPI/SQLAlchemy/Pydantic.
PostgreSQL źródłem prawdy; BIGINT grosze/centy; ledger bez zmian kwot i postingów.
Kwoty podsumowań z backendu, bez sumowania stron księgi w UI. Auth/CSRF bez regresji.
Backend serializuje dane bankowe tylko dla właściciela; brak PII w narzędziach Advisora/logach.
Testy RED→GREEN, integracyjne na izolowanym PostgreSQL, lint/types/build i browser.
Minimum 320 px, focus/klawiatura, contrast AA, reduced motion. Brak dostępu do produkcyjnej DB,
deployu/pusha/merge/importu/backup operacji produkcyjnej w tej iteracji.

## Kontrakty integracyjne (ustalenia implementacyjne)

- `AccountResponse`: add nullable `bank_name`, `account_holder`, `iban`, `bic`, `notes`,
  plus integer `balance_source`; existing `balance_pln` unchanged. Create/update accept
  optional metadata; explicit null clears metadata, omitted field preserves it.
- `CategorySummaryResponse`: legacy groups/categories retained; add `tree` nodes:
  `category_id`, `name`, `parent_id`, `is_active`, `direct_total_pln`, `total_pln`, `children`.
- `TransactionSearch`: additive `include_descendants: bool = False` passed through query API.
  Also `budget_accounts_only: bool = False` so report drilldowns retain the report's
  budget-account scope without changing normal history's all-account default.
- `BudgetStatusResponse`: add integer `total_budget_pln`, `total_spent_pln`, `remaining_pln`.
  Individual items preserve own limits and subtree spend; aggregate excludes descendant
  budgets when an ancestor already has a budget. Cashflow summary uses these totals.
- Legacy fixtures may omit additive data; TS fields optional for compatibility, UI fallback
  must not fabricate source amounts or compute report totals from current page.
