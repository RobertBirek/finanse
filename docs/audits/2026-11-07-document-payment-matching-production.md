# Dokumenty ↔ płatności 5A — wdrożenie produkcyjne

Data:2026-11-07. Status: **wdrożone i zweryfikowane**.
Zgoda użytkownika: „scal, push do main i wdróż” po odebraniu lokalnego HEADa68d9e4.

## Rewizja i zakres

- `main` z8121512 do `a68d9e4c5ead523f071d5d64f78a6cb0a532495e` fast-forward;
  push79cfa78→a68d9e4 potwierdzony przez `ls-remote`, bez force i konfliktów.
- Backend/worker/frontend mają teraz obraz `local/finanse-<service>:a68d9e4…`, zgodną
  etykietę OCI revision i spójne źródła. Stan env, sieci, zasobów, polityk AI i mountów
  poza obrazami/build bez zmian. Nie ma host-mountu `/app`.
- Pakiet `/opt/finanse/webapp/releases/a68d9e4/` przez `ops/prepare_release.py`,
  pełne base+prod+compose.active i dotychczasowy envfile; `--no-deps --no-build` tylko
  backend/worker/frontend. Images zbudowano `--network=none`, wymagania runtime
  identyczne z95f8380. Dane PostgreSQL/Redis/Stirling i ich kontenery niezmienione.
- Schemat pozostaje `f3a9d17c2e4b`. **Bez migracji**, downgrade, importu, batchu,
  reorganizacji kategorii, nowych zgód AI, wywołań modeli lub danych próbnych użytkownika.

## Gate i backup

- FF integruje dokładnie odebrany tree, nie nową kombinację kodu. Odebrane lokalnie
  1788backend/540frontend/153E2E+1expectedskip, niezależny review bez uwag.
  Świeże lint/types/build po merge PASS; źródła i assety zgodne z manifestami gate.
- Świeży zaszyfrowany backup przez `finanse-backup.service`, kontrolne odtworzenie
  wyłącznie do nowej własnej `payment_matching5a_20261107_restore` na loopback.
  SHA dump/uploads, schematf3a9 i zero naruszeń ledgeru PASS. Bez uruchamiania Alembic.
  Po odbiorze usunięto wyłącznie tę własną bazę kontrolną; backup/rollback zachowane.
- Przed przełączeniem sprawdzono brak aktywnych zadań dokumentów/receipt/sugestii,
  queue0 i aktywne0. Krótki transientcronqueue1 zatrzymał preflight **przed** zmianą;
  bramka czeka warunkowo do90s na faktyczne0, nic nie usuwa z Redis.

## Pierwsza próba i bezpieczny rollback

Pierwszą próbę wykonano pod osłoną HTTP503. Wewnętrzna bramka startup wykryła
`ModuleNotFoundError: app.main/app.worker`; nowego API nie otwarto publicznie.
Natychmiast przywrócono pełny poprzedni override i obrazy, potwierdzono health/login200.

Zidentyfikowana przyczyna: ekstrakcja archiwum Git przy umask077 utworzyła katalogi
`source/backend/app`0700. Docker COPY przeniósł je do obrazu; istniejący runtime
UID10001 nie mógł ich przechodzić. Stary pakiet miał0755. To błąd uprawnień pakietu,
nie zależności, modeli danych lub działania matcherów.

- Offline RED: `docker run --network none --user10001` importapp.main odtwarza błąd.
- Poprawiono **tylko skopiowany kod pakietu** source/backend: katalogi0755,
  pliki0644/istniejące executables0755, bez zmiany zawartości. Prywatny root pakietu
  pozostaje0700. Bez chmod/chown oryginalnych uploads, sekretów lub repozytorium.
- Zachowano failedimages pod tagami `matching5a-failed-permissions`; przebudowano
  backend/worker. Offline GREEN dla obu: UID10001/networknone, wszystkie źródła
  czytelne, importmain+worker i nowe pole evidence PASS.
- Każdy backendplik w pakiecie porównany z dokładnym Git a68d9e4: identyczna zawartość.
  Poprawka pakowania nie zmienia przetestowanego kodu. Automatyzacja tego zabezpieczenia
  w prepare_release wymaga osobnego regresyjnego zadania; nie zmieniono jej ukradkiem.

## Końcowe przełączenie i weryfikacja

Ponowne przełączenie backend/worker/frontend pod osłoną503; przed otwarciem sprawdzono
wewnętrznyhealth, exactimage/revision, env, brak mountapp i niezmienione IDs danych.
Następnie otwarto normalny nginx:

- HTTPS/login i `/api/health`:200, statusok; anonimowe bills i candidates:401.
- Publiczne JS/CSS zgodne bajt w bajt z zatwierdzonym buildem, bez cache starego pakietu.
- GET-only browser375/1440:login/render/fonty/brak overflow, chronione routes→login,
  pageerrors0, mutacje0 i egress0. Nie wykonywano produkcyjnej alokacji ani OCR/AI.
- Trzy procesy running, restart0, errorlogs0 po udanym przełączeniu.
- Kontrolny production READ ONLY: schematf3a9, naruszeń double-entry0.
- Prywatne metadane active-release.json zmieniono atomowo dopiero po odbiorze.

## Rollback i dowody

Rollback: `/opt/finanse/webapp/releases/ebe441e/compose.active.yaml` z tą samą pełną
listą base/prod/envfile przywraca backend/worker95f8380 i frontendebe441e. Nie usuwać
tych obrazów. Bez downgrade/restore produkcyjnej DB i bez zmian epoch/policy.

Trwałe dowody: `/opt/finanse/webapp/releases/a68d9e4/evidence/` — proof backupu,
baseline/private config, prepare/build, przyczyna/repair, offlineimports, public/browser,
observation/ledger, handoff i manifest. Lokalne logi `/tmp/opencode/payment-matching-5a-release/`.
Materiały zawierające środowisko/backup są root-only, nie należą do repo.
W worktree zachowano wcześniejsze niestage'owane Velo/Q7; hostuntrackedwebapp nietknięte.
