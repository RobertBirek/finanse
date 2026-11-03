# Wydanie archiwum dokumentów — ZAKOŃCZONE

## Zgoda

Użytkownik odpowiedział „zatwierdzam” po odbiorze lokalnego8106532 i wymaganiu osobnej
zgody na migrację/wdrożenie. Następnie „akceptuję” na przedstawiony kontrakt: krótkie
okno serwisowe oraz w razie istnienia archiwów maintenance/naprawa nowego wydania,
bez powrotu do niezgodnego starego backendu. Zgoda nie obejmuje kasowania archiwum,
produkcyjnego restore, nowych wywołań AI/OCR ani replay/historycznych napraw.

Kandydat: `81065329cc4cc8edc511800c436bf0a2f7b94025`.
Plan: `docs/superpowers/plans/2026-11-03-document-archive-deployment.md`.

## Przygotowanie

- Dokładne źródła/dist zgodne z odebranym gate1183backend/410frontend/lint/types/build
  i103E2E+1celowy skip. Kod aplikacji nie zmieniony przy przygotowaniu wydania.
- Rzeczywisty baseline: backend/worker/frontend69b6f3d, schemat92eef8e8086c,
  policyenabled/epoch4, brak aktywnej pracy. Zapisane hashe danych/originals i identyfikatory
  usług danych. Read-only preflight początkowo użył błędnej nazwy kolumny; poprawiono
  zapytanie według rzeczywistego modelu, bez DDL lub zmiany danych.
- Świeży snapshot `4e7b441f`: backup i installed isolated restore tego samego snapshotu
  PASS. Bez resetowania limitów systemd i bez odtwarzania produkcji.
- Pakiet `/opt/finanse/webapp/releases/8106532/`, trzy obrazy przypięte imageID.
  Pełny render Compose zgodny z baseline poza obrazami/build; wszystkie210plików
  w każdym obrazie backend/worker zgodne z Git. Runtime zależności bez zmian.
- Offline exactimage routes/DTO/archiveguard PASS; smoke dostosowany do lazyrouterów
  FastAPI przez OpenAPI, nie przez zmianę aplikacji. Brak sieci/providerów/DB w smoke.
- Dodatkowo ten sam snapshot odtworzono w jednorazowym PostgreSQL na odizolowanej
  wewnętrznej sieci Docker (bez portu hosta). Rzeczywista migracja92→2f PASS;
  hashe wierszy starego schematu/księgi/linków/usage/policy zachowane, archived_at
  nullable iNULL dla istniejących dokumentów. Kopia dumpu/oryginałów sprawdzona sumami
  manifestu. Jednorazowy kontener i sieć usunięte.
- Stary ORM na nowym schemacie przy zerze archiwów PASS wyłącznie w izolacji;
  syntetyczny stan archiwum blokuje recovery do starego runtime. Ogólny rollback
  w nowym pakiecie celowo odmawia wykonania; nigdy nie usuwa archived_at.
- Kontroler12offline testów PASS, w tym RED→GREEN dla guardów, niezatwierdzonych
  transakcji w toku i równoległej aktywności użytkownika po otwarciu aplikacji.
  Oryginalne przetestowane wersje kontrolera/guardów zachowano z kontrolą hashy;
  program migracji identyczny z rzeczywiście wykonanym rehearsal.

## Wykonanie i odbiór

Niezależny read-only operations review `ses_e5e5a8f3dffeSRkQPmcwfI1T2e`: Approved,
Critical0/Important0. Związano265artefaktów;12offline testów ponowniePASS. Preapply
potwierdził niezmieniony baseline/config/obrazy i świeżość backupu (1282s).
Jednorazowy apply uruchomiony jako `sh_1a1a93a70001Czr6HpNj6dSyc5`; wynik jeszcze
nie był odebrany w poprzednim wpisie. Callback potwierdził `verified.json` PASS:
schemat2f4b2c2a527c i backend/worker/frontend8106532. Nie powtarzać apply. Procedura:

