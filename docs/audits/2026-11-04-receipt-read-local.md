# Odczyt pozycji paragonu 4B — odbiór lokalny

Status: odebrane lokalnie, cel AI nadal OFF (2026-11-05).
Plan4a41000 zatwierdzony przez użytkownika kolejnym „tak”.

## Końcowy dowód

**1628 backend + 493 frontend + lint/typecheck + świeży build + 141 E2E PASS.**
Backend:8deselected według istniejącej konfiguracji, zero skipów bazy. Browser:1 oczekiwany
skip desktopowego wariantu testu mobilnej agendy. Żadnych nieznanych wyjątków testów.

`verify-final.py verify/commits` potwierdził te same bajty źródeł przed/po gate i w HEAD,
skróty wszystkich plików dist i assets z index.html oraz niezmienną migrację/proof.
Backend `f9fe4c87b54066093a23826348bdc212e9e3cf7a`, frontend
`527e92a0637735af965cecf6ff19045ecf52c3f2`. Komity dopiero po pełnym gate, bez push.
Dowody: `/tmp/opencode/receipt-read-20261104/final-proof.json`, `final/`, `build-proof.json`,
`e2e-final.log`, `migration-proof.json`, `review-result.md`. Nie powtarzać niezmienionego
godzinnego gate albo seedów migracji przy aktualizacji samych dokumentów.

## Granice

- Jeden wybrany, już dołączony JPEG/PNG/HEIF, odczyt wyłącznie na żądanie.
- Osobny cel/polityka domyślnie OFF. Cały znormalizowany obraz może zawierać dane
  osobowe i nagłówek. Dodatkowy płatny call względem odczytu nagłówka, `store=false`.
- Trwały dispatch marker i rezerwacja przed HTTP. Po nim unknown nie daje prawa
  automatycznego ponowienia ani zwrotu limitu. Nie obiecujemy provider exactly-once.
- Anulowanie tylko przed dispatch. Ponowny odczyt to nowa zgoda i możliwy kolejny koszt.
- Import tylko do nowego szkicu4A. Sklep i kategorie wybiera człowiek; zatwierdzenie
  pozycji oraz podziału istniejącej płatności nadal osobno. Model nie zmienia ledgeru.
- Bez PDF/multipage/batch, liveAPI, prywatnych zdjęć, produkcji, aktywacji, merge i push.

## Zebrane dowody przed końcowym gate

Guardowane testy korzystają wyłącznie z loopback `finanse_test`; provider keys wyczyszczone.
Transport testowy HTTP i syntetyczne obrazy, bez zewnętrznych wywołań.

- Foundation21, adapter+regresje112, admission39, worker+regresje65,
  import+regresje50 PASS; najnowsze42 dla importu/races/policy PASS.
- Frontend489 testów, lint/types PASS. Browser14/14 desktop1440/mobile375,
  flow8000/2000/rabat1000→7200/1800, osobne zgody, unknown/replay, cancelrace,
  partial review, Axe i brak overflow PASS.
- Migracja7b57f2f0bde6 tylko w schemacie `receipt_read_stage4b_test`, dokładnie siedem
  nowych tabel, bez backfillu. Stare dane/kolumny/indeksy/headerjobs/4A/origins/alokacje/
  receipts zachowane; emptyrollback/reupgrade i populatedrefusal PASS. SHA:
  `45bb5d20d7beb3527cdbf3d5560916b1650e44159f5cf35b8a6a065b0247720b`.
- Jeden niezależny review aktualnych tracked+untracked źródeł zakończony:
  Critical0/Important1/Minor0/Declined0. Important: niepewny start/import znikał po
  reload/unmount. Dwa testy remount RED→GREEN; poprawka przechowuje wyłącznie
  metadata intencji w sessionStorage, przed POST, scope owner/bill/karta. Po nowym
  session/owner klucz znika; przy pierwszym bootstrap tego samego ownera po reload
  odtwarzany jest tylko klucz/body, bez automatycznego POST. Brak pamięci blokuje
  nowe polecenie. Możliwe jawne porzucenie; kanoniczny odczyt po replay bez instalacji
  starej odpowiedzi do formularza. Żadnych obrazów/tekstów paragonów w sessionStorage.
- Świeży finalny build/exactsource/assets i pełny browser: **141 PASS + 1 oczekiwany
  desktop skip testu mobilnej agendy**, także full-page reload niepewnego startu.
  Pełny backend/frontend/static gate na tych samych zamrożonych plikach zakończony PASS;
  produktcommity zapisano dopiero po odczytaniu tego wyniku.

## Decyzje wykonawcze

1. Acykliczne wspólne kontrakty dowodu w `finance/receipt_read_contracts.py`, re-export
   w Documents. Koszt pomyłki: dodatkowy moduł; wire fields bez zmiany.
2. Nowe wiersze stream/job z FK do bill dopiero po Financegates; istniejące stream/job
   zablokowane przed nimi. Zapobiega ukrytemu KEY SHARE→allocation cycle.
   Koszt pomyłki: dodatkowe odczyty pod globalnym admission.
3. ResultDTO dodatkowo zwraca ownerowi zapisany bounded immutable payload, potrzebny
   do printed_total i tekstu źródłowego; maps przechowują source_text/basis/kind.
   Koszt pomyłki: addytywne pola odpowiedzi, bez nowego eksportu/uprawnień.
4. Review pakiet używa workingtree scope, bo plan odkłada commity do pełnego gate
   i native helper odrzuca pusty BASE..HEAD. Koszt pomyłki: jawna inspekcja nowych
   plików zamiast samego diffu commitów; finalny manifest nadal obejmie wszystkie.

Review `ses_e5583dc59ffeXrFOCGtD1DE5Ir`; jeden fixpass, bez re-review. Brak declined
behaviors i deferred minors. Ważny finding o utracie intencji po reload zamknięty testami
RED→GREEN, pełnym493frontend i browserreload375/1440; cały gate zielony.

## Przekazanie

Gałąź/worktree i zastane Velo/Q7 dirty zachowane. Brak zmian produkcji lub aktywacji;
konfiguracja celu domyślnie OFF, osobna od nagłówków i doradcy. Pierwsze rzeczywiste API,
ewentualny deploy/aktywacja/merge/push oraz prywatne zdjęcie wymagają osobnej zgody.
Testy syntetyczne nie są potwierdzeniem jakości odczytu prawdziwego paragonu. PDF/multipage,
automatyczny wspólny upload nagłówek+produkty, historia batch i etap5 pozostają poza zakresem.
