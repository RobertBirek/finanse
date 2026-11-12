# Importery A+B: wydanie produkcyjne

**Status: wdrożone i zweryfikowane, `verified-live`. Runtime5dc84fe, schemat84fdbd10aa18.**

## Zgoda i rewizje

- Po zakończeniu P użytkownik wybrał „Tak, pełny etap D”, potem „dokończ”.
- Zgoda obejmuje FF/push main `4d2cf216b5b1b7c0eba6c2357c22a1b3013fc517`,
  runtime `5dc84febc9a22e16afa76a9641e45a5f337d76a0` i odebrane trzy obrazy.
- Migracje: `739144d5eaef → 6bd8758ebc7d → 84fdbd10aa18`; wyłącznie addytywny UP.
- Maintenance, świeży szyfrowany backup bez retencji, restore/próby migracji
  na własnym no-port klonie, trzy usługi i cleanup wyłącznie własnych zasobów.
- Brak zgody na produkcyjny DOWN/restore, import dokumentów, korekty historii,
  Q7/Actual, konfigurację Velo lub usuwanie poprzednich snapshotów/obrazów.
- Awaria oznacza utrzymanie503. App-only rollback do7801 na84 dopuszczalny
  wyłącznie po pełnych aktualnych guardach, snapshotcie i proof zgodności starego
  runtime; brak danych staging/import/receipt/pointer. Nie ma ślepego rollbacku.

## Wykonane przed maintenance

- Required4hostdocs w kolejności oraz runbook `/deploy`, backup/restore i plan.
- Fetch wykazał brak driftu main/origin-main; źródła775 i15dist odpowiadają P.
  Odbiór P:2329backend/617frontend/11proxy/lint/types/build,0runtime-skips.
- Świeży verifier exactimages/nonrootusers10001:10001/importonly/cleanupnoforcePASS.
- Full inheritedCompose różni się tylko image/build. Nowy standaloneactiveoverride
  ma identyczny render jak zatwierdzony stos base+prod+active7801+release5dc.
- Nowe guardy operatora:3testy RED→GREEN. Izolowana próba zatrzymanego frontendu:
  copymaintenance przedstart→503, nohostports/networknone i cleanupbezforcePASS.
- FFmain e3c906f→4d2cf21 i pushorigin/main wykonano; ls-remote potwierdził dokładnySHA.
  Nie zmieniło to obrazów działających bez hostcodebind.
- Niezależny safetyreview nowego operatora D dopuścił wykonanie:0Critical/Important,
  3puretests i22artifacthashesPASS. Jedna odłożona uwaga Minor: durableevidence
  zawiera hashcleanupskryptu i jego wynik, ale nie jego źródło; pełny skrypt zostaje
  w prywatnym katalogu D. Nie omija to bramki ownership/idle lub liveproof.

## Przebieg i kontrole danych

Maintenance/drain/stoppedwriters zakończonePASS: publiczne4ścieżki503,
brak aktywnej pracy wDB/Redis, SIGTERM bezSIGKILL i zatrzymane starebackend/worker.
Zamrożono hash62tabel i manifestuploadów. Przed UP produkcja pozostawała na739,
a aplikacje nie wykonywały zapisów.

Freshfencedbackup `406802268541d10282ae5dcf0467905eb88611ff0afcad21ac18d9f004d399e5`
powstał po zatrzymaniu writerów. Checksumdump/uploads i własny restore/UP-DOWN-UP/
oldreadonlyORM/ledgerPASS. Wszystkie62hashy i uploady są zgodne z zamrożoną produkcją.
Pierwszy check klonu trafił w restart bootstrap PostgreSQL; potwierdzono gotowy
TCPserwer i pustą własnąDB, potem wznowiono tylko restore na tym samymPG.
Nie powtarzano backupu i nie osłabiono guardów.

Pojedynczy produkcyjnyUP i retencja62tabel/13nowychpustych/pointeryNULL/ledger0/
uploadybez zmianPASS. Zachowano migrator z dokładnymID/image/user/env/mounts/
command/exit0/stopped. Nie wykonano drugiegoUP, DOWN lub restoreprodukcji.

Nowe3aplikacje przeszły internalproof za fence: zgodne obrazy/env/user/mounty/sieci,
HTTP200 i ARQcheckPASS. Stos nie ma DockerHealthcheck: sprawdzono prawdziwe HTTP
i ARQ zamiast zakładać istnienie pola State.Health. Operatorguard poprawiono przed
UP po REDmissing→GREEN4puretests; obrazów aplikacji i ich konfiguracji nie zmieniono.

