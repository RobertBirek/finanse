# Gotowe etapy finansów — preflight wydania produkcyjnego

## Kontynuacja po zgodzie na konkretną rewizję

**Wynik końcowy: WDROŻONO / ACTIVE.** Raport:
`docs/audits/2026-11-05-finance-production-release.md`. Dalsze sekcje STOP opisują historię,
nie aktualną blokadę; exact8121512 i schema7b57 są już na produkcji.

Poniższy preflight opisuje stan historyczny przed potwierdzeniem. Użytkownik odpowiedział
„tak” na `8121512`/pełny zakres/host fast-forward/serwerowe AI bez historii. Host checkout
zaktualizowany kontrolowanym FF do tej rewizji; zainstalowany restore drill zakończył się
PASS (sześć migracji, checksumy i invariant księgi). Wdrożenie jest wykonywane etapami;
wynik końcowy należy odczytać z osobnego raportu wydania, nie z historycznej sekcji STOP.

Jedno niezależne review procedury operacyjnej wskazało pięć braków: blokada dostępu
do końca smoke, metadane przed jej zdjęciem, drain po zatrzymaniu procesów, oznaczenie
audytu operatora oraz dowód izolacji backendu. Poprawione w procedurze; testy operacyjne
4RED→7GREEN. Rzeczywisty reverse proxy to Caddy, nie dawny NPMplus; backend tylko internal,
bez publikowanych portów, Caddy nie ma sieci backendu i kieruje domenę do frontendu.

Podczas maintenance wykryto dodatkowo markery deduplikacji zakończonych zadań cron ARQ.
Nie są aktywną pracą: `finish_job` zachowuje klucz in-progress, usuwając payload i wpis
kolejki. Osobny probe rozróżnia je od faktycznych zadań (2RED→2GREEN). Kontrola po
zatrzymaniu wykryła również jedno rzeczywiście pozostawione zadanie dispatchera;
bramka odmówiła przejścia dalej. Zaplanowano ograniczony drain starym runtime bez
harmonogramowania nowych cronów, a dopiero po zerowych kolejkach świeży backup/restore.
Nie pominięto bramki i nie kasowano kluczy Redis ani zadań domenowych.

## Zgoda i precyzyjny kandydat

User polecił „jak masz gotowe to wdróż i włącz wszystko, najwyżej będziemy poprawiać
na bieżąco”. To zgoda kierunkowa na produkcyjne udostępnienie gotowych etapów i serwerową
aktywację AI, nie usunięcie walidacji/zgód ani batch historii. Zgodnie z `/deploy`
przed zmianą runtime/migracją wymagana jest akceptacja **dokładnej rewizji i zakresu**:

`8121512d1479ed101851f3617f970c7c132f40c2` (kandydat, nie yet deployed).

Zakres: daty zakupów/księgowania i raporty; ręczne kategorie/splity; zatwierdzane reguły
3A; propozycje AI3B; ręczne produkty/rabaty/sklepy/historia4A; odczyt zdjęcia4B na żądanie
z jawnym importem. Spójne backend/worker/frontend; sześć addytywnych migracji
`2f4b2c2a527c`→`7b57f2f0bde6`, bez backfillu.

Receipt_items i suggestions serwerowo dostępne po wdrożeniu, OpenAI/Terra jak uzgodnione
dla ekstrakcji. Zachowane limity i wszystkie wymagane opt-in oraz zatwierdzenia finansowe:
3A wymaga jawnej własnej kategorii technicznej i zatwierdzonej reguły;3B osobnej zgody
właściciela na eksport opisów/taksonomii;4B wskazania zdjęcia i zgody konkretnego eksportu.
Nie tworzyć pozorowanych grantów użytkowników, nie aktywować arbitralnych reguł,
nie przetwarzać dawnych transakcji/zdjęć ani nie usuwać ręcznych zatwierdzeń.

## Bieżąca produkcja (odczyt bez mutacji)

- Faktycznie działa `81065329cc4cc8edc511800c436bf0a2f7b94025`, nie stary45c8c2d.
  Aktywny `/opt/finanse/webapp/releases/8106532/compose.active.yaml`.
