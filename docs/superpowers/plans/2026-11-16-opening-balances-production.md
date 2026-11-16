# BO — integracja main i wdrożenie

Zatwierdzenie: użytkownik polecił „wypchaj do main i wdróż”, następnie zatwierdził
poniższe sześć kroków, migrację i ewentualną krótką przerwę.
Kandydat produktu: `ee21930`; remote main przed integracją: `d8b676f`.
Cel: `https://finanse.birek.online`. Live przed wdrożeniem: aplikacje `e0e746e`,
schema `2c77e935ee39`.

## Nienaruszalne granice

- Bez force-push, nadpisania nowych zabezpieczeń testDB lub zmian innych worktree.
- Jedyna migracja produkcyjna: `efaf78432563`, addytywne BO=0 wszystkich kont,
  bez zmian starych tabel, historii, sald lub uploads (poza alembic_version).
- Bez rzeczywistych prób zapisu BO na produkcji. Smoke wyłącznie readonly.
- Backup/restore i dowód retencji przed migracją. Poprzednie obrazy i backup zachowane.
- Nowe obrazy przygotowane wspieranym `prepare_release.py`; nonroot gate z exactIDs.
- Pełna zatwierdzona konfiguracja Compose, tylko backend/worker/frontend.
- Błąd migracji/retencji/health oznacza rollback aplikacji, bez downgrade danych.
  Przed otwarciem ruchu potwierdzić zgodność starego wydania z addytywnym schematem.
- Zachowany prywatny klon i usługi danych nietknięte; cleanup tylko nowych własnych zasobów.

## Kroki

1. [~] Scalić aktualny main, zachować obie historie dokumentacji; lint/types/test
   wynikowego drzewa. Aplikacja BO pozostaje identyczna z testowanym `ee21930`.
2. [ ] Commit i zwykły push `HEAD:main`; potwierdzić pełne CI tej rewizji.
3. [ ] Przygotować wersjonowane obrazy, offline nonroot proof i zgodny rollback;
   sandbox bez providerów, bez operacji na produkcji.
4. [ ] Świeży szyfrowany backup, restore do własnego nowego no-port klonu,
   realna migracja i retencja wszystkich starych tabel/uploads.
5. [ ] Maintenance/drain, ponowny backup i retencja pod blokadą zapisów,
   migracja dokładnej rewizji i spójne wdrożenie trzech aplikacji.
6. [ ] HTTPS/auth/readonly BO/runtime/worker/logs, obserwacja, atomowa publikacja
   metadanych dopiero po sukcesie; docs i cleanup własnych zasobów.

Dowody operacyjne: `/tmp/opencode/opening-balances-deploy-20261116/`.
Status i źródłowe SHA, komendy, zakres zgody i identyfikatory zasobów zapisujemy
w tym katalogu; publiczny raport nie zawiera sekretów lub danych finansowych.