1. Ponowna kontrola zgody/hashów/config/baseline/freshbackup/idlework.
2. Zatrzymanie jedynego ingressu frontend i potwierdzenie blokadyAPI, naturalne
   zakończenie requestów/pracy, następnie zatrzymanie backend/worker.
3. Jedna addytywna migracja2f z ograniczonym czekaniem na blokady; bez downgrade.
4. Backend/worker810 przy nadal zamkniętym ingressie, wewnętrzna kontrola zdrowia
   i ścisłe porównanie danych/originals/księgi. Dopiero potem frontend810.
5. HTTPS/assets/authrejection, browser375/1440 GET-only, minimum5min obserwacji,
   atomowy active-release i jawne ograniczenie recovery. Po otwarciu nowa aktywność
   użytkownika jest dozwolona; nie traktować jej jako korupcji spowodowanej wydaniem.

Przy błędzie ingress pozostaje zamknięty, archiwum i schemat zachowane; bez automatycznego
uruchamiania starych obrazów lub restore produkcji. Pełne dane dowodowe root-only:
`/tmp/opencode/document-archive-deploy-20261103/`. Bez sekretów/treści dokumentów w raporcie.

### Stan po apply

- Ścisła kontrola przed otwarciem ingressu (`fenced-verified.json`) potwierdziła
  zachowane wiersze starego schematu, księgę, linki, usage, politykę i pliki oryginalne.
- Publiczne health/login/assets i pięć odrzuceń anonimowego API PASS. Nowa aplikacja
  jest otwarta; nowe działania użytkownika nie są traktowane jako korupcja wydania.
- Browser375/1440 i finalizer11próbek/>=5min uruchomione jako
  `sh_1a1aa1ada001vR8wdLyyHVnXPU`; czekać na wynik, nie powtarzać wdrożenia.
- Odroczony OpsReviewMinor: check/dropTOCTOU przy ręcznym downgrade migracji2f.
  Taki downgrade nie jest wykonywany ani dozwolony w tej procedurze; ogólny rollback
  odmawia. To ograniczenie zabezpieczenia ręcznej ścieżki, nie blocker obecnego apply.

## Odbiór końcowy

- Callback `sh_1a1aa1ada001vR8wdLyyHVnXPU` PASS: browser375/1440 bez overflow,
  pageerror/foreignorigin/mutacji, fontsloaded, prywatne trasy→login.11próbek343,69s
  obserwacji, zero nowych errorów w logach usług i brak restartów.
- Atomowy active-release sfinalizowany `2026-11-03T13:53:23.372938+00:00`:
  trzy usługi81065329cc4cc8edc511800c436bf0a2f7b94025, migration2f4b2c2a527c,
  migration_executed=true, backup4e7b441f, genericrollbackdisabled/rollback_override=null.
- Fresh `final_check.py` PASS: dokładne imageIDs/OCI/source/dist, render konfiguracji,
  HTTPS, DB/Redis/ARQworkerreadiness i dataIDs. Wiersze starego schematu/finanse/linki/
  usage/policy zachowane; jedyną różnicą23własne audyty odrzucenia anonimowego dostępu
  (5API+18browser). Dokładny hash zbioru oryginałów niezmieniony.
- `final-readonly-proof.json` i pozostałe dowody root-only pod wskazaną ścieżką;
  kopia kontrolerów/zgody/odbioru/review w8106532/archive-operations-evidence.
  Bez nowych AI/OCR, mutacji dokumentów/finansów w smoke, cleanupu produkcji,
  napraw historycznych, hostmainmerge/pushu lub usuwania dawnych obrazów.
- Nie powtarzać apply, migracji lub finalizera. Rzeczywista próba użytkownika może
  teraz użyć Dokumenty→Archiwum; odczyt AI nie jest częścią potwierdzenia tego wydania.

