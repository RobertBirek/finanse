# Finance UI — implementacja w izolowanej gałęzi

## Zgoda i granice

Użytkownik zatwierdził wygląd makiety `/makieta`, ośmioetapowy plan, podlimity
i implementację w osobnym worktree. Przed produkcją ma otrzymać wersję do oceny.
Nie wykonano deployu, migracji produkcyjnej, importu, merge ani pusha.

Powyższy opis dotyczy etapu implementacji. Następnie użytkownik jawnie wybrał
bezpośredni main i produkcję: wydanie1b42e34 z migracją b8 jest wdrożone.
Osobny raport wykonania: `docs/audits/2026-10-26-release-finance-ui.md`.

- Gałąź: `feat/finance-ui-redesign`.
- Worktree: `/root/.local/share/opencode/worktree/a46231/finance-ui-redesign`.
- Wzorzec: `frontend/public/makieta/` (przeniesiony z wcześniejszej sesji do gałęzi).
- Spec/plan: `docs/superpowers/specs/2026-10-26-finance-ui-design.md` oraz
  `docs/superpowers/plans/2026-10-26-finance-ui.md`.

## Zakres wykonany

- Wspólne jasne/ciemne powierzchnie, pojedynczy sidebar z wszystkimi modułami,
  mobilna dolna nawigacja, bez usuwania profilu i logowania. Preferencja motywu
  w localStorage; brak dostępu do storage nie blokuje aplikacji.
- Konfiguracja kont/kategorii/limitów/harmonogramów/prognozy pod
  `/settings/finances/…`, dostępna też z globalnych ustawień. Stary adres kont
  przekierowuje; codzienny Budżet i Nadchodzące zachowują operacyjne widoki.
- Opcjonalne dane bankowe z maskowaniem/pokazaniem/kopiowaniem, osobna nazwa banku,
  właściciel, IBAN/NRB, BIC i notatka. PATCH zachowuje pominięte pola, null czyści.
  Walidacja IBAN: normalizacja, kraj/długość/checksum, polskie konto numeryczne.
- Migracja `b8e4c2f1a7d9` dodaje tylko nullable kolumny po `c7f8c620460d`.
  Istniejące konta nie wymagają uzupełnienia, waluty i ID nie są zmieniane.
- Prawdziwe salda źródłowe i księgowa równowartość PLN; backendowe agregaty aktywnych
  kont ogółem/budżetowych oddzielone od przychodów/wydatków okresu.
- Edytor drzewa, rozwijanie/zwijanie, podkategorie, edycja/przenoszenie, archiwizacja
  i bezpieczne usuwanie pustych kategorii. Aktywne dzieci nie znikają pod nieaktywnym
  rodzicem. Pickery i filtry pokazują pełne ścieżki.
- Backendowe rekursywne drzewo raportów: wartości bezpośrednie i całej gałęzi,
  zachowane stare pola API, opcjonalne filtrowanie po potomkach.
- Budżet dziecka pozostaje podlimitem: agregat całkowity/cashflow bierze tylko
  najwyższe budżetowe węzły gałęzi, bez podwójnego liczenia wydatków.
- Przegląd z rzeczywistych endpointów: okres, konto/waluta, ostatnie transakcje,
  budżet i wykres z dziennych punktów prognozy. Żadnych stałych kwot demonstracyjnych.
- Formularz transakcji w dialogu, szczegóły w panelu bocznym, dotychczasowe filtry,
  paginacja i przywracanie fokus/URL zachowane.

## Rozstrzygnięcia implementacyjne

1. Niezależne backend/frontend były realizowane równolegle z jawnym kontraktem API.
   Ryzyko rozbieżności ograniczone wspólną specyfikacją i końcowym typecheck/testami.
2. Użyto istniejących zależności przez ignorowane symlinki, bez zmiany lockfile.
   Środowisko kolejnego wykonawcy musi mieć te same zależności z lockfile.
3. Wyszukiwanie kategorii domyślnie nadal exact; potomkowie tylko po jawnym przełączniku.
   Zachowuje to stare URL/klienty, kosztem potrzeby włączenia opcji dla gałęzi.
