# Actual — zatwierdzony import produkcyjny

## Zgoda i bramki

Użytkownik jednoznacznie zatwierdził zapis286 nowych operacji na produkcji po świeżym
backup/restore,bez usuwania/nadpisywania historii,z zachowaniem jednej przypiętej
operacji nieobecnej w źródle. Zgoda nie obejmowała importu CSV/PDF bankowych.

- Świeży backup **bd201f28** i izolowany restore drill:success/0.
- Bezpośrednio przed wykonaniem:źródłowy ZIP/manifest/runtime zgodne z zatwierdzonymi
  hashami,0 nowszych komunikatów Actual względem eksportu. Pin nie był odświeżany.
- W świeżej transakcji READ ONLY sprawdzono pełną identyczność produkcji z baseline:
  1601 transakcji/postingów,33 konta,102 kategorie,869 mapowań. Head c7f8c620460d bez zmian.
- Wywołano wdrożony scripts.migrate_actual d3c2c68,require_reconciled i przypięty
  manifest. Wszystkie mutacje przez istniejące serwisy domenowe. Bez replacement,
  migracji bazy lub równoważących zapisów.

## Wynik zapisu

| Kontrola | Wynik |
|---|---|
| Nowe operacje | **286** |
| Istniejące wspólne operacje pominięte | **799** |
| Błędy importu | **0** |
| Zachowane wcześniejsze transakcje/postingi | **1601 pełnych fingerprintów bez zmian** |
| Transakcje w całej produkcyjnej bazie po imporcie | **1887** |
| Mapowania idempotencji operacji z eksportu | **1085/1085** |
| Salda kont — jawne uzgodnienie z zachowaną historią | **16/16 zgodnych** |
| Kategorie / grupy | **54/54 i9/9 zgodnych** |
| Zamknięte konta | **2 nieaktywne,żadnego ponownego otwarcia** |

Surowy raport względem samego Actual **pozostaje niezgodny** dla jednej uzgodnionej
do zachowania operacji. Raport augmented jawnie dodaje tylko postingi tego przypiętego
zapisu do oczekiwanych sald. Brak tolerancji innych różnic i brak korekty księgowej.
Zachowana operacja i pozostała historia nie zostały zmienione.

## Kontrola przed commitem i po nim

Oprócz istniejącego ensure_reconciled prywatny operator dodał wyłącznie kontrolę
zakresu przed fizycznym commitem:pełne1601 wcześniejszych fingerprintów,dokładne286
zatwierdzonych Actual ID,właściwy owner i mapowania,liczby encji zgodne z próbą,
niezmienione stare metadane poza zatwierdzonym statusem source-closed.

Krótka blokada współdzielona wcześniejszych transakcji/postingów utrzymywała ten
warunek do commitu. Każda operacja nadal ma min.2 postingi i sumę basePLN=0.
To dodatkowa bramka odrzucająca nieoczekiwane zmiany,nie inna ścieżka zapisu.
Sprawdzono ją na wyniku udanej próby i8 negatywnych mutacjach; wszystkie odrzucone.

Importer wykonał dokładnie jeden commit; marker operatora zabrania automatycznego
ponowienia przy błędzie lub niejasnym wyniku. Po commicie świeża sesja READ ONLY
sprawdziła zakres i wszystkie1085 mapowań idempotencji — bez drugiego importu.
Zmieniono wyłącznie zatwierdzony zakres danych; aplikacja/kod/schema pozostają bez zmian.

Niezależny odczyt z odrębnego procesu sprawdzający salda i cały snapshot po commicie:
**PASS**. Transakcja REPEATABLE READ+READ ONLY potwierdziła identyczność pełnego
snapshotu po commicie,wszystkich1601 wcześniejszych fingerprintów oraz1887 invariantów.
Ponownie odczytane salda16/54/9 odpowiadają zatwierdzonemu raportowi augmented,
1085 idempotency checks i pin poprawne,HTTPS health200. Nie wykonywano drugiego importu.

## Ochrona zakończonego stanu

Po weryfikacji wykonano dodatkowy backup **c69299d0** i izolowany restore drill:
success/0. Zachowano także przedimportowy backupbd201f28. Aplikacja i Actual działają
bez restartów,kod/schema niezmienione. Przed commitem samej dokumentacji:96 testów
manifestu/integracji oraz194 frontend,Ruff/mypy/ESLint/tsc PASS na niezmienionym kodzie.

## Dowody i ograniczenia

Pełny raport raw_actual/augmented,manifest,log,precommit/postcommit proof i snapshot
pozostają w prywatnym `/tmp/opencode/actual-production-import-20261024`.
Trwały prywatny pakiet dowodów/zaakceptowanych wejść skopiowano poza Git do
`/opt/finanse/webapp/imports/actual-20261024-154006` z manifestem hashów. To archiwum
audytowe,nie finansowe źródło prawdy; tym pozostaje PostgreSQL.
Inputy trafiały poprzez stdin wyłącznie do prywatnego tmpfs kontenera i były usuwane
po zakończeniu; nie zapisywano ich w uploads ani w repozytorium.

Nie restartowano aplikacji i nie zmieniano źródła Actual. Wyciągi bankowe oraz
harmonogram kredytu nie zostały zaimportowane. Następny zakres to osobno zatwierdzony
podgląd importu bankowego,z kontrolą duplikatów i sald,zanim nastąpi zapis.
