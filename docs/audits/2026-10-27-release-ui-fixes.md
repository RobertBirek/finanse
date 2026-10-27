# Wdrożenie poprawek przeglądu UI — 2026-10-27

## Zgoda i rewizje

Użytkownik polecił: „scal, commit, push do main i wdróż”.

- Kod: `550b0f036de536f990be89e415cdd1524bef99bc`.
- Wydanie: `e5ce5f5c5a927e61ab9604205321750098375ac3`, zawiera dodatkowo
  wyłącznie dokumentację wcześniejszego przeglądu i zgody na wdrożenie.
- Main scalony fast-forward i wypchnięty bez force-push. Zastane wpisy przeglądu
  zachowano, także w nazwanym stash `pre-ui-fixes-deploy-review-docs-20261027`.
- Zakres: tylko frontend — okres w URL/nawigacji, kontrast archiwalnych kont,
  obsługa Clipboard API oraz ręczne kopiowanie i ponowne maskowanie IBAN-u.
- Backend i worker pozostają na `1b42e34`. Bez nowego API, zmian zależności/Nginx,
  migracji, importów Actual/Velo, korekt sald i mutujących testów produkcyjnych.

## Gate i przygotowanie

- Na scalonym main: **230 unit PASS**, lint/typecheck/build PASS,
  **43 E2E PASS + 1 celowy desktop skip**.
- CI dokładnej rewizji wydania: **success**, oba zadania:
  https://github.com/RobertBirek/finanse/actions/runs/40496488681.
  Backend 790 PASS + 5 testów proxy/kontenerów, Ruff/mypy PASS;
  frontend 230/43, lint/types/build i audyt zależności PASS.
- Nie ponawiano odrzuconego w poprzednim etapie lokalnego wywołania testów backendu;
  wynik backendu powyżej pochodzi z izolowanego CI uruchomionego przez push.
- Świeży szyfrowany backup **0c35f0fe**. Izolowany systemd restore drill:
  **success/0**, dziennik potwierdza odtworzenie dokładnie tego snapshotu.
- Pakiet `/opt/finanse/webapp/releases/e5ce5f5` przygotowany przez
  `ops/prepare_release.py`. Frontend zbudowano z archiwum Git dokładnej rewizji,
  zapisano provenance i hashe; brak użycia roboczego dist jako źródła wydania.
- Obraz frontendu zbudowany offline na dotychczasowym runtime. Zawartość obrazu
  zgodna hashami z pakietem; pełne E2E powtórzone na dokładnym release-dist:
  **43 PASS + 1 celowy skip**, w tym oba motywy i viewporty dla kont archiwalnych.
- Render pełnego Compose różni się wyłącznie obrazem frontendu. Hardening,
  środowisko, sekrety, sieci, konfiguracja backendu i usług danych bez zmian.
- Niezależne review procedury: poprawiono przypięcie SHA, pochodzenie builda,
  wiązanie E2E z rewizją/obrazem, backupu z restore oraz obowiązkowy gate logów.
  Ponowne review bez blokad.

## Przełączenie i kontrola

- Użyto pełnej listy Compose base+prod+nowy active override, z istniejącym env,
  `up -d --no-deps --no-build --pull never frontend`. Odtworzono tylko frontend.
- HTTPS `/`, `/login`, `/api/health`, `/makieta/`: 200. Anonimowe API finansów,
  dokumentów, pracy i doradcy: 401. Publiczne HTML/JS/CSS/fonty zgodne hashami.
- Produkcyjny test przeglądarkowy 375/1440: login, fonty, brak overflow i błędów JS,
  chronione trasy kierują do logowania. Zero mutujących i obcych żądań.
- Read-only repeatable-read fingerprint wszystkich kolumn tabel finansowych,
  w tym danych bankowych, dokumentów, ustawień, budżetów, harmonogramów i mapowań
  Actual: identyczny przed/po. Hashe oryginalnych uploads identyczne, invarianty 0 błędów.
- Identyfikatory/obrazy/czasy startu backendu, workera, PostgreSQL, Redis, Stirling
  i Actual identyczne przed/po. Brak rzeczywistych zadań dokumentów w kolejce.
- Pięciominutowa obserwacja: **11/11 PASS**, zero restartów i nowych
  ERROR/CRITICAL/Traceback w logach frontendu, backendu i workera.
  Ponowne porównanie wszystkich fingerprintów danych i oryginałów: identyczne.
- Końcowy HTTPS/assets/auth/state gate ponownie PASS. Metadane aktywnego wydania
  zaktualizowano atomowo dopiero po smoke i obserwacji; wskazują frontend e5ce5f5,
  backend/worker 1b42e34 i zachowany rollback. Nie było konieczne wycofanie.

## Rollback i ograniczenia

- Poprzedni frontend i wszystkie obrazy backendu/workera zachowane.
  Rollback: `/opt/finanse/webapp/releases/e5ce5f5/rollback.sh` — odtwarza wyłącznie
  frontend z pełnym Compose i poprzednim active override 1b42e34.
- Rollback nie wykonuje restore bazy ani downgrade; schemat pozostaje b8.
- Brak zalogowanej sesji produkcyjnej: funkcjonalność po zalogowaniu sprawdzona
  na exact-dist z fikcyjnym API, nie na rzeczywistych operacjach użytkownika.
- Prywatne dowody/provenance/render/hashe/logi i rollback:
  `/tmp/opencode/release-ui-fixes-550b0f0/` oraz katalog pakietu.
  Nie dodawano `webapp/`, sekretów ani danych użytkownika do repozytorium.
- Log CI i dowód liczników testów zachowane prywatnie jako `ci.log`
  i `ci-count-proof.json` wraz z hashem logu.