4. Reguły prognozy/pending/PLN oraz limity backendu pozostały niezmienione poza
   zatwierdzonym sumowaniem nakładających się budżetów. Nie przeniesiono fikcyjnych
   reguł prognozy ani zakresów formularzy z makiety.
5. Dodano serwerowe `balance_all_pln`/`balance_budget_pln`, zamiast sumować kwoty
   w przeglądarce. Są bieżące, nie historyczne dla wybranego miesiąca; UI to opisuje.
6. Dotychczasowy filtr „Wydatki bez budżetu” nie uwzględniał głębokich gałęzi.
   Zastąpiono go prawidłowo nazwaną pełną analizą kategorii, nie wymyślając nowych
   agregatów w UI. Osobny raport wyłącznie niebudżetowy wymagałby osobnego kontraktu.

## Weryfikacja

- Backend: końcowy pełny run **790 PASS**, 8 testów proxy świadomie deselected przez
  istniejącą konfigurację, 2 istniejące warningi bibliotek passlib/argon2.
- Migracja: pojedynczy Alembic head oraz test operacji upgrade/downgrade/upgrade na
  syntetycznym koncie i transakcji testowej, z identycznymi postingami i historią.
  Nie jest to jeszcze próba na kopii danych produkcyjnych.
- Frontend: **220 Vitest PASS**; Ruff/mypy i ESLint/tsc/build PASS.
- RED→GREEN: nowe pola i kontrakty backendu, kraj/długość/format IBAN, salda zakresów,
  hierarchia/agregaty, pojedynczy head migracji, nawigacja, kontrolki przeglądu,
  ustawienia i obsługa odrzuconego storage. Dodatkowe testy komponentów chronią
  potomków/cykle/archiwizację, picker i zerowanie metadanych kont.
- Fresh-context review: brak ustaleń Critical/Important/Minor. W dalszej walidacji
  przeglądarkowej znaleziono i poprawiono kontrast zaznaczonej zakładki oraz kontrolek
  archiwalnych kategorii; regresje pokrywa axe/E2E.
- E2E: **31 PASS + 1 celowy mobile-only skip na desktopie**. Axe bez naruszeń
  wybranych reguł A/AA na przeglądzie/ustawieniach i obu motywach; dodatkowe kontrole
  overflow na 320/768 px. Nie jest to pełna certyfikacja dostępności ani produkcyjny
  test zalogowanego konta. Chromium z istniejącej instalacji, wskazane jawnie.
- Po własnym przeglądzie dodano regresję zachowania zakresu kont przy drilldown:
  sumy raportów są budżetowe, a zwykła historia obejmuje wszystkie konta. Nowy
  opcjonalny `budget_accounts_only` zapewnia zgodność linku z raportem; checkbox
  pozwala jawnie rozszerzyć zakres. Testy nowych kontraktów/migracji **12 PASS**,
  pełny backend po tej poprawce **790 PASS**.

Artefakty poza repo: `/tmp/opencode/finance-ui-*.log`,
`/tmp/opencode/finance-ui-e2e-{results,report}` i screenshoty
`/tmp/opencode/finance-ui-{desktop,mobile}-*.png`. Wyłącznie syntetyczne fixtures.
W testach API prawdziwych usług produkcyjnych nie używano; baza integracyjna to
lokalny `finanse_test`, nie produkcyjna księga.

## Przed wydaniem produkcyjnym

- Pokazać wersję roboczą i uzyskać zgodę na wydanie.
- Próba migracji na izolowanej kopii z kontrolą sald, ID, postingów i mapowań Actual.
- Świeży backup/restore, pakiet wydania ze sprawdzonym rollbackiem i hardeningiem.
- Rollback obrazów nie powinien automatycznie usuwać nowych kolumn metadanych;
  ewentualny downgrade po ich uzupełnieniu wymaga osobnego rozważenia utraty tych pól.
- Backend i nullable migracja muszą być zgodne z nowym frontendem; starsze pola API
  pozostają, nowe agregaty nie są zastępowane fikcyjnymi wartościami przez UI.
- Reguły kategoryzacji, nowe integracje i zmiana kategorii istniejącej transakcji
  pozostają poza zakresem, zgodnie z zatwierdzonym planem.
