# Waluta konta — pierwszy slice roadmapy (2026-10-27)

## Zgoda i zakres

Po zatwierdzeniu kolejności waluty → Q7 → pozostałe zobowiązania/Goodie/darowizny
użytkownik polecił „ok, działaj”. Zrealizowano pierwszy, niezależny slice walut.
Gałąź `feat/account-currency` od main11a625d, istniejący izolowany worktree.
Bez merge/push/deployu, migracji schematu lub operacji na produkcyjnej księdze.

## Zachowanie

- Edycja konta pokazuje PLN/EUR/USD i wyjaśnienie blokady.
- Puste ręczne konto może zmienić walutę. Dowolny posting (także pending i saldo0),
  dowolny harmonogram (także nieaktywny), źródło importowe lub mapowanie Actual
  blokują zmianę. UI korzysta z wyliczanego serwerowo `can_change_currency`;
  brak pola w starszym API nie odblokowuje kontrolki.
- PATCH normalizuje lowercase, odrzuca null/nieobsługiwane wartości422;
  konflikt409 jest atomowy, właściciel inny niż żądający otrzymuje404.
  Ta sama waluta jest idempotentna, pozostałe metadane pozostają edytowalne.
- Serwer ponawia sprawdzenie niezależnie od UI. FOR SHARE przy walidacji postingów
  i harmonogramów współpracuje z FOR UPDATE zmiany waluty; odczyty po czekaniu
  odświeżają ORM, kolejność blokad account.id jest deterministyczna.
- Salda nadal pochodzą z istniejących postingów; niczego nie przewalutowano
  ani nie przepisano. Capability jest właściwością odczytową, nie kolumną bazy.

## Dowody

- Baseline: backend accounts/queries21 PASS i frontend accounts26 PASS.
- TDD: backend15 RED przed rozszerzeniem API, concurrency/stale ORM6 RED przed
  blokadami, frontend4 RED przed selectem/komunikatami. Potem odpowiednie GREEN.
- Pełny backend: **812 PASS**,8 proxy deselected,2 dotychczasowe warningi bibliotek.
  Ruff/mypy65 PASS. Pierwszy run przekroczył240s; powtórzony bez limitu zakończył
  się po493,83s. Po uzupełnieniu typowanego settera dodatkowo targeted25 PASS.
- Frontend **235 PASS**, ESLint/tsc/build PASS, **47 E2E PASS +1 celowy desktop skip**.
  Axe obejmuje edycję kont na desktopie i mobile. Wszystkie mutacje E2E idą
  wyłącznie do fikcyjnych handlerów, nie do produkcyjnego API.
- Pierwszy E2E używał selektora formularza tworzenia zamiast edycji — poprawiono
  selektor. Pierwszy dodatkowy mypy z root nie rozwiązał importów; prawidłowy gate
  z backend PASS. Nie zmieniano produktu lub konfiguracji, by ukryć te błędy narzędzi.
- Niezależny review całej zmiany bez blokad. Poprawiono setup przypadku nieaktywnego
  harmonogramu: dezaktywacja przez serwis, nie ignorowany atrybut create schema.

Dowody prywatnie: `/tmp/opencode/account-currency-gate/backend.log`,
`/tmp/opencode/account-currency-e2e-green-report` i artefakty sesji narzędziowej.

## Następna iteracja

Q7 wymaga semantyki zobowiązania, podziału kapitał/odsetki/opłaty i trwałego
powiązania planowanej raty z istniejącą rzeczywistą płatnością. Obecna walidacja
expense ma dokładnie jeden posting konta — kategoria nazwana „kapitał” nie
zastąpi księgi długu. Nie wprowadzono takiego obejścia ani nowych operacji Q7.
Karta Velo/Allegro Pay, pożyczki rodzinne, Goodie i darowizny pozostają backlogiem.
