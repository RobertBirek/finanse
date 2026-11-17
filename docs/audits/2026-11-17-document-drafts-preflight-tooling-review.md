# Osobny przegląd narzędzi preflight przed wdrożeniem szkiców

Data: 2026-11-17. **Wdrożenie zatrzymane; nie zmieniono produkcji.**

## Zakres i zgoda

Użytkownik polecił przejrzeć trzy pliki blokujące preflight i ustalić zgodną
ścieżkę dalszego działania. To nie jest zgoda na pominięcie wyniku `blocked`.

Porównanie źródeł:

- aktywna rewizja `45bcf8812ded8696624ead6dd65d2a0c5f80710a`;
- kandydat `5c372467b3f5af712ea2cd7055b1b99836387031`;
- `.opencode/command/deploy.md`;
- `ops/release_preflight.py`;
- `ops/release_preflight_policy.py`.

Diff trzech plików:854dodane linie. Lokalna treść każdego pliku odpowiada
dokładnie kandydatowi w Git; zapisano SHA256 źródeł. Nie zmieniano tych plików.

## Dowody

- Natywny preflight dla zatwierdzonego inventory: exit2,
  `unknown_change_scope`, przed Docker/DB. Spośród72zmienionych ścieżek
  nieobsługiwane są dokładnie trzy pliki wskazane powyżej.
- Świeży test offline w izolacji sieciowej: **91PASS** w39.44s.
  Uruchomiono `test_release_preflight_policy.py` i `test_release_preflight.py`.
  Adapter jest testowany przez syntetyczne repozytoria Git i atrapę Docker,
  bez rzeczywistych kontenerów lub danych użytkownika.
- Dowody prywatne: `/tmp/opencode/document-drafts-preflight-bct7kdzz/`:
  `preflight.json`, `unsupported-source-paths.json`,
  `offline-preflight-tests.log`, `review-source-binding.json`.

## Status przeglądu

- [x] Przypięcie zakresu i zgodności źródeł.
- [x] Świeże testy syntetyczne adaptera i polityki.
- [x] Odbiór osobnego readonly review trzech plików:0Critical,3Important.
- [x] Zweryfikowanie uwag w kodzie i syntetycznych próbach negatywnych.
- [ ] Osobne uzgodnienie naprawy i obsługi zakresu tooling; review nie odblokowuje CLI.

## Ustalenia review i weryfikacja

Werdykt: **changes requested; nie zatwierdzono użycia w rzeczywistym środowisku.**

1. `ops/release_preflight.py:209-218`: odziedziczony PATH pozwala podstawić
   wykonywalny Git/Docker. Syntetyczna próba faktycznie uruchomiła podstawiony Git.
2. `ops/release_preflight.py:266-272,494-503`: Compose/env są hashowane, a potem
   ponownie otwierane przez narzędzie po ścieżce. Próba zmieniła syntetyczny env
   po kontroli hasha; natywny CLI nadal zwrócił no_rollout zamiast blocked.
3. `ops/release_preflight.py:153-162,464-479`: komenda psql nie przypina endpointu
   libpq i nie izoluje pozostałych zmiennych PG. CLI zaakceptował syntetyczny
   PGHOST/PGPORT/PGSERVICE. To dowód braku kontroli, nie rzeczywistego połączenia
   z inną bazą; nie wykonywano zapytań do prawdziwego PostgreSQL.

Wszystkie trzy negatywne oczekiwania blokady zakończyły się RED:3FAIL w2.29s,
wyłącznie w izolowanej sieci, na syntetycznych plikach/Git i atrapie Docker.
Dowody: `test_review_proofs.py` i `review-negative-proofs.log` przy raporcie
preflightu. Nie jest to zielony test naprawy; kodu narzędzia nie zmieniono.

Przejście91istniejących testów nie pokrywało tych trzech przypadków. Wynik
review nie jest sprzeczny z zielonym CI aplikacji ani nie zastępuje odbioru runtime.

## Granice i dalsza ścieżka

- `unknown_change_scope` dla nowych modułów/komendy jest zamierzoną blokadą V1,
  odrębną od trzech powyższych usterek. Sam review nie zmienia jej na sukces.
- Nie istnieje wspierana obecnie ścieżka uzyskania exit0 dla tego kandydata
  przez samo zatwierdzenie review. Nie wolno filtrować diffu, podmieniać rewizji,
  edytować metadanych lub dodawać bezwarunkowej whitelisty, by wymusić zielony wynik.
- Potrzebne jest osobne uzgodnienie projektu obsługi zatwierdzonych zmian tooling
  i granicy zaufania narzędzia, wraz z naprawą trzech usterek, testami i odbiorem.
  Nie rozpoczęto implementacji takiej zmiany ani nie uznano obecnego review
  za upoważnienie do rollout.
- Poza zakresem tego review: pełna funkcja szkiców, gotowość produkcyjna,
  rzeczywista konfiguracja/libpq oraz nowe rozwiązanie onboardingowe.
  Nie wyciągano wniosków o ich poprawności.

Nie filtrowano diffu, nie przepisywano rewizji, nie nadpisano inventory/metadanych,
nie osłabiono polityki i nie uruchomiono kolejnego rollout.
