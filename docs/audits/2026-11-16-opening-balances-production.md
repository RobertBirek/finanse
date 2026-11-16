# BO — integracja i wdrożenie

**Status: VERIFIED LIVE — `45bcf88`, schema `efaf78432563`.**

## Zgoda i wersje

Użytkownik zatwierdził push main, spójne wydanie backend/worker/frontend,
świeży backup z próbą odtworzenia, dokładną migrację `efaf78432563` i krótką
przerwę techniczną. BO=0 ma objąć istniejące konta bez zmiany sald i historii.

- Produkt: `ee21930`, po jednym readonly review i poprawce annotations.
- Aktualny main przed integracją: `d8b676f`.
- Main po zwykłym push bez force: `45bcf8812ded8696624ead6dd65d2a0c5f80710a`.
- CI: [43937664943](https://github.com/RobertBirek/finanse/actions/runs/43937664943),
  11/11 zadań PASS dla dokładnej rewizji.
- Live przed wydaniem: aplikacje `e0e746e`, schema `2c77e935ee39`.
- Docelowa schema: `efaf78432563`. Bez downgrade lub restore na produkcję.

## Przygotowane dowody

- Integracja zmieniła tylko testy/infrastrukturę CI względem sprawdzonego BO;
  drzewa aplikacji/migracji/frontendu pozostają identyczne z `ee21930`.
- Lint, mypy215/tsc, kolekcja offline,707Vitest i build PASS.
  Początkowy wyścig starego testu DocumentList nie powtórzył się w izolacji ani
  pełnym zestawie; nie zmieniano jego asercji lub kodu.
- Trzy wersjonowane obrazy przygotowano przez `ops/prepare_release.py`.
  `ops/verify_release.py` potwierdził rzeczywiste image IDs i import nonroot10001.
  Osobna kontrola potwierdziła dokładne źródła backend/workera i pliki Vite w obrazach.
- Finalny standalone Compose odpowiada pełnej konfiguracji stary override+nowy
  release; zachowuje hardening, user, env, sieci i upload mount, bez host-code `/app`.
- Nowy klon ma własne ID i wolumen, networknone/noports. Zachowany prywatny klon
  certyfikacyjny pozostaje nietknięty.

## Operator i rozstrzygnięcia

Nowy operator: `/tmp/opencode/opening-balances-deploy-20261116/`, katalog prywatny.
Nie uruchamiamy operatora app-only poprzedniego wydania ze starymi pinami.

- Pierwsza próba nowego restore pytała adminDB zamiast utworzonej scratchDB;
  regresja RED→GREEN wymusza jawny `POSTGRES_DB` dla klonu.
- Multiline JSON z psql wymagał pełnego połączenia linii; regresja RED→GREEN.
  Nie zmieniono danych produkcyjnych przy tych próbach.
- Review bezpieczeństwa wskazał optimize/assert: operator jawnie odmawia startu
  w trybie `-O`/`PYTHONOPTIMIZE`. Regresja RED→GREEN.
- Fingerprint schematu rozszerzono o stare constraints, triggers, views, sequences,
  policies i functions. Dozwolone różnice to nowy BO i jego indeksy oraz techniczny
  indeks kategorii; regresja RED→GREEN.
- Rollback sandbox używa obrazów uchwyconych z rzeczywistych starych kontenerów,
  nie potencjalnie przestarzałego wskaźnika metadanych. Regresja RED→GREEN.
- Uwaga review o braku sprawdzania kwoty BO została zweryfikowana z modelem:
  **nie ma oddzielnej kolumny kwoty**. `transaction_id IS NULL` oznacza dokładnie
  BO=0. Globalna kontrola SQL już odrzuca inny stan dla dowolnego konta.
- Probe właściciela nadpisuje wewnętrznie zależność auth i odrzuca DML.
  To dowód readonly route/data, nie rzeczywistej sesji/cookies. Osobno sprawdzamy
  anonimowe401 i browser logowania. Nie tworzymy produkcyjnej sesji dla testu.
- Backup wydania nie wykonuje `restic forget/prune`: zgoda dotyczy nowej kopii,
  nie usuwania dawnych backupów. Koszt: dodatkowe miejsce w repozytorium.
- Dodatkowa regresja rollbacku wymaga zatrzymania wszystkich writerów przed
  sprawdzeniem braku nonzero BO; RED→GREEN. Sam fence HTTP nie wykluczał
  transakcji pozostającej w locie. Powrót starej aplikacji po nonzero BO jest zabroniony.
- Syntetyczne regresje operatora:11PASS. Actual backup/clone/runtime nadal muszą
  przejść realne bramki; review nie zastępuje tych dowodów.

## Bramka przed przełączeniem

- [x] Exact source/main,11/11CI, obrazy i nonroot/content/config.
- [x] Backup i odtworzenie, migracja na klonie z pełną retencją81starych tabel, sandbox/rollback.
- [x] Maintenance/drain i ponowny backup/restore zgodny z zamrożonym stanem.
- [x] Migracja na produkcji, retencja każdej starej tabeli/schematu/uploads.
- [x] Trzy aplikacje, readonly API, HTTPS/assets/auth, worker i obserwacja.
- [x] Publikacja aktywnego release, własny cleanup i końcowy werdykt.

Próba online zakończyła się PASS dla realnego restore, migracji `2c→efaf`,
globalnego zerowego BO, retencji81starych tabel i ich struktur oraz readonly API.
Sandbox uruchomił rzeczywisty backend, worker i frontend kandydata, następnie
te same trzy usługi na uchwyconych starych image IDs. Brak portów hosta i sieci
produkcyjnej; providers wyłączone tylko w klonie.

## Pierwsza próba produkcyjna — przerwana przed migracją

Fenced backup/restore wykrył różnicę tekstu części CHECK constraints między
źródłem i odtworzonym schematem. Dane wszystkich81tabel były identyczne,
pozostałe struktury także. `pg_restore` przenosi niejawny cast tablicy varchar[]
do text[] na równoważne casty poszczególnych literałów.

Nie pominięto porównania: oryginalne definicje CHECK ponownie sparsowano na
izolowanym klonie, w tabelach TEMP ON COMMIT DROP. Wynik musi być dokładnie
równy odtworzonej definicji. Inne różnice, w tym FK, dane i typy, nadal blokują
wdrożenie. Porównanie przed/po samej migracji pozostaje ścisłe.

Rollback odtworzył stare obrazy, ale ostatnia asercja porównywała uporządkowaną
listę env zamiast jej znaczenia. Sprawdzenie potwierdziło identyczne wartości
wszystkich zmiennych; różniła się tylko kolejność. Nowy helper odrzuca duplikaty
i porównuje mapy klucz→wartość. Obie regresje RED→GREEN, operator13PASS.

Po przerwaniu: HTTPS200/auth401, stare trzy obrazy i ich konfiguracja, worker,
schema2c i metadane potwierdzone. Produkcyjna migracja nie została wykonana.
Dowody zachowano w `attempt-1`; ponowienie używa nowego fenced backupu i nowej
scratchDB, bez nadpisania pierwszej kopii. Zakres wydania nie uległ zmianie.

## Druga próba — migracja zakończona, rollback aplikacji

Świeży fenced backup został odtworzony i sprawdzony z parserowym dowodem CHECK.
Migracja na produkcji przeszła: `efaf78432563`, retencja81starych tabel i ich
struktur, niezmienione uploads, invariant księgi0 oraz globalne BO=0 PASS.

Backend i worker kandydata przeszły readiness i readonly route probe.
Przygotowanie zatrzymanego frontendu używało jednak flagi `create --no-deps`,
której ta wersja Docker Compose nie obsługuje. Operator przywrócił trzy stare
obrazy; potwierdzono runtime/worker/HTTPS200/auth401. Schemat addytywny pozostawiono
na `efaf78432563`, bez downgrade i bez restore produkcji.

Wspierana równoważna komenda to `up --no-start --no-deps --no-build frontend`;
sprawdzono flagi rzeczywistego CLI i dodano regresję RED→GREEN.
Stan globalny BO nadal0 i kompletne powiązanie wszystkich kont potwierdzono.
Dowody zachowano w `attempt-2`.

Końcowe ponowienie jest **app-only** dla tych samych obrazów `45bcf88`:
ponowny świeży backup/restore obecnej schemaefaf, retencja82tabel i przełączenie
aplikacji. Nie wykonuje ponownie migracji ani inicjalizacji danych.
Po tym rozszerzeniu operator ma14regresji; testy aplikacji nie zostały zmienione.

## Końcowy wynik produkcyjny

App-only rollout zakończył się sukcesem. W tej próbie nie wykonywano ponownie
migracji; świeży backup schematu efaf odtworzono na własnym klonie z retencją82tabel.
Ruch otwarto po readiness backend/workera, readonly API i kontroli tożsamości.

| Bramka | Wynik |
|---|---|
| Source/main | PASS — `45bcf8812ded8696624ead6dd65d2a0c5f80710a` |
| CI | PASS — 43937664943,11/11jobs |
| Trzy obrazy/nonroot/content/config | PASS — exactIDs,10001:10001, bez host-code `/app` |
| Backup/restore | PASS — świeże szyfrowane snapshoty, checksums i własny klon |
| Migracja | PASS — `2c77e935ee39→efaf78432563`, tylko w drugiej próbie |
| Retencja | PASS —81starych tabel/struktur/uploads bez zmian, BO=0 dla wszystkich kont |
| Końcowy app-only restore | PASS —82tabele i obecna schemaefaf, brak nowej migracji |
| Liveness | PASS — HTTPS frontend/APIhealth200 |
| Readiness | PASS — SQL readonly route oraz ARQ/Redisworkercheck |
| Ochrona anonimowa | PASS —401 dla kont/osób/transakcji/dokumentów |
| Readonly dane właściciela | PASS — wewnętrzny dependency override, wszystkie odczytane konta mają BO |
| Frontend | PASS — publiczne pliki zgodne z buildem; browser375/1440 bez błędów/overflow |
| Obserwacja | PASS —306.52s,0runtimeERROR/Traceback/restartów |
| Usługi danych | PASS — identyczne ID/obrazy/mounty/StartedAt/restartcounts |
| Publikacja metadanych | PASS — atomowa pod deploylock, status verified-live |
| Cleanup | PASS — tylko własny klon/wolumen/plaintext staging; brak force/prune |

Końcowy werdykt w uzgodnionym zakresie: **GREEN**.
Nie testowano prawdziwego logowania/cookies ani mutacji BO na danych użytkownika.
Zapis BO był sprawdzony lokalnie, w CI i przeglądarkowych fixturetestach;
produkcyjny smoke pozostał readonly. Nie jest to dowód odporności na awarię lub
test wydajności poza krótką obserwacją.

### Artefakty wydania

- Release: `/opt/finanse/webapp/releases/opening-balances-45bcf88/`.
- Active override: `compose.active.yaml`; dowody root-only: `evidence/`.
- Backend: `sha256:81fcdb8dea461d2ef92cfd440da76176ba21b6c71fc112a62fd2a8bb96ff8f09`.
- Worker: `sha256:747dab3ee80bdbf36538aa99a7015a119db8482298dd3aa3f2b03102df8e2bda`.
- Frontend: `sha256:9782eddf5ae0e496299ebe66d905ad4b0e8bea687b56c16d781c65c0b147d1f1`.
- Poprzednie obrazy, konfiguracja i zaszyfrowane backupy obu schematów zachowane.
  Prywatny stały klon certyfikacyjny i pozostałe worktree pozostają nietknięte.
- Wycofanie aplikacji wymaga maintenance, zatrzymania writerów i sprawdzenia
  braku nonzeroBO; po zapisaniu takich BO stara aplikacja nie jest bezpiecznym
  rollbackiem. Nie wykonywać automatycznego downgrade/restore danych.
- Dowody obu wcześniejszych prób zachowano. Dwóch rollbacków operatora nie
  przedstawiamy jako „bezbłędnego wdrożenia”;0błędów dotyczy końcowego runtime.

## Ograniczenia testów lokalnych

Końcowy domyślny Vitest ponownie ujawnił wcześniejszy wyścig w starym
`DocumentList.test.tsx`: etykieta pola jest dostępna przed useEffect wstawiającym
sugestię.706PASS/1FAIL; wynik zachowano. Pełna kontrolowana powtórka z dwoma
workerami:707PASS135.58s. Nie zmieniano/wyłączano asercji; CI dokładnego wydania
ma11/11PASS. Flaky test pozostaje osobną pracą, nie deklarujemy, że go naprawiono.
