# Narzędzia release non-root — integracja i aktywacja na serwerze

Data:2026-11-07. Status: **scalone, wypchnięte, narzędzia aktywne**.
Zgoda użytkownika: „scal i wdróż” po propozycji integracji e8f6714 bez odtwarzania
kontenerów. Zakres jest operacyjny: skrypty, testy, runbook i komenda `/deploy`.

## Wykonane

- Lokalny main i origin/main były a1cc6b8, oba są przodkami e8f6714; fast-forward
  hostcheckoutu `/opt/finanse` do `e8f6714`, bez konfliktów/force i zmian testowanego kodu.
- Zapisano SHA256 narzędzi hosta oraz zgodność z odebranym commitem. Poprawione
  `ops/prepare_release.py`, nowe `ops/verify_release.py` i instrukcje są dostępne
  w operacyjnym checkout main. Nie zmieniano jednostek systemd ani zależności.
- Świeża bramka **na scalonym checkout hosta**:931backendunit PASS/888deselected
  (DB/proxy)/2znanewarnings41.71s,540frontendPASS86plików45.00s; Ruff/mypy149/ESLint/tsc
  PASS. DBintegrations nie wykonywano i nie są oznaczonePASS.
- Oddzielnie6Docker PASS66.98s: syntetyczny backend good/tampered/importfailure/
  missingentrypoint i istniejące nginxreadgood/fail. Wyłącznie własne disposable
  tags/containers, offline; żadnego Composeup lub restartu usług.
- Z rzeczywistego finalnego Compose (base+prod+activeoverride i obecnyenvfile)
  odczytano UID:GID backendu/workera, porównano z konfiguracją działających usług.
  Weryfikator z `/opt/finanse/ops/verify_release.py` uruchomiono z tymi użytkownikami
  na lokalnych gotowych obrazach. OCIrevision i resolvedIDs odpowiadają aktywnemu
  a68d9e4. Import obu entrypointów i odczyt źródełPASS; tylko nowe kontenery kontrolne,
  networknone/read-only/no mounts/wyczyszczoneenv/syntheticsettings, bez startupu/DB/AI.
- Push a1cc6b8→e8f6714 do origin/main potwierdzony `ls-remote`. Kolejny wpis w main
  jest wyłącznie dokumentacją tej integracji, nie nową rewizją aplikacji.

## Produkcja bez odtwarzania kontenerów

Poprawka narzędzi nie wymaga nowego obrazu aplikacji. Backend/worker/frontend nadal
działają na **a68d9e4**, schematf3a9 i ten sam override/rollback. Nowa bramka będzie
obowiązkowa przy następnym budowaniu/przełączaniu aplikacji.

Przed i po aktywacji porównano wszystkie6 usług aplikacji/danych:
containerID, imageID, StartedAt, RestartCount, docelowyuser — identyczne i running.
Prywatne `active-release.json` aplikacji pozostało bez zmian. PubliczneGET:health200,
login200, anonimowebills401. Nie zmieniano polityk, zgód, sekretów, uploads, danych,
schematu lub finansów; nie uruchamiano migracji, batchy ani wywołań modeli.

Nie uruchamiano nowego backup/restore: nie przełączano aplikacji ani nie zapisywano
DB/plików użytkownika. Poprzednie obrazy i backup/rollback aplikacji są zachowane.
Wycofanie narzędzi to osobna kontrolowana zmiana Git poprzednich skryptów/runbooka,
nie reset main, usuwanie zmian roboczych ani przywracanie bazy.

## Dowody i granice

- Lokalne logi: `/tmp/opencode/release-nonroot-integration-20261107/`.
- Trwały raport/proof/manifest narzędzi:
  `/opt/finanse/webapp/releases/operator-tools-e8f6714/evidence/`.
- Odbiór implementacji i niezależny review bez uwag:
  `docs/audits/2026-11-07-release-nonroot-local.md`.
- To aktywacja narzędzi operatora, nie ponowny deploy/certyfikacja funkcji finansowej
  i nie obietnica, że ręczne pominięcie procedury jest technicznie niemożliwe.
  Przyszły rollout wymaga świeżego dowodu dla dokładnych nowychIDs i finalnychusers.
- Niezwiązane Velo/Q7 w featureworktree oraz hostuntrackedwebapp zachowane.
