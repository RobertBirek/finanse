# Actual — aktualność przed decyzją o imporcie produkcyjnym

## Zakres zgody

Użytkownik zatwierdził kontrolę aktualności i raport, **bez zapisu do księgi**.
Nie uruchamiano importera, migracji, backup/restore produkcji, napraw danych ani
ponownego importu na kopii. Wykonano wyłącznie odczyty i zapis prywatnych dowodów.

## Źródło Actual

- Tożsamość budżetu, cloud file i grupy synchronizacji odpowiada zatwierdzonemu eksportowi.
- Spójna prywatna kopia sync store wykonana przez SQLite backup z połączenia mode=ro;
  integrity_check=ok. Nie odtwarzano samodzielnie CRDT i nie interpretowano treści komunikatów.
- Ostatni komunikat serwera:2026-10-23 20:29:07.363 UTC, identyczny z watermarkiem
  dostarczonego eksportu. Liczba komunikatów późniejszych:0.
- Hash niezmiennego ZIP odpowiada zatwierdzonemu manifestowi. Hash db.sqlite z ZIP
  odpowiada użytej w próbie prywatnej kopii; integralność SQLite OK.
- Nieaktualny serwerowy .blob nie jest wykorzystywany jako bieżący eksport.
- Wniosek dotyczy stanu zapisanego na serwerze. Zmian klienta Actual, których jeszcze
  nie zsynchronizowano, nie da się potwierdzić tą kontrolą.

## Produkcyjna PA wobec pierwotnego baseline próby

Połączenie aplikacyjne miało transakcję REPEATABLE READ i jawne READ ONLY.
Fingerprinty obejmują wszystkie kolumny transakcji/postingów oraz pełne metadane
kont/kategorii/mapowań, dla wszystkich właścicieli; bez ujawniania treści w repozytorium.

| Sekcja | Wynik |
|---|---|
| Wcześniejsze transakcje i postingi | 1601 pełnych fingerprintów identycznych |
| Konta | 33 identyczne,0 nowych/usuniętych/zmienionych |
| Kategorie | 102 identyczne,0 nowych/usuniętych/zmienionych |
| Mapowania Actual | 869 identycznych,0 nowych/usuniętych/zmienionych |
| Pin zachowanej operacji | właściciel,mapowanie,ID i pełny fingerprint zgodne |
| Schema | c7f8c620460d,bez zmian |
| Runtime | backend/worker d3c2c68,bez restartów; health200 |

## Aktualny zakres przyszłego importu

- Eksport:16 kont (2 zamknięte),54 kategorie,9 grup;0 ostrzeżeń parsera.
- Operacje:986 zwykłych +99 transferów,0 splitów;1085 operacji i1184 żywe źródłowe ID.
- Bieżące mapowania:800 operacji;799 wspólnych z eksportem,286 nowych do dodania,
  1 nieobecna w źródle pozostaje zachowana zgodnie z przypiętym manifestem.
- Nowe encje źródła:1 konto,8 kategorii,1 grupa. Nie dopasowujemy ich po nazwach.
- Wspólne operacje:kwoty/waluty/daty/typy/natywne postingi i opisy zgodne.
  **Nie ma obecnie różnic opisów.** Wcześniejszy wynik21 różnic odtworzono starym
  parserem:brakowało nazw zamkniętych kont w opisach transferów, zastępowanych przez
  `?`. Po poprawce parsera wszystkie21 opisów odpowiadają istniejącej PA. Nie było
  w tym celu aktualizacji danych ani operacji źródła/produkcji.
- Surowa różnica jednej przypiętej operacji pozostaje jawna. Jawne uzgodnienie
  eksport+zachowana historia obejmowało16/16 kont,54/54 kategorii i9/9 grup w próbie;
  oba wejścia próby nadal są niezmienione, więc jej wynik pozostaje adekwatny.

## Weryfikacja raportu

Kod aplikacji/importera nie zmienił się względem wdrożonego d3c2c68. Przed zapisem
dokumentacji ponowiono96 testów manifestu/integracji importera i194 testy frontendu;
Ruff/mypy/ESLint/tsc PASS. Testy używały wyłącznie lokalnej bazy testowej, nie księgi
produkcyjnej. Wcześniejszy pełny gate tej samej wersji:backend778 PASS/8proxy deselected.

## Wniosek i dalsza granica

**Kontrola PASS:286 nowych operacji; nie stwierdzono przeszkody wymagającej nowego
eksportu lub powtarzania niezmienionej próby. Import produkcyjny nie został wykonany.**

Przed wykonaniem wymagana jest osobna zgoda użytkownika na zapis produkcyjny,
świeży backup/restore drill i ponowna krótka kontrola źródła/pinu/stanu PA bezpośrednio
przed uruchomieniem. Każda zmiana zatrzymuje wykonanie; nie przepinać manifestu
automatycznie i nie tolerować innych różnic. Spodziewane zachowanie:tylko uzupełnienie,
bez aktualizacji/usuwania wcześniejszych transakcji, bez korekt i bez importu bankowego.

Prywatne dowody i pełne diffy:
`/tmp/opencode/actual-current-preflight-20261024`. Zawierają hashe,metadane i dane
finansowe; nie commitować ich,nie przekazywać do zewnętrznych narzędzi/LLM.
