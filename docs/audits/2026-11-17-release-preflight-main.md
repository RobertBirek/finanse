# Publikacja preflightu na main — 2026-11-17

## Zakres

- Zgoda użytkownika: „push do main i wdróż”.
- Przed publikacją czysty detached linked worktree, HEAD `2492ad2`.
- Remote main `b5c212a`; cztery lokalne commity, potwierdzone fast-forward.
- Push bez force `b5c212a..2492ad2`; zdalne refs/heads/main potwierdziło pełny
  `2492ad27701d21dafc2531bba7e1615f87f5e38e`.
- Zakres operatora: [.opencode/command/deploy.md](../../.opencode/command/deploy.md)
  i runbook. Odczyt produkcji był częścią zatwierdzonego sprawdzenia wdrożenia,
  nie zgodą na wydawanie inventory z własnych obserwacji.

## Decyzja wdrożeniowa

`NO_BLOCKER_FOUND` dla publikacji narzędzia i pozostawienia obecnej aplikacji.

Diff od rzeczywistej rewizji wszystkich3usług `45bcf88` obejmuje ops, dokumentację
i testy. Osobny dokładny diff backend/frontend/root Dockerignore, z wyłączeniem
rozpoznanych testów, jest pusty. Brak nowych bajtów aplikacji, build inputs,
zależności lub migracji. **Nie było nowego rollout aplikacji.**

Nie budowano identycznych obrazów ani nie wykonywano up/create/restart/stop.
Nie uruchamiano maintenance, backup/restore, migracji, importu, nowej kolejki,
rollbacku lub publikacji active-release.json. Nie zmieniono /opt/finanse checkoutu,
oryginalnych dokumentów, zachowanych klonów lub danych.

Jest to jawna kwalifikacja operatorska zakresu ops, **nie raport `no_rollout`
z nowego CLI** i nie obchodzenie jego statusu blocked. Zmiany ops wymagają
ręcznej oceny zgodnie z kontraktem V1; nie dodano dla nich wyjątku.

## Świeże kontrole lokalne przed push

- Kanoniczne `/lint`, `/typecheck`: PASS, mypy215/tsc.
- Backend `/test`: kolekcja offline PASS, bez fixture DB.
- Pełny Vitest707/707PASS65.81s.
- Konkretne134nowych/powiązanych unit w odizolowanym netns: PASS40.37s.
- Dodatkowo Ruff nowychops/testów i mypy2modułów: PASS.
- Bez instalacji/aktualizacji wybranego interpretera lub zależności.
- Wynik lokalny nie zastępuje CI dla dokładnego zdalnego commita.

## Readonly produkcja

- Aktywne metadane verified-live,3service_revisions=`45bcf88`; rzeczywiste image
  IDs/OCI revisions/running state zgodne. Brak hostmount `/app`,0restartów.
- HTTPS `/`200, `/api/health`200, anonimowy GET `/api/finance/accounts`401.
- ARQ `--check`PASS; stały readonly SELECT wersji schematu: `efaf78432563`.
- Postgres/Redis/Stirling healthy. Zachowane kontenery one-off dawnych migracji
  nie są usługami runtime: rozpoznano je po etykiecie oneoff=True i nie usunięto.
- Nie testowano rzeczywistego logowania/cookies lub mutacji BO.

## Granica odbioru nowego CLI

`NEEDS_CONFIRMATION` przed pierwszym rzeczywistym użyciem narzędzia:
brak niezależnie zatwierdzonego inventory/digestu. **Nie uruchamiano nowego CLI
na produkcji, nie wydawano inventory i nie zmieniano metadanych, aby uzyskać PASS.**
Potwierdzono jedynie obecność wymaganych pól w rzeczywistych active metadata;
to nie jest pełny pozytywny odbiór adaptera. Zaakceptowane wdrożenie nie oznacza
automatycznego zatwierdzenia snapshotu wygenerowanego z obserwacji.

## Dowody

Prywatne, zredagowane artefakty:
`/tmp/opencode/release-preflight-main-20261117.uOt5wazx/`.
Zawierają logi kontroli i snapshot bez env/config-secretów. Active release pozostaje
`45bcf8812ded8696624ead6dd65d2a0c5f80710a`, nie etykietujemy go nowym SHA main.
Dokumentacyjny follow-up nie zmienia aplikacji. Zdalne CI sprawdzać dla dokładnej
końcowej rewizji po tym follow-up, nie dla wcześniejszego commita lub lokalnego wyniku.