### Certyfikacja uzgodnionego zakresu

| Gate | Wynik |
|---|---|
| Źródła/gate1183backend/410frontend/lint/types/build/103E2E+1skip | PASS, dokładne hashe |
| Zewnętrzny CI | Nie dotyczy: lokalny gate przypiętegoSHA |
| Backup/installedrestore/same snapshot/candidate migration rehearsal | PASS |
| Exactartifact/runtimeidentity/schema2f | PASS |
| Liveness HTTPS i readiness DB/Redis/worker | PASS |
| Krytyczne publiczne trasy/assets/authrejection/browser375/1440 | PASS |
| Zachowanie wierszy/księgi/linków/originals/usage/policy/dataIDs | PASS |
| Logi/11próbek/>5min/atomowa finalizacja | PASS |
| Nowe mutacje po zalogowaniu/real AI/OCR | Wyłączone z zakresu; lokalne/in-isolation testy funkcjonalne PASS |

Werdykt: **GREEN w zatwierdzonym zakresie wdrożenia**, nie twierdzenie o nowym odczycie
prywatnej faktury lub próbie archiwizacji rzeczywistego dokumentu użytkownika.

### Przypięte obrazy

| Usługa | Zweryfikowany image ID |
|---|---|
| backend | `sha256:1391f7d53945261ef2a6295058f4a366c2b4faa48114da75e8fdb9188329bb14` |
| worker | `sha256:1391f7d53945261ef2a6295058f4a366c2b4faa48114da75e8fdb9188329bb14` |
| frontend | `sha256:0f9fb2601bc90758f1e175fda66385399cea5a91fe77e7c3041ff49beb930fc5` |

Wszystkie trzy obrazy mają OCIrevision81065329cc4cc8edc511800c436bf0a2f7b94025.
Nie usuwać wcześniejszych obrazów, ale nie uruchamiać ich dawnych skryptów rollbacku.

### Decyzje operacyjne

- Zachowano wcześniejszy pełny gate i porównano dokładne hashe źródeł/distu z Git810,
  zamiast ponawiać suite dla nowych wpisów dokumentacji. Przy rozbieżności apply blokuje.
- Zatrzymanie wyłącznie ingressowego frontendu daje fence także dla API z cache klienta;
  backend jest tylko nafinanse_internal. Wewnętrzny odbiór backend/worker następuje
  przed uruchomieniem nowego frontendu. Koszt awarii: kontrolowana niedostępność503.
- Ogólny rollback do starego runtime jest zawsze wyłączony w nowym pakiecie, nawet
  przy zerze archiwów. Jest to bardziej konserwatywne niż minimum; koszt to dłuższa
  naprawa zamiast automatycznego przywrócenia niezgodnego backendu.
- Ścisła równość danych jest dowodzona za zamkniętym ingressem. Po otwarciu dozwolone
  jest nowe użytkowanie; kontrolujemy runtime/schemat/ledger i jawnie raportujemy
  ewentualne różnice, zamiast przypisywać każdą mutację wydaniu. To nie jest dowód
  semantycznej poprawności nowych prywatnych danych.
- Reviewer nie wykonywał produkcyjnych/providerowych prób ani nie czytał sekretów
  i prywatnych dokumentów. Parent wykonuje read-only certyfikację runtime/browser;
  nie deklarujemy nowego rzeczywistego odczytu faktury. Dla kopii i konfiguracji
  dowodami są checksums/rowhashes i pełne porównanie renderów/HMAC, nie ręczny audyt
  wartości prywatnych danych lub sekretów.

## Poza zakresem

Nowe realne AI/OCR, mutacje dokumentów/finansów w produkcyjnym smoke, replay, import,
cleanup/GC, refundowaniequota, scalenie hostmain, push i usuwanie innych worktree.
Dwie drobne uwagi implementacji pozostają jawnie w TASKS (terminaljob delivery i375px).
