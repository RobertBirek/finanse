# Walidacja dat odpowiedzi vision — 2026-11-02

## Zgoda i diagnoza

Użytkownik zatwierdził przygotowanie i wydanie poprawki ISO/null oraz bezpiecznej
obsługi błędnej odpowiedzi po komunikacie „AI niedostępne”. Upload JPEG45c8c2d był
już poprawny. Read-only agregacja pokazała1nowy JPEG/done oraz1visionjob failed,
attempts_exhausted po2próbach. Analiza wyłącznie klas/pól/ścieżki kodu wykazała
ValidationError ReviewFields.sale_date poza try/catch w vision_client.py.
Nie wypisano wartości pola, treści faktury/modelresponse, nazw/ID lub surowych logów.
Daty błędów14:53:59 i14:56:13UTC, nie ostatnie45min od czasu późniejszego zgłoszenia.

VisionFields dopuszczał dowolne stringi dat, a ReviewFields wymagał rzeczywistej daty
ISO. Konwersja po poprawnej odpowiedzi modelu rzucała nieobsłużony wyjątek; wygaśnięcie
lease i recovery kończyły attempts_exhausted. To nie dowód niedostępności dostawcy.
Odtworzenie syntetyczne potwierdziło tę samą granicę bez AI/DB lub prywatnego pliku.

## Zmiana

- Trzy wymagane nullable pola dat mają schemat `YYYY-MM-DD` lub null i opis/prompt
  zabraniający wymyślania brakujących/niejednoznacznych dat i zwracania opisów/czasów.
- Istniejący ReviewFields nadal semantycznie odrzuca niemożliwe lub niekanoniczne
  daty, np. syntetyczne2026-02-30. Nie konwertujemy arbitralnych formatów lub wartości
  faktury i nie dopisujemy żadnej daty.
- Konwersja do ReviewFields jest wewnątrz bezpiecznej granicy ValidationError/ValueError:
  stały log bez inputów i VisionProviderError invalid_model_output/retryablefalse
  raised fromNone. Worker zapisuje terminalną rewizjęincomplete,1próbę; bez crasha,
  lease-retry lub przekazania błędnych wartości do finansów.
- UI invalid_model_output: „Nieprawidłowy wynik AI”; stały alert i formularz ręczny.
  Dotychczasowy attempts_exhausted: „Odczyt AI przerwany” oraz jawny przycisk PonówAI,
  także gdy historyczna rewizja jest incomplete. Samo otwarcie nie wywołuje AI.
- Nie zmieniono auth, modeli/providerów/kluczy, konfiguracji i polityki vision, limitów,
  worker/CAS/quota/retry, schematu bazy, oryginałów lub ręcznego zatwierdzania finansów.
  Nie ponowiono odczytu istniejącej prywatnej faktury i nie edytowano jej starej rewizji.

## Testy i przegląd

- Adapter/worker RED:11failed,21passed; frontend RED:5failed,42passed.
  GREEN focused36backend i47frontend, Ruff/mypy/ESLint/tsc PASS.
- Testy obejmują wszystkie3pola, złyformat i niemożliwą datę, nullable i leapdate,
  właściwy Responses schema/prompt, brak inputów/sekretów wlogach i exceptionrender,
  prawdziwy worker+adapter zMockTransport:1request, terminalinvalid_model_output,
  brak drugiej próby i zachowanie oryginału.
- Niezależny source/security review PASS, bez Critical/Important/Minor.
- Kontroler wykrył dodatkową lukę UX: stara incomplete/attempts_exhausted nie miała
  przycisku jawnego ponowienia. Dodane4regresjeRED→GREEN,51focusedfrontend/lint/typesPASS.
  Pierwszy pełny gate przerwany świadomie SIGINT tylko własnego pytest po244PASS,
  nie błąd produktu; teardown zakończony. Dowody zachowane wgate-interrupted.
  Pierwsze93E2E+1skip PASS zachowane; po zmianie UI uruchomiono świeżybuild/E2E i
  nowy pełny gate z manifestami niezmienionych źródeł/dist. Nie uruchamiać ich ponownie.
