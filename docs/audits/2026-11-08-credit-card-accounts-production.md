# Typ konta karty i przegląd wielu kart — wydanie produkcyjne

Status: **wdrożone i zweryfikowane**.

## Zgoda i zakres

Użytkownik: „scal, wypchnij do main i wdróż”, następnie „Tak, migracja i wdrożenie”
dla rewizji `7801ba591223c213c1fcd69a0c3ace19c81ef9db`, migracji
`00a9ccb532b9 → 739144d5eaef`, maintenance, backup/odtworzenia i trzech usług.
Osobne „Tak, tylko ten rollback” zatwierdza w razie awarii wyłącznie odwrotną
klasyfikację `739144d5eaef → 00a9ccb532b9` przed uruchomieniem starych obrazów.

Migracja rozpoznaje konta tylko po istniejącym profilu tego samego właściciela,
nie po nazwie. Nie tworzy profilu Velo, nie zmienia sald, transakcji, warunków,
wyciągów lub rat. Wykluczone importy, próbne zapisy użytkownika i sesje w jego imieniu.

## Przygotowanie i odebrany artefakt

- FF i push `main`: `775e875 → 7801ba5`, potwierdzone zdalnie, bez force.
- Dokładne źródła odebrane lokalnie: **1863 backend, 568 frontend, 165 E2E +1
  oczekiwany skip**; manifesty i JUnit zgodne, niezależny review produktu bez uwag.
- Świeżo po scaleniu: **952 backend unit, 568 frontend**, Ruff/mypy/ESLint/tsc/build
  PASS. Pełnych integracji nie uruchamiano na produkcji lub wcześniejszych bazach.
- Publiczne bajty świeżego buildu identyczne z artefaktem odebranym w E2E.
- Pakiet `/opt/finanse/webapp/releases/7801ba5/` przez `prepare_release.py`, trzy
  obrazy zbudowane offline. Weryfikator gotowych image IDs z rzeczywistymi non-root
  UID:GID finalnego Compose i odczyt assetów jako nginx PASS.
- Cały inherited base+prod+active zachowuje env, users, zasoby, sieci i mounty poza
  image/build; brak host mountu `/app`. Stare obrazy i override020c229 zachowane.

## Próby backupu, migracji i rollbacku

Świeży szyfrowany backup przez istniejący serwis odtworzono do wyłącznie własnej
bazy loopback `card_accounts_7801ba5_rehearsal_restore`. Checksumy dump/uploads,
stary schemat i księga PASS. Próba UP/DOWN/UP zachowuje wiersze wszystkich **62
tabel** poza zamierzoną klasyfikacją kont. Stary runtime po dokładnym downgrade
czyta konta/kategorie poprawnie; nowy zbiorczy odczyt odpowiada istniejącym pozycjom.
Próbny snapshot miał zero skonfigurowanych profili — nie tworzono żadnego na potrzeby
smoke testu. Próbę powtórzono na świeżym backupie już po fence i zatrzymaniu aplikacji,
w drugiej własnej bazie `card_accounts_7801ba5_fenced_restore`: UP/DOWN/UP PASS,
pełne dane i uploads zgodne z zamrożonym źródłem produkcji przed APPLY.

Retencja używa SHA-256 serializacji JSON uporządkowanych wierszy. Tylko `credit_card`
jest normalizowane do `credit` na potrzeby hasha; niezależne porównanie pełnej mapy
ID→typ sprawdza dokładnie dozwolony kierunek migracji i zbiór kont z profilami.
Kolumny oraz pozostałe dane, w tym profile i księga, pozostają identyczne.

## Review procedury awaryjnej

Read-only review `ses_e4519269cffesp87sxuZ4CeZTD` wskazał dwa Important, naprawione
przed maintenance:

1. Zatrzymany lub brakujący frontend musi zostać utworzony/uruchomiony z konfiguracją
   maintenance i publicznym503 przed downgrade, zamiast pomijania fence.
2. Przed rollbackiem ponownie renderowany Compose musi odpowiadać zamrożonemu
   kandydatowi. Kontener wykonujący downgrade ma deterministyczną nazwę, pozostaje
   po wykonaniu i jest sprawdzany: exact image ID, user, tag, env, mounty, exit0,
   stopped. Nie używamy automatycznego `--rm` dla tej operacji.

