# Jedno polecenie wydania aplikacji

Po zaliczonym pushu do `main` uruchom `finanse-release <pełny SHA>` na VPS.
Wpisanie pełnego SHA zatwierdza wyświetlone obrazy i powrót do poprzedniego wydania.
Polecenie zapisuje dowody prywatnie. Komunikat STOP oznacza, że wydanie wymaga
decyzji operatora. Po rollbacku można ponowić wydanie po potwierdzeniu
odtworzonego stanu oraz nowych ID kontenerów.

## Jednorazowe uruchomienie

1. Zrecenzuj zmianę narzędzi i włącz ją do historii `main` **bez squashowania**.
   Udostępnij na `main` zgodną historię obecnej produkcji, bez naruszania
   niezależnych zmian w roboczym checkoutcie. Zapisz zaakceptowany commit
   integrujący narzędzia jako `bootstrap_anchor` i aktualną pełną rewizję jako
   `bootstrap_previous`. Ta wyjątkowa granica działa tylko na pierwszym wydaniu
   i musi mieć taki sam kod aplikacji oraz migracje jak aktywna produkcja.
2. Z zatwierdzonego checkoutu zainstaluj jako root `finanse-release` w
   `/usr/local/sbin` oraz `backup-restore` i katalog `backup-bin` razem w
   `/usr/local/lib/finanse-release`. Pliki i katalogi muszą należeć do root i nie
   być zapisywalne przez grupę ani innych. Na VPS nadaj administracyjnemu
   `gh` wyłącznie odczyt repo i wyników Actions. Repozytorium użyte przez
   kontroler jest osobnym checkoutem Git z odczytem zdalnego `main`; kontroler
   nie uruchamia żadnego skryptu z pobranego commitu.
3. Przygotuj prywatny katalog stanu obok istniejących wydań produkcyjnych, np.
   `/opt/finanse/webapp/releases/one-command`, i zapisz w nim `active.json` (0600).
   `init-baseline <zatwierdzony inventory V2> <zatwierdzony SHA256> <aktywne metadane> <dowód poprzedniego wydania>`
   generuje propozycję bez odczytu Dockera. Sprawdź i zatwierdź ją niezależnie.
   Późniejsze stany wynikają z zaliczonego i jawnie zatwierdzonego wydania.
4. Ustaw `/etc/finanse-release/config.json` (root, 0600). Użyj dokładnych wartości
   z zatwierdzonego spisu i plików instalacji. Przykładowe pola:

```json
{
  "github": "RobertBirek/finanse",
  "remote": "https://github.com/RobertBirek/finanse.git",
  "repository": "/var/lib/finanse-release/git",
  "state": "/opt/finanse/webapp/releases/one-command",
  "active_release": "/opt/finanse/webapp/releases/active-release.json",
  "workflow_sha256": "SHA256 zaakceptowanego .github/workflows/ci.yml",
  "bootstrap_anchor": "zaakceptowany pełny SHA wdrożenia narzędzi",
  "bootstrap_previous": "pełny aktywny SHA",
  "backup_restore": "/usr/local/lib/finanse-release/backup-restore",
  "lock": "/run/lock/finanse-deploy.lock",
  "project": "finanse",
  "url": "https://finanse.birek.online",
  "compose": ["/docker/finanse/compose.yaml", "/docker/finanse/compose.prod.yaml"],
  "env_file": "/docker/finanse/.env",
  "postgres_os_user": "70:70",
  "psql": "/usr/local/bin/psql",
  "pg_socket": "/var/run/postgresql",
  "pg_port": "5432",
  "pg_database": "zgodnie z zatwierdzonym spisem",
  "pg_role": "zgodnie z zatwierdzonym spisem",
  "containers": {
    "backend": "finanse-backend", "worker": "finanse-worker",
    "frontend": "finanse-frontend", "postgres": "finanse-postgres",
    "redis": "finanse-redis", "stirling": "finanse-stirling"
  }
}
```

## Odbiór

Workflow dispatch na gałęzi służy do prób. Kontroler produkcji akceptuje tylko
artefakt udanego pushu do chronionego `main` i przypięte bajty workflow.
Przed pierwszym przełączeniem przećwicz trzy obrazy i rollback w osobnym
projekcie Docker z syntetyczną bazą i kolejką. Sprawdź próbę z błędnym
identyfikatorem obrazu i zmienionym Compose. Te próby nie potrzebują sekretów
produkcyjnych.

Po pierwszym zaliczonym wydaniu przez nową ścieżkę usuń routing tylko
`dev.finanse.birek.online`, zatrzymaj jego projekt Compose i zachowaj checkout,
konfigurację, wolumeny i kopie. Przed usunięciem routingu sprawdź jego dokładną
konfigurację i wykonaj kopię umożliwiającą przywrócenie adresu.

Zaliczenie obejmuje trzy kolejne zwykłe wydania, każde z jedną zgodą i bez
ręcznych kroków pomiędzy zgodą a obserwacją produkcji. Cel to 15 minut od
zgody. Czas CI licz oddzielnie. Jeśli dłużej trwa kopia lub test, odnotuj
opóźnienie i zachowaj bramkę.
