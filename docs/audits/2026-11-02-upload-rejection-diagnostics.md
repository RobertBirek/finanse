# Diagnostyka odrzucenia uploadu z iPhone — 2026-11-02

## Zakres i zgoda

Użytkownik zatwierdził wdrożenie małej poprawki diagnostycznej po błędzie uploadu
HEIF z biblioteki iPhone. Nie rozstrzygnięto jeszcze, co Safari rzeczywiście wysyła.
Nie jest to deklaracja naprawienia uploadu ani zgoda na osłabienie walidacji.

## Diagnoza przed zmianą

- OdrzuconePOSTupload400 są przed wywołaniem AI; body67B odpowiada bezpiecznej
  odmowie walidatora, nie błędowi multipart/rozmiaru lub braku sesji.
- Oryginał udostępniony przez użytkownika: HEIF3024x4032/3675697B, ograniczonyparser
  na dokładnym runtime84c9c27 (takżeUID10001/networknone) PASS dla MIMEheif/heic/octet.
  Plik pozostał niezmieniony i nie został przekazany doAPIAI, OCR lub bazyaplikacji.
- SyntetyczneJPEG iHEIF12MP, również szumowy3,6MB, takżePASS. Limity20MiB/25MP
  nie są przekroczone; nie należy ich podnosić jako pozornej naprawy.

## Poprawka

- JSON400 zawiera zamknięty kod: document_mime_unsupported, document_empty,
  document_validation_failed lub document_mime_mismatch.
- UI tłumaczy wyłącznie te kody; nie wyświetla dowolnego serverdetail. Nieznanykod
  zachowuje ogólny komunikat, dotychczasowe413/503/507 bez zmiany.
- Log odrzucenia zawiera tylko kod, deklarowane/rozpoznaneMIME z zamkniętego
  mapowania oraz liczbę odczytanychbajtów. Nie zawiera nazw/treści/id/hashów/EXIF,
  surowegoMIME lub tekstu wyjątkuparsera.
- Nie zmieniono dopuszczanychplików, rozmiarów, limitówparsera, dekoderów, finansów,
  autoryzacji, dostawcyAI, politykvision lub modeludanych. Bez migracji/backfillu.

## Dowody i stan

**Stan: diagnostyka9369b5d wdrożona i sfinalizowana; oczekuje na próbę użytkownika.**

- TDD: zapisaneRED/GREEN początkowego wykonawcy. Po limicieużycia koordynator
  zachował zmianę i uzupełnił rozróżnienie malformedparser→validation_failed,
  testRED→GREEN. Focusedbackend59PASS, Ruff/mypyPASS.
- Pełny gate: **1036 backend PASS, 8 deselected, 10 znanych ostrzeżeń;316frontendPASS**,
  Ruff/mypy/ESLint/tsc PASS. Dokładny commit `9369b5dc3019bd8cf623fc69f0b629968a991803`.
- Niezależny przegląd źródeł: PASS, bezCritical/Important. Minor: bezpośredni test
  pustego/nieobsługiwanego MIME w logu serwera można rozszerzyć; przed apply kontrola
  dokładnegoobrazu ćwiczy wszystkie4kodyHTTP na syntetykach bezDB/AI.
- Frontend build i93E2E+1celowyskip PASS; utrwalono bloby źródeł i hashe rzeczywistego
  dist bezpośrednio po build, potwierdzono niezmienność po E2E. Przed pakowaniem
  muszą być identyczne z dokładnym commitem kandydata.
- Backup c3935c47 iinstalledrestore success/0. Początkowo zadziałał limit systemd
 3starty/3h po wcześniejszychudanychdrill; wyczyszczono wyłącznie failedcounter
  tej jednostki, po potwierdzeniu pustego parentdir, potem rzeczywiście odtworzono.
- Procedura wymaga candidateHEAD/gate/reviewtegosamegoSHA i blobówźródła frontendu,
  sumdist bezpośredniopobuild i niezmienionych poE2E. Render konfigurowany porównywany
  w pamięci, utrwalany wyłącznie jakoHMACcałości, nie wartości środowiska.
- Scoped operacyjny odbiór warunkowoApproved; warunek nowego dowodu niezmienionego
  dist faktycznie zamknięty, bloby źródeł w9369b5d identyczne z tymi z build/E2E.
- Rollback to dokładne sprawdzoneobrazy84c9c27 z niezmienioną aktywnąpolitykąvision;
  przedwydaniem zgodnośćżywychobrazów i metadanych, po awariihealth/images/data/policy.
- Gotowy pakiet zachowuje identyczny environment/hardening/networks/volumes; runtime
  dependencies bez zmian. Oba obrazy backendowe zawierają dokładnie199plików zarchiveGit.
- TestHTTP na dokładnymobrazie, networknone/UID10001: wszystkie4kody400PASS,
  brak połączeń doDB/AI i brak użycia prywatnego pliku. Log zawiera wyłącznie kody,
  MIMEbucket i bytes. Przełączenie uruchomione dopiero po zamknięciu wszystkichproof.
- Produkcyjne przełączenie backend/worker/frontend9369b5d PASS; HTTPS/login/health,
 4API401 i hashystaticassets zgodne. Starewiersze/politykavision/originals/usługi
  danych bez zmian poza dokładnie4własnymi securityauditod401. Nie uruchomiono
  migracji, disable/enablevision lub odczytu prywatnejfakturyAI.
- Końcowy browser375/1440 PASS, brak błędów/overflow/mutacji. Obserwacja10próbek
  PASS; active-release atomowo zapisany 2026-11-02T12:34:58Z. Świeża kontrola HTTPS200
  i zgodności działających obrazów z metadanymi PASS. Nie ponawiać wdrożenia.
- Lokalny hostmain FF9369b5d, bez push. Nadal potrzebny rzeczywisty wynik uploadu
  z iPhone; nie uznano samego wdrożenia diagnostyki za naprawę przyczyny błędu.

Dowody prywatne: `/tmp/opencode/iphone-upload-fix-20261102/`.
Oryginał wyłącznie w oddzielnym prywatnym katalogu diagnozy, nie w repo ani pakiecie.

## Dalszy krok po wydaniu

Poprosić o jedną próbę z biblioteki iPhone. Nowy komunikat i bezpiecznylog pozwolą
rozróżnić niedopuszczony MIME, zawartość nierozpoznaną przezparser i MIMEmismatch.
Nie twierdzić, że konkretna faktura jest już przyjmowana bez rzeczywistego wyniku.

## Rozstrzygnięcia koordynatora

- Dokończenie inline po limicie wykonawcy, z zachowaniemRED/GREEN i niezależnego
  odbioru; kosztpomyłki: dodatkowy kontekst po stronie koordynatora.
- HMAC całegorenderu zamiast listy pólsekretnych; koszt: mniej czytelny artefakt,
  lecz żadna nieznana zmienna lub poleCompose nie może ujawnić sekretu.