Po otwarciu HTTPShealth/login200, import/history401, wszystkie15plików dist zgodne
co do bajtu. Browser375/1440 GETonlyPASS: redirect chronionych tras, fonty, brak
overflow/JSerrors/foreignrequests/mutations. Screeny obejrzane. Startup3appsERROR0.

Obserwacja minimum300s:29kontroliPASS,0restartów i0błędów w3nowychaplikacjach,
health200, ledger0naruszeń, Redisready. Końcowy read-only proof potwierdził też
retainedmigrator z tym samymID/image/env/user/mounts/command/exit0 oraz brak zmian
usług danych. Nie wykonywano finansowych mutacji smoke ani rzeczywistego importu.

## Końcowy zapis i cleanup

- Aktywne metadata zapisano atomowo dopiero po obserwacji i liveproof:
  `revision=5dc84febc9a22e16afa76a9641e45a5f337d76a0`, `migration=84fdbd10aa18`,
  `release_status=verified-live`, GitTip4d2cf21, trzy dokładneimageIDs oraz
  conditionalapp-only7801rollback bez produkcyjnegoDOWN/restore.
- Nowy activeoverride `R/compose.active.yaml` zachowuje ustawienia inheritedstack;
  jego standalone base+prod+active render odpowiada zatwierdzonemu pełnemu stosowi.
- Dowody53plików w `R/evidence/deployment-ZsicuH9p/`, manifestSHA-256:
  `a105c46320fa2ed033154a4e36c2f37e4f4ecdf16aa6f00314dd66082506341d`.
  Checksumy i skan rzeczywistych wartości sekretówPASS. Surowe env/Compose/dump/
  uploads nie trafiły do tego pakietu lub Git. `archive-proof.json` opisuje manifest.
- Po kontroli exactID/label/image/network/mount/idle usunięto5własnychkontenerów
  klonu i1własnywolumen, plaintextrestore i credentiale klonu. Nie użytoforce/prune.
  Wcześniejszy izolowany fenceprobe także usunięto po kontroli własności.
- Zachowano backup40680226, poprzednie obrazy/override7801, nowy pakiet i migrator
  `fdafa2ef1a6c426985b13c5cc343fef051ecb458def3a11affe853fee57ca9f5` jako dowód.
  Cudze środowiska i prywatne oryginały pozostały nietknięte.
- Nie był potrzebny rollback. Nie zmieniono Q7/Actual, historii, sald ani konfiguracjiVelo.

## Decyzje i ograniczenia

Dokładne775sourcehash/15dist/images pozwoliły wykorzystać świeży odbiórP bez
ponownego2-godzinnego pełnego backendu podczas maintenance. Każdy drift blokowałby
to reuse. NiezależnyDreview obejmował operatora, nie powtórkę aplikacji.

Readiness przyjęto z rzeczywistegoHTTP/ARQ, ponieważ zaakceptowany stack nie ma
DockerHealthcheck. Po RED→GREEN4puretests odnowiono manifestoperatora przed UP;
nie zmieniano aplikacji lub konfiguracji runtime. Bootstraprestart własnegoPG
obsłużono przez potwierdzenie pustej własnejDB i finalnegoTCP, bez obchodzenia
guardów lub powtórzenia backupu. Rollback nie był automatyczny ani wykonywany.

**Odłożona Minor:** pakiet audytowy zawiera hash i wynik cleanup, ale nie jego
źródło `cleanup_clone.py`; pełny plik pozostaje w prywatnym D. Nie dotyczy danych
użytkownika ani poprawności potwierdzonego cleanup.

Pozostaje osobna kontrola read-only następnego dnia. Autoryzowany pilotaż prawdziwego
pliku nadal wymaga osobnej decyzji; test publiczny obejmował wyłącznieGET.
Gałąź i worktree pozostają. Końcowy commit dokumentacji jest lokalny; zatwierdzony
GitTip4d2cf21 pozostaje na main/origin i w metadata, runtime5dc84fe bez zmian.

## Artefakty

- D: `/tmp/opencode/bank-imports-deploy-5dc84fe-ZsicuH9p/` (prywatny).
- R: `/opt/finanse/webapp/releases/bank-imports-5dc84febc9a2-NpudCmae/`.
- Poprzedni zgodny runtime:7801ba5, zachowany aktywny override i trzyimageIDs.
- Niezwiązane robocze audyty pozostają nietknięte.
