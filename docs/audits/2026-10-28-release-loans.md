# Wydanie walut kont i harmonogramów kredytu — 2026-10-28

## Zgoda i kod

- Użytkownik jawnie zatwierdził pełne testy, main/push i produkcję.
- Kod: `9db255be06ce83a70572332ad42d130126d4f128`, scalony fast-forward i wypchnięty
  do main bez force. Zawiera także wcześniejszy slice walut `0d52f9d`.
- Migracja schematu: `b8e4c2f1a7d9` → `c2d7e9a4f801`, wyłącznie trzy nowe tabele.
- Brak importu harmonogramu Q7, księgowania historycznych odsetek, korekt Velo
  i zmian oryginalnych dokumentów. Powiązanie przelewu jest metadanymi, nie rozksięgowaniem.

## Gate

- Backend844 PASS,8 proxy deselected,2 znane warningi bibliotek (596,88s).
- Osobno proxy/kontenery5 PASS; Ruff/mypy68 PASS.
- Frontend243 unit,59 E2E PASS+1 celowy skip desktop; lint/types/build PASS.
- Pierwszy pełny backend gate841 PASS/1 FAIL zatrzymał wydanie. Regresję serializacji
  PATCH naprawiono przez eager-load postingów;2 nowe regresje RED→GREEN i pełny
  ponowiony zielony gate. Nie opublikowano czerwonego kodu.
- Niezależne review kodu, blokad i procedury rollout bez ważnych blokad.
- CI dokładnej rewizji: `https://github.com/RobertBirek/finanse/actions/runs/40644862567`
  — **success**, oba wymagane zadania, również proxy/kontenery i przeglądarka.

## Backup i zachowanie zastanego stanu

- Świeży szyfrowany snapshot **6ebdef50**, backup i izolowany restore: success/0.
- Zastane dokumenty Velo zachowano w wydaniu i w dodatkowym stash
  `pre-loans-release-velo-docs-20261028`; nie przywracać go ponownie ani nie usuwać.
- Prywatny `/opt/finanse/webapp/` nie został dodany do Git.
- Dotychczasowe obrazy i pełny aktywny override pozostają rollbackiem aplikacji.
  Rollback nie usuwa addytywnych tabel i nie wykonuje restore/downgrade produkcji.

## Pakiet i przełączenie

- Pakiet wersjonowany przygotowany przez `ops/prepare_release.py`, z archiwum Git
  dokładnego SHA i builda main; obrazy offline, bez zmian zależności runtime.
- Pakiet `/opt/finanse/webapp/releases/9db255b` gotowy. Porównanie renderu zmienia
  wyłącznie image/build aplikacji; env/hardening/sieci/usługi danych bez zmian.
  Non-root network-none startup oraz hashe kodu i assetów we wszystkich obrazach PASS.
- Próba migracji na świeżej kopii produkcyjnego dumpa w tmpfs/network-none PASS:
  wszystkie stare kolumny i invariant księgi zachowane, nowe tabele puste.
  Pierwszy start próby trafił w restart tymczasowego serwera initdb; readiness
  zmieniono z gniazda Unix na końcowy TCP loopback. Ponowienie PASS, bez zmian produkcji.
  Tymczasowy kontener, dump i jego env usunięte po próbie.
- Przed przełączeniem: kontrola środowiska/hardeningu, non-root startup, próba migracji
  na świeżej izolowanej kopii danych i fingerprinty wszystkich starych kolumn.
- Po przełączeniu zweryfikowano HTTPS/assets/auth, przeglądarkę375/1440 bez zapisu,
  niezmienność ledger/original uploads i usług danych oraz obserwację.
- Dowody prywatne: `/tmp/opencode/release-loans-20261028/`.

## Wynik przełączenia

- Dokładny pakiet frontendowy: dodatkowe59 E2E PASS+1 celowy skip.
- Migracja produkcyjna do c2 zakończona przed wymianą aplikacji. Pełny Compose
  base+prod+previous-active+release zmienił wyłącznie backend/worker/frontend.
- HTTPS `/api/health`, `/login`, publiczne hashe assetów i odrzucenie anonimowego
  API (także nowych loans) PASS. Przeglądarka375/1440: login/fonty/przekierowania
  chronionych tras, zero JS errors i mutujących żądań.
- Trzy aplikacje mają właściwe image ID/revision, zero restartów i brak host mountu
  `/app`. Kontenery i czasy startu PostgreSQL/Redis/Stirling/Actual bez zmian.
- Wszystkie stare kolumny tabel finansowych/dokumentów/ustawień/mapowań i oryginały
  uploads identyczne z baseline. Nowe trzy tabele pozostają puste, ledger bez naruszeń.
- Nie wykonywano rzeczywistych operacji użytkownika: to smoke wdrożenia,
  nie ocena zalogowanej produkcji. Harmonogram Q7 nie został zaimportowany.
- Pięciominutowa obserwacja **10/10 PASS**: właściwe obrazy, zero restartów i nowych
  ERROR/CRITICAL/Traceback, stare dane/originals i usługi danych nadal niezmienione.
- Metadane `active-release.json` zaktualizowane atomowo dopiero po sukcesie;
  skonsolidowany `compose.active.yaml` odtwarza dokładnie zastosowaną konfigurację.
  Końcowa ponowna weryfikacja PASS, tymczasowe kopie env sekretów usunięte.
- Rollback aplikacji: `/opt/finanse/webapp/releases/9db255b/rollback.sh`, pełny
  poprzedni override e5 z zachowaniem starych obrazów. Nie był potrzebny; nie
  wykonuje downgrade, restore ani usuwania tabel/danych.
- Dokumentacyjny commit po wydaniu nie zmienia kodu aplikacji ani obrazów.
