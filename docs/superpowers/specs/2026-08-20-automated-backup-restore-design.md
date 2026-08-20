# Automatyczny backup i restore drill — projekt

**Data:** 2026-08-20  
**Status:** zaakceptowany projekt — oczekuje na review dokumentu  
**Cel:** codziennie wykonywać zaszyfrowany backup produkcyjnej bazy PostgreSQL
i uploadów oraz raz w miesiącu wykonywać izolowany restore drill.

## Zakres

Systemd będzie uruchamiał istniejące, wersjonowane skrypty
`ops/backup.sh` i `ops/restore-verify.sh` przez targety Makefile w
`/docker/finanse`. Nie zmienia formatu snapshotu, retencji Restic (7
dziennych / 4 tygodniowych / 6 miesięcznych), bazy produkcyjnej ani polityki
restore: drill nadal akceptuje wyłącznie loopbackową bazę o nazwie kończącej
się na `_restore` lub `_test`.

Sekrety pozostają wyłącznie w obecnych plikach root-only pod
`/docker/finanse/secrets/` i `.env`. Ani unity systemd, ani journal, ani Git
nie zawierają haseł, URI z hasłem lub kluczy API.

## Warianty rozważone

1. **Cron:** najprostszy i zgodny z istniejącym VPS, ale nie zapewnia
   `Persistent=true`, spójnego statusu i wygodnej diagnostyki.
2. **Systemd timers (wybrany):** trwały harmonogram, status przez
   `systemctl`, logi w journalu i wykonanie zaległego backupu po restarcie
   serwera.
3. **Scheduler w kontenerze:** niepotrzebnie zwiększa powierzchnię awarii dla
   dwóch zadań administracyjnych hosta.

## Architektura

### Wersjonowane definicje i instalacja

- Definicje unitów będą wersjonowane w repozytorium w `ops/systemd/`.
- Skrypt instalacyjny skopiuje jawnie wskazane unity do
  `/etc/systemd/system/`, wykona `systemctl daemon-reload` oraz włączy oba
  timery. Nie będzie tworzył ani modyfikował sekretów.
- Instalacja wymaga roota i jest wykonywana tylko jawnie przez operatora.
- Dokumentacja operacyjna opisze instalację, weryfikację, ręczne uruchomienie,
  przegląd logów oraz bezpieczne wyłączenie timerów.

### Backup

- `finanse-backup.timer` użyje
  `OnCalendar=*-*-* 02:30:00 Europe/Warsaw` oraz `Persistent=true`.
- `finanse-backup.service` uruchomi `make -C /docker/finanse backup`.
- Wspólny hostowy lock (`flock`) serializuje backup i restore drill. Proces
  będzie oczekiwał najwyżej 15 minut na zwolnienie locka; po przekroczeniu
  limitu zakończy się błędem bez wykonywania częściowego zadania.
- Usługa zapisuje standardowe wyjście i błędy tylko do journald. Własny skrypt
  backupu zachowuje obecne prywatne katalogi tymczasowe i cleanup.

### Miesięczny restore drill

- `finanse-restore-verify.timer` użyje
  `OnCalendar=Sun *-*-01..07 04:30:00 Europe/Warsaw`, co oznacza pierwszą
  niedzielę miesiąca, oraz `Persistent=true`.
- `finanse-restore-verify.service` pobierze identyfikator najnowszego
  snapshotu wyłącznie przez Restic i wywoła wersjonowany target
  `restore-verify` z tym identyfikatorem.
- Target restore jawnie załaduje te same root-only zmienne konfiguracji co
  backup. Nigdy nie interpoluje ich do argumentów procesu ani logów.
- Weryfikacja odtwarza dane tylko do `finanse_restore` na `127.0.0.1:55431`,
  porównuje checksumy i rewizje, aplikuje migracje oraz kontroluje double-entry
  invariant.
- Dedykowany wrapper schedulera po sukcesie drillu usuwa wyłącznie dokładny,
  wcześniej utworzony katalog `RESTORE_DIR/uploads` i bazę
  `finanse_restore`. Przed usunięciem ponownie wymaga loopbackowego hosta,
  dokładnej nazwy bazy i katalogu pod `/docker/finanse/data/restore-drill`.
  Nieudane czyszczenie jest błędem usługi i nie dopuszcza następnego drillu do
  pracy na niepustym celu.

### Awaria i obserwowalność

- Błąd backupu lub drillu kończy service kodem non-zero i uruchamia
  `OnFailure=finanse-operation-failure@%n.service`.
- Jednostka failure zapisuje zwięzłe, pozbawione sekretów zdarzenie do
  journald z nazwą nieudanej usługi i wskazuje operatorowi `journalctl -u`.
- Operator sprawdza harmonogram przez `systemctl list-timers` i stan przez
  `systemctl status`; szczegóły przez `journalctl -u finanse-backup.service`
  lub `journalctl -u finanse-restore-verify.service`.
- Timer pozostaje włączony po pojedynczym błędzie, aby kolejne planowane
  uruchomienie odbyło się automatycznie.

### Hardening unitów

- Unity działają jako root, ponieważ istniejący Makefile odczytuje Docker
  network inspection i korzysta z Docker socketu. Nie ma osobnego użytkownika
  o równoważnych, mniejszych uprawnieniach.
- Zostaną ustawione co najmniej `NoNewPrivileges=true`, `PrivateTmp=true`,
  `UMask=0077`, ograniczony `ReadWritePaths` do katalogów roboczych i restore
  oraz jawny `WorkingDirectory=/docker/finanse`.
- Restrykcje, które blokowałyby wykonanie klienta Docker lub dostęp do
  root-only sekretów, nie będą deklarowane pozornie; zostaną zweryfikowane
  testowym uruchomieniem usługi.

## Przepływ danych

1. Timer uruchamia service o zaplanowanej porze w `Europe/Warsaw`.
2. Service uzyskuje wspólny lock.
3. Makefile ładuje lokalne pliki środowiskowe bez ich wypisywania.
4. Backup tworzy dump, archiwum uploadów i manifest, a Restic wysyła
   zaszyfrowany snapshot oraz stosuje retencję.
5. Drill wybiera najnowszy snapshot i wykonuje istniejące fail-closed
   odtworzenie do izolowanego celu.
6. Exit status trafia do systemd i journald; błąd aktywuje failure unit.

## Weryfikacja

- Testy statyczne sprawdzają timer calendars, `Persistent=true`, lock,
  brak sekretów oraz wywołania wyłącznie do zatwierdzonych Make targets.
- Instalator przechodzi `systemd-analyze verify` dla unitów przed ich
  instalacją i po `daemon-reload` potwierdza aktywność timerów.
- Po wdrożeniu operator ręcznie uruchamia backup service, sprawdza snapshot
  Restic i status jednostki; pierwszy zaplanowany drill lub jawny test
  potwierdza izolowane odtworzenie.
- Test błędnej konfiguracji musi kończyć usługę non-zero i tworzyć zdarzenie
  failure bez ujawnienia sekretu.

## Poza zakresem

- Powiadomienia e-mail, Slack, Telegram i zewnętrzny monitoring.
- Zmiana harmonogramu retencji Restic.
- Automatyczny restore do produkcji, automatyczna korekta danych albo
  automatyczna rotacja sekretów.