Cztery izolowane testy operatorowych zabezpieczeń **RED→GREEN**, bez Dockera,
HTTP lub bazy: zatrzymany frontend, przypięcie i inspekcja kontenera, odrzucenie
niewłaściwego obrazu i roota. Refrozen manifest wszystkich krytycznych artefaktów;
niepełny manifest odrzucony, fenced backup bez potwierdzonego zatrzymania odrzucony
przed działaniem. Reviewer nie wykonywał testów/runtime; te dowody sprawdza operator.

## Procedura przełączenia i granice

Przełączenie zakończone: pojedynczy produkcyjny UP do739144d5eaef, zachowane62tabele
oraz dokładne porównanie dozwolonej mapy typów kont. Nowe trzy usługi za maintenance
przeszły health, odczyt zbiorczy, retencję i kontrolę exactimages/env/users/mounts/sieci;
usługi danych bez zmian. Po otwarciu publiczne HTTPS health/login200,
anonimowe nowe summary/accounts/card401, assety identyczne z odebranym pakietem.
Zamrożona produkcja również nie miała profili kart: migracja przeklasyfikowała
**zero kont** i zachowała wszystkie istniejące wiersze. Schemat jest gotowy, ale Velo
trzeba świadomie skonfigurować przez edycję istniejącego konta — nie utworzono profilu
w ramach wdrożenia i nie dopasowywano konta po nazwie.

Końcowy GET-only browser375/1440 PASS: login, ochrona listy/szczegółów/edycji/starych
linków, fonty, brak overflow/błędów JS/mutacji/obcego ruchu. Oba screenshoty obejrzane.
Nie tworzono sesji, więc nie jest to autoryzowany test zapisu na danych użytkownika;
ten przepływ ma osobne lokalne E2E i integracje.

Obserwacja **316 sekund, 31 kontroli** PASS: health200 (maksymalnie134ms), właściwe
trzy obrazy, zero restartów i błędów w nowych logach, schema739144d5eaef,
ledger0naruszeń, Redisready. PostgreSQL/Redis/Stirling zachowały IDs, obrazy, czasy
startu i restart counts. Rollback produkcyjny nie był potrzebny.

Po komplecie bramek atomowo zapisano metadane `verified-live` i trwałe prywatne
dowody. Usunięto wyłącznie dwa własne restoreDB po porównaniu zapisanych nazw/OID
i braku połączeń; potwierdzono brak po cleanup. Bez force lub zmiany innych baz.

503 → bezczynność i łagodne zatrzymanie starych backend/worker → zamrożony odczyt
→ nowy backup/odtworzenie porównane ze źródłem i uploads → próba UP/DOWN/UP
→ jednokrotny produkcyjny UP → retencja i zbiorczy odczyt → nowe trzy usługi
za maintenance → kontrole wewnętrzne → otwarcie → publiczne auth/assets/browser
→ pięciominutowa obserwacja → metadane i trwałe dowody → cleanup wyłącznie własnych
restoreDB po kontroli nazwy/OID/braku połączeń.

W razie problemu: fence, zatrzymanie aplikacji, aktualny snapshot, tylko zatwierdzony
downgrade klasyfikacji, sprawdzenie zachowania bieżących danych, stare obrazy,
weryfikacja przed otwarciem. Nigdy wcześniejszy downgrade lub odtworzenie produkcji.
Nieudana kontrola rollbacku pozostawia maintenance i wymaga decyzji operatora.

Prywatne dowody: `/tmp/opencode/card-account-release-7801ba5/` i trwała kopia
w `/opt/finanse/webapp/releases/7801ba5/evidence/`, z manifestem SHA-256,
handoff, proofami backupów/migracji/retencji/nonrootimport/browser/observation/cleanup.
Pliki env sond nie są archiwizowane. Metadane wskazują dokładny zatwierdzony rollback.
Dwa wcześniejsze robocze raporty Velo/Q7 pozostają nietknięte i poza commitem.
