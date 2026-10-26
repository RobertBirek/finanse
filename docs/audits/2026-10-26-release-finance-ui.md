# Wdrożenie nowego UI finansów — 2026-10-26

## Zgoda, rewizja i zakres

Po zakończeniu implementacji użytkownik wprost polecił: „wdróż od razu do main,
i tak będziemy poprawiać”. Zatwierdzony zakres: scalenie/push oraz wdrożenie
backendu, workera i frontendu z addytywną migracją danych bankowych kont.

- Wydanie: `1b42e345f42bec2667c888a578b8f9b60a6fc136`.
- Main scalono fast-forward i wypchnięto bez force-push.
- Produkcja: `https://finanse.birek.online`.
- Migracja: `c7f8c620460d` → `b8e4c2f1a7d9`; wyłącznie pięć nullable kolumn kont.
- Bez importu Actual/bankowego, zmian kategorii dawnych operacji, korekt sald,
  resetu retry dokumentów lub nadpisywania oryginałów.

## Gate, backup i próba migracji

- Na scalonym main: backend **790 PASS**, 8 testów proxy deselected w standardowym
  uruchomieniu i 2 znane warningi bibliotek; Ruff/mypy PASS.
- Frontend **220 PASS**, ESLint/tsc/build PASS, E2E **31 PASS + 1 celowy desktop skip**.
- CI dla dokładnej rewizji: **success**, oba wymagane zadania; obejmuje też
  osobny krok testów proxy i kontenerów:
  `https://github.com/RobertBirek/finanse/actions/runs/40412251107`.
- Świeży szyfrowany backup **c5520a46** i systemd restore drill: **success/0**.
  Odtworzona izolowana baza przeszła migrację do b8 i kontrolę invariantów.
- Dodatkowo nowy obraz migracyjny sprawdzono na świeżej kopii produkcyjnego dumpa
  w osobnym kontenerze PostgreSQL bez sieci zewnętrznej i z danymi w tmpfs.
  Wszystkie stare kolumny kont, kategorii, transakcji, postingów, mapowań Actual,
  dokumentów, budżetów, harmonogramów i ustawień miały identyczne hashe przed/po.
  Nowe metadane NULL, zero naruszeń księgi. Kontener próbny usunięty po weryfikacji.

## Pakiet i przełączenie

- Wersjonowany pakiet `/opt/finanse/webapp/releases/1b42e34` przygotowano przez
  `ops/prepare_release.py`, na zweryfikowanych bieżących runtime'ach d3c2c68;
  zależności backendu bez zmian. Build obrazów offline, przypięte immutable image IDs.
- Zachowano znane obejście restrictive umask wyłącznie dla wygenerowanej kopii
  kodu i dist (katalogi0755/pliki0644), nigdy dla uploads, sekretów lub oryginałów.
  Każdy nowy obraz backend/worker przeszedł próbę Uvicorn/health jako produkcyjny
  UID10001 z dokładnym env, read-only i network-none; wszystkie hashe źródeł zgodne.
- Render Compose zmienia tylko image/build trzech usług aplikacji. Zachowane:
  środowisko, sekrety, sieci, UID, read-only, cap-drop ALL, no-new-privileges,
  limity zasobów i brak host mountu `/app`.
- Przed przełączeniem wykonano migrację produkcyjną do b8 i ponownie potwierdzono
  niezmienność całej starej treści finansowej oraz NULL nowych pól.
- Następnie zastosowano pełny Compose base+prod+previous-active+release przez
  `up -d --no-deps --no-build --pull never backend worker frontend`.
  PostgreSQL/Redis/Stirling/Actual nie były odtwarzane ani restartowane.
- Nie jest to wdrożenie bezprzerwowe. Zmiany schematu wykonano przed uruchomieniem
  nowego ORM, a stary runtime toleruje dodane nullable kolumny.

## Kontrole po przełączeniu

- HTTPS `/`, `/login` i API health200; anonimowe finance/documents/work/advisor401.
- Publiczne zasoby zgodne hashami z pakietem, również zachowany `/makieta/`;
  sourcemap nie pobierano z produkcji jako części smoke.
- Trzy aplikacje wskazują właściwe obrazy/revision i mają zero restartów.
  Backend/worker pozostają non-root i read-only, bez hostowego montowania kodu.
- Dokładne fingerprinty starej treści księgi, kategorii, mapowań i dokumentów,
  budżetów/harmonogramów/ustawień oraz hashe oryginalnych uploads identyczne.
  Revision zmieniło się jedynie c7→b8; nowe pola początkowo NULL.
- Kontenery i czasy startu PostgreSQL/Redis/Stirling/Actual identyczne z baseline.
  Brak rzeczywistych oczekujących zadań dokumentów; metryka cron dispatchera
  nie jest traktowana jako transakcja finansowa ani job dokumentu.
- Przeglądarka produkcyjna375/1440: login/fonty/zasoby/ochrona tras PASS, bez
  overflow, błędów JS, obcych originów i mutujących żądań. Bez login POST.
- Active-release metadata zaktualizowano atomowo dopiero po udanym smoke;
  skonsolidowany `compose.active.yaml` renderuje dokładnie wdrożony runtime.
- Pięciominutowa obserwacja po wdrożeniu: **11/11 prób PASS**, health17–68ms,
  zero restartów, zero nowych ERROR/CRITICAL/Traceback. Redis PONG, aplikacje
  uruchomione na właściwych obrazach; identyfikatory/czasy startu usług danych bez zmian.

## Rollback i ograniczenia

- Poprzednie trzy obrazy d3c2c68 i override zachowane; rollback przez
  `/opt/finanse/webapp/releases/1b42e34/rollback.sh`.
- Rollback aplikacji **pozostawia nullable kolumny i rewizję b8**. Nie wykonuje
  downgrade, restore produkcji ani usuwania danych bankowych. Taka operacja
  wymagałaby osobnej zgody, zwłaszcza po uzupełnieniu nowych pól przez użytkownika.
- Nie było wymagane wycofanie tego wdrożenia. Fresh operational review nie znalazł
  Critical/Important w guardach migracji, porównaniach, switchu i rollbacku.
- To weryfikacja wdrożenia i krótkie smoke, nie certyfikacja obciążeniowa ani
  test zalogowanych operacji użytkownika na produkcji. Funkcje po zalogowaniu
  mają pokrycie E2E na fixtures, ale wymagają też normalnej oceny użytkownika.
- Zastane niezatwierdzone zmiany prototypu na main zachowano w nazwanym Git stash;
  ich treść jest w scalonym wydaniu, stash nie został usunięty. Prywatny `webapp/`
  nie został dodany do Git. Worktree feature pozostawiony.
- Dowody/manifesty/logi/render z konfiguracją: prywatnie w
  `/tmp/opencode/release-finance-ui-1b42e34`, bez sekretów i danych osobowych w repo.
  Tymczasowy nieszyfrowany dump próby i skopiowane env usunięto po weryfikacji;
  szyfrowany backup, rollback i dowody hashów pozostają zachowane.

## Następny krok

Ocena nowego interfejsu przez użytkownika na własnym koncie i małe poprawki
zgłaszanych problemów. Nie łączyć tego z nadal zablokowanym importem bankowym Velo.