- Schema `2f4b2c2a527c`; vision włączoneepoch4; advisorSol/ekstrakcjaTerra.
- Kandydat jest potomkiem aktywnego kodu, requirements bez zmian. Zachowane backend/
  worker/frontend imageIDs oraz postgres/redis/stirling containerIDs (privateOUT).
- Hostcheckout `/opt/finanse` jest stary: `1865d90`. Nie jest źródłem kodu działających
  kontenerów; zainstalowany restore wrapper jednak korzysta z migracji hostcheckoutu.

## Przeprowadzone przygotowania

- Retained exactsource proof1628backend/493frontend/lint/types/freshbuild/141E2E+
  1expectedskip PASS oraz wszystkie plikiHEAD zgodne zgate. Nie powtarzano niezmienionego
  godzinnego gate; żadnych zmian produktu lub nowych APIcalls.
- `ops/prepare_release.py` utworzył wersjonowany kandydat
  `/opt/finanse/webapp/releases/8121512` z zatwierdzonego frontenddist i jawnych tagów
  zachowanych bieżących runtimeimages; bez wymiany kontenerów. BudowaDocker networknone.
  Wszystkie3obrazy zbudowanePASS; offline runtimeimport/OpenAPI nowego endpointu/
  pojedynczy Alembichead7b57 PASS wnetworknone/read-only kontenerze, bez połączenia zDB.
- Świeży encryptedbackup systemd2026-11-05 17:48CET zakończonyResultsuccess/exit0;
  restore log wskazuje snapshot`7e2c0b91`. Backup nie jest jeszcze uznany za sprawdzony
  aż do pomyślnego zakończenia odtworzenia i kontroli ledgeru.
- Próba przez wymagany zainstalowany `finanse-restore-verify.service` odtworzyła snapshot,
  zweryfikowała checksums i napotkała **Can't locate revision2f4b2c2a527c** podczas Alembic.
  Przyczyna: hostcheckout1865d90 nie zawiera już działającej migracji archiwum2f.
  Wrapper wycofał własny restore target; stopservice zatrzymał automatyczny restart.
  Timer pozostaje aktywny, polityki/harmonogramu nie wyłączono.

## Blokady przed apply

1. Akceptacja exactSHA8121512 i scope, w tym uporządkowanie hostcheckoutu przez kontrolowany
   fast-forward do tego samego kandydata (bez push, bez nadpisania plików prywatnych/webapp).
2. Ponowny restore przez zainstalowany wrapper po udokumentowanej naprawie rozjazdu
   hostmigracji; wtedy snapshot2f→head7b57, checksumy/ledger/uploady. Nie obchodzić bramki
   ani nie ręcznie restaurować na produkcję. Do czasu PASS brak produkcyjnej migracji/apply.
3. Renderowany pełny Compose musi zachować aktualną konfigurację/hardening ingress oraz
   DB/Redis/Stirling, keys prywatne, jedynie jawne nowe serwerowe flagi/configAI.
4. Freeze ingress/admission i drain aktywnych kolejek, aktualny backup i plan nieutracenia
   danych między backupem a przełączeniem, sprawdzenie każdego obrazu/migracji.
5. Kontrolowany rollback kompatybilny ze schematem i nowymi dowodami. Istniejący release
   ma zakaz genericoldruntime rollback po nowych stanach. Nie zakładać bezpiecznego
   cofnięcia po powstaniu approved_llm/reguł/pozycji/odczytów. Zachować schema i dowody,
   przy niezgodności maintenance/fixforward; bez automatycznego restore/downgrade/DELETE.
6. Po apply: exactimage/revision/nohostappmount, niezmienione dataserviceIDs,
   HTTPS/assets/health/odrzucenie anonimowych odczytów, workerlogs, readonlybrowser375/1440, obserwacja;
   dopiero później atomowe active-release metadata.

## Stan przekazania

**Nie wdrożono** i nie aktywowano nowych funkcji na produkcji. Backup jest świeży,
restore nadal BLOCKED na rozjechanym checkoutcie. Nie prezentować buildów lub backupu
jako udanego wydania. OUT `/tmp/opencode/finance-all-release-20261105/`, stare wersje/
snapshoty i obrazy pozostają zachowane. Zastane Velo/Q7dirty w worktree bez zmian.