- 16offlineguardów procedury wydania PASS, scoped operationsreview warunkowoApproved;
  wymagane proofy exactimage i zgoda exactSHA następnie spełnione przedapply.
- Świeży backup **8d9d72db** oraz zainstalowany restore tego samego snapshotu success/0,
  bez resetu failedcounter lub zmiany jednostek systemd.

## Stan

**Wydanie5d5b82f zakończone; można wykonać jawne PonówAI użytkownika.**
Dokładny kod: `5d5b82ff34ac838a18229332cc27e3efa80553bf`,9plików źródeł/testów.
Pełny1070backend/325frontend/Ruff/mypy/ESLint/tscPASS,8deselected/10znanychostrzeżeń.
Końcowybuild/93E2E+1celowyskipPASS. Nie zmieniono testowanych źródeł (manifestPASS).
Pakietspójnychobrazów zawiera200plikówbackendu każdy, wszystkie zgodne zarchiwumGit.
Cała konfiguracja/hardening/sieci/wolumeny niezmienione poza obrazami aplikacji.
ExactbackendimageID/OCIrevision5d5b82f:8syntetycznychMockTransportprzypadków datPASS,
bez sieci/DB/AI/prywatnegopliku; terminalbezpiecznebłędy i nullable/leapdates potwierdzone.
Osobny syntheticHTTP4kodów400PASS. Pakiet nie wywołuje ponownie starego dokumentu.
Na pytanie o zgodę na dokładny5d5b82f użytkownik odpowiedział „potwierdzam”.
Świeża kontrola preapplyPASS: aktywne obrazy/metadane, HMAC całej konfiguracji,
wszystkie dane/schema/policy/originals i identyfikatory usług niezmienione względem
baseline; kolejki opróżnione. Zapisano zgodę exactSHA i uruchomiono apply tylko aplikacji.
Nie ponawiać apply; zakończono odczytową kontrolę po wdrożeniu.
Apply zakończone: dokładne spójneobrazy/HTTPS/assets/auth i invariantsdanych/policy/
schema/original/data-serviceIDsPASS poza4własnymi audytami401. Bez migracji lub policyop.
Końcowy browserread-only375/1440 i5minobserwacja10próbekPASS, bez błędów/mutacji.
Metadaneatomowo2026-11-02T18:34:03Z; świeżeHTTPS200 i dokładneimageIDs/OCIrevision
działających usług zgodne zactive-releasePASS. Dane/schema/policy/oryginały zachowane;
audyt zawiera wyłącznie dokładnie policzone własne odrzucenia401 smoke/przeglądarki.
Rollback45c8c2d zachowany. Brak automatycznego odczytu dokumentu przezAI.
Zweryfikowano aktualne bloby źródeł frontendu i hashe dist względem prawdziwego
dowodu build/E2E; dist bez zmian pomiędzy build i E2E. Nie powtarzać tej bramki.
Plan: `docs/superpowers/plans/2026-11-02-vision-date-validation.md`.
Prywatne, wyłącznie syntetyczne dowody: `/tmp/opencode/vision-date-fix-20261102/`.
Wszystkie bramki exactSHA/backend+worker+frontend, synthetic network-none adapter
smoke i legacy400smoke oraz exactSHAapproval zamknięte przedapply. Lokalny main
pozostaje1865d90, bez nowej zgody na merge/push; źródło5d5b82f w gałęzi sesji.
Bez migracji, policychange, backfillu, automatycznego retry lub importów.

## Decyzje

- Wykonanie inline zatwierdzonej małej poprawki, z niezależnym review zamiast kolejnego
  pytania o metodę; koszt: użytkownik mógłby preferować osobnych wykonawców per task.
- Wersje skonfigurowanego prompt/schema i policy pozostają niezmienione: doprecyzowano
  istniejącą semantykęISO ReviewFields, bez nowej zdolnościAI. Koszt: sama etykieta
  wersji nie rozróżnia kodu przed/po; dokładne GitSHA/obrazy są w metadanych wydania.
- Domknięcie manualnego retry starej rewizji jest niezbędne dla obecnego dokumentu;
  nie odtwarzamy jego danych ani nie ponawiamy wysyłki w imieniu użytkownika.
