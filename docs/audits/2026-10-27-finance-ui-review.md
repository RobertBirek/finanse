# Przegląd użyteczności finansów — 2026-10-27

## Zakres i ograniczenia

Zgoda użytkownika: przegląd nowej wersji i krótka lista poprawek, bez zmieniania
danych. Nie wykonano napraw, deployu, mutujących żądań API ani dostępu do bazy.

Przegląd dotyczy runtime1b42e34, dokumentacja mainc917ac3. Publiczne hashe JS/CSS
odpowiadają dokładnie plikom wydania `/opt/finanse/webapp/releases/1b42e34/frontend-dist`.
Nowa, anonimowa przeglądarka na produkcji przekierowuje `/finances` do `/login`.
Nie udostępniono zalogowanej sesji; nie pobierano ani nie tworzono cudzych tokenów.
**Test zalogowanego konta na produkcji pozostaje niewykonany.**

Testy zalogowanych widoków wykonano na tych samych zasobach wydania, lokalnie
pod przechwyconym `ui.test.invalid`, z fikcyjnymi odpowiedziami API. Żadne żądanie
tych scenariuszy nie dociera do produkcji. Potwierdzono brak mutujących żądań
także podczas otwierania formularza transferu i próby kopiowania.

## Wyniki

- 10 widoków × 375/1440px × jasny/ciemny motyw = **40 kombinacji**:
  przegląd, transakcje, budżet, nadchodzące, raporty oraz pięć stron ustawień.
- W tym zestawie brak poziomego overflow i nieoczekiwanych błędów JS.
- Axe WCAG A/AA: 36 kombinacji bez naruszeń badanych reguł; w czterech wariantach
  ustawień kont naruszenie kontrastu archiwalnego konta. To nie pełny audyt dostępności.
- Dodatkowo odtworzono powrót z raportu do historii, zmianę zakładek, formularz
  transferu oraz odmowę dostępu do schowka. W ostatnim scenariuszu celowo
  wywołano i zaobserwowano nieobsłużone odrzucenie Promise.
- Próby salda1 234 567,89PLN na375px oraz budżetu15 000PLN na320/375/768/1440px
  nie wykazały poziomego overflow głównej treści. Nie zgłaszamy hipotetycznego błędu.

## Lista potwierdzonych poprawek

### 1. Zachować miesiąc przy powrocie i zmianie zakładki — priorytet P2

**Odtworzenie:** Raporty → poprzedni miesiąc (wrzesień2026) → Dom → historia
z prawidłowym zakresem01–30.09 → Wstecz. Raport pokazuje znów październik.
Analogicznie wrześniowy Przegląd → Raporty otwiera październik.
Potwierdzone dwukrotnie. Kwoty nie są uszkodzone, ale użytkownik traci kontekst
i może kontynuować analizę innego okresu niż zamierzał.

**Przyczyna:** `FinanceReports.tsx:18`, `FinanceBudgets.tsx:35`, `Finances.tsx:20`
przechowują okres wyłącznie w lokalnym `useState`, inicjalizowanym bieżącym miesiącem.
`CategorySpendTree.tsx:106` używa zwykłego linku, a URL raportu nie zawiera okresu.

**Proponowany zakres:** okres w URL, zachowanie go w nawigacji finansów i przy Wstecz;
testy odświeżenia, powrotu i przejścia między zakładkami. Nie zmieniać zakresu danych
po cichu ani przeliczeń backendu.

### 2. Przywrócić kontrast kont archiwalnych — priorytet P2

**Odtworzenie:** Ustawienia → Konta z aktywnym i nieaktywnym rachunkiem.
Axe wykrywa niewystarczający kontrast etykiet/typu/waluty i przycisku usuwania
w obu motywach, na desktopie i telefonie. Przykładowo etykiety2,28:1 w jasnym
i3,37:1 w ciemnym zamiast4,5:1. Aktywne kontrolki wizualnie przypominają wyłączone.

**Przyczyna:** `AccountSettingsRow.tsx:108–112` stosuje `opacity-60` do całego
wiersza, także jego tekstu i aktywnych przycisków.

**Proponowany zakres:** oznaczać archiwizację tekstem/badge i ewentualnie tłem,
bez przygaszania całego wiersza. Regresja axe dla nieaktywnych kont, oba motywy.

### 3. Obsłużyć rezultat kopiowania IBAN-u — priorytet P2

**Odtworzenie:** kontrolowana odmowa Clipboard API → Kopiuj. Promise odrzucony
`NotAllowedError`, nieobsłużony błąd JS; tekst interfejsu pozostaje identyczny,
więc użytkownik nie wie, że numer nie trafił do schowka. Brak zapisu danych.

**Przyczyna:** `AccountSettingsRow.tsx:146–154` wywołuje
`void navigator.clipboard?.writeText(...)` bez obsługi błędu i potwierdzenia sukcesu.
Przy niedostępnym API optional chaining milcząco nic nie robi.

**Proponowany zakres:** krótki komunikat sukcesu/błędu, obsługa braku Clipboard API,
możliwość ręcznego zaznaczenia numeru i dostępny status dla czytnika ekranu.
Testy sukcesu/odmowy/niedostępności bez utrwalania IBAN-u w logach.

## Dalsze obserwacje, nie blokady

- Na375px zakładka Raporty i dalsze zakładki ustawień są poza widocznym fragmentem
  poziomej nawigacji. Przewijanie działa; warto czytelniej zaznaczyć, że są dalsze pozycje.
- Raporty nazywają sumy ogólnie „Przychody/Wydatki”, chociaż backend ogranicza je
  do kont budżetowych (`reporting.py:70,105,159`). Przegląd ten zakres opisuje;
  analogiczny dopisek w Raportach zmniejszy ryzyko nieporozumienia.
- Wczesny odczyt DOM wskazał0 dialogów po kliknięciu Transfer. Po właściwym
  oczekiwaniu na widoczny dialog wynik1 i brak błędów: był to wyścig w skrypcie
  przeglądu, nie usterka aplikacji. Nie trafia na listę napraw.

## Dowody i następny krok

Prywatne artefakty (wyłącznie fikcyjne dane) w
`/tmp/opencode/finance-ui-review-20261027/`: `report.json`, `navigation.json`,
`clipboard.json`, `budget.json`, `asset-proof.json`, skrypty i screenshoty.

Rekomendacja: jedna mała iteracja trzech potwierdzonych poprawek po akceptacji.
Nie rozpoczynać importu ani porządkowania istniejących kategorii w ramach tej iteracji.
Osobno ustalić bezpieczny dostęp/sposób oceny zalogowanej produkcji; nie prosić
o hasło lub cookie w rozmowie. Raport nie potwierdza rzeczywistych sald użytkownika.
