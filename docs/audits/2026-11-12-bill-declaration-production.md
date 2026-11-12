# Wdrożenie deklaracyjnego opłacenia faktury

## Zgoda i zakres

Użytkownik: „scal, wypchnij do main i wdróż”. Zatwierdzona rewizja aplikacji
`69ee8b7`, backend/worker/frontend. Bez migracji, importu, korekt historii lub
oznaczania rzeczywistej faktury jako opłaconej w ramach testu.

## Przygotowanie i integracja

- main1b43f0d→69ee8b7 fast-forward i push; remoteexactSHA potwierdzone.
- Pełny backend2351PASS/23proxyexcluded/0fail/error/skip i422hash zweryfikowane;
  świeży frontend631PASS, Ruff/mypy192/ESLint/tsc/buildPASS. Nie powtarzano pełnego
  backendu bez zmiany źródeł. Testy lokalnego przepływu desktop/mobile28PASS.
- Jawne testy pakowania rzeczywistych obrazów:6proxyPASS/11pozostałych przypadków
  pliku deselected; brak twierdzenia, że powtórzono wszystkie23proxy całego projektu.
- Przygotowano3niemutowalne obrazy offline z istniejącego, zgodnego runtime5dc.
  Nonroot10001:10001 import/readgatePASS dla dokładnych imageIDs.
- Guard renderowania wykrył dziedziczenie starych mountów przez Composeextends;
  przed jakąkolwiek zmianą produkcji dopisano jawne !override uploads/configs/logs.
  Pełny standaloneoverride zgodny z zatwierdzoną listą Compose; poza image/build
  konfiguracja identyczna z produkcją. Bez osłabienia hardeningu lub zmiany danych.
- Jeden safetyreview operatora:1Important — błędny klucz kształtu dowodu offline.
  TestREDKeyError→GREEN po odczycie services.<service>.image_id; rzeczywisty
  preflightPASS. Nie wykonano drugiego review ani nie zmieniano kodu aplikacji.

## Status wykonania

Public503/drain/stopPASS, świeży backup bez retencji i restorechecksumPASS. Własny
no-port klon: exacthash wszystkich tabel/uploadów, ledger0 i newORMread-onlyPASS.
Podmieniono3aplikacje bez migracji. ExactimageIDs/env/users/mounty/sieci zgodne
z zatwierdzonym Compose; retencja76publictables i uploadów przedotwarciem ingressPASS.
PostgreSQL,Redis,Stirling bez zmian identyfikatorów lub mountów.

HTTPS200, protectedAPI401,15plików dist byte-match (łącznie z mapą źródeł),
GET-onlybrowser375/1440PASS. Screeny obejrzane: brak overflow i błędów JS,
bez obcych domen i mutacji.29kontroli przez minimum300sekund:health200,
0ERROR/restartów,ledger0,workerARQready. Active69ee8b7/schema84 **verified-live**;
metadane zapisano atomowo dopiero po tych dowodach.

Backup `247606953fcee001daedb10005936d3a1d1b7e783e3f4d45bc27035d092cc936`
zachowany w szyfrowanym repozytorium, bez retencji. Własny klon i plaintextcopy
usunięto po kontroli exactID/label/idle/noports/exit0/absence, bezforce/prune.
Prywatny pakiet dowodów: `/opt/finanse/webapp/releases/bill-declaration-69ee8b7/evidence`.
Nie oznaczono realnej faktury jako opłaconej i nie zmieniano danych finansowych.

Rollback: poprzedni5dc activeoverride i zachowane obrazy, schema84 bez zmian.
Bez produkcyjnegoDOWN/DBrestore lub cofania deklaracji użytkownika. Prywatne dane,
oryginały, konfiguracja środowiska i receipty pozostają pozaGit.
