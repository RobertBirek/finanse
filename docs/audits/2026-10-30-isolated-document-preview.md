# Izolowany podgląd dokumentów — 2026-10-30

Adres: **https://finanse-test.birek.online**. Status: gotowy do testów właściciela.
Nie jest to wdrożenie produkcji ani certyfikacja rzeczywistego telefonu.

## Zgoda i zakres

Użytkownik osobno zatwierdził podgląd na fikcyjnych danych, odrębne kontenery/bazę/
uploady/lokalny OCR oraz dodanie jednego hosta Caddy. Nie zatwierdził merge/deploy
produkcji, migracji jej bazy ani importu prawdziwych dokumentów.

- Źródła PR5: `6385f39debb8bbadf0caf1c95f67e09cb3ed0051`, wyeksportowane przez git archive.
- Prywatny bundle infrastruktury: `/docker/finanse-preview/`; brak sekretów w repo.
- Projekt Compose `finanse-doc-preview`: osobny PostgreSQL16/Redis7/backend/worker/
  frontend/Stirling. Nowe sieci internal, brak portów hosta i mountów produkcyjnych.
- Caddy jest jedynym wspólnym elementem. Dołączono go do nowego ingressu; wszystkie
  stare bloki Caddyfile zachowano bajtowo. Graceful reload, bez restartu kontenerów.
- Nowe testowe hasło i SECRET_KEY, produkcyjna polityka Secure/HttpOnly/SameSite cookies,
  host-only cookies i zaufany origin wyłącznie preview; rejestracja wyłączona.
- Backend/worker nie mają kluczy LLM ani dostępu TCP do Internetu. OCR trafia tylko
  do własnego Stirling; nie wysyła tekstów do dostawcy AI.
- W widoku stały napis „PODGLĄD · TYLKO DANE TESTOWE”, no-store i noindex.

## Dane i testy

Seed utworzył6 syntetycznych przykładów:100PLN do zapłaty,200PLN z częściową50PLN,
paragon35PLN deklarowany opłacony bez uzgodnienia,120PLN wobec estymaty100PLN,
20EUR wyłączone z prognozy PLN i75PLN bez terminu. Dane nie pochodzą z produkcji.

| Kontrola | Wynik |
|---|---|
| Własna migracja do7f8ce92bda94 i seed | PASS |
| Health wszystkich usług, brak restartów po ustaleniu konfiguracji | PASS |
| Nieautoryzowany odczyt, login, Secure/host-only cookies, CSRF, register404 | PASS |
| FiltrEUR, częściowa pozostałość, paragon bez fakeallocation, forecast | PASS |
| Faktyczny HTTPS upload PDF/JPEG/HEIF | PASS |
| Lokalne OCR trzech plików, tekst niepusty | PASS |
| OryginałSHA niezmieniony, prywatne no-store, JPEGpreview bezGPS | PASS |
| Review incomplete bez LLM i ręczne zatwierdzenie | PASS |
| Upload/OCR/approve nie zmienia ledger ani sald | PASS |
| Prawdziwa przeglądarkaHTTPS375/1440, EUR, oryginał/preview/review, focus/Escape | PASS |
| Kontenery produkcji: ID/start/restartcount i stary HTML/trasy bez zmian | PASS |
| Niezależny security/runtime review | PASS do testów właściciela |
| Aparat/galeria prawdziwego Android/iPhone | Wymaga testu użytkownika |

## Przebieg i ograniczenia

Bootstrap wymagał doprecyzowania cytowania tmpfs w YAML, prywatnego /pipeline0700
Stirling i PYTHONPATH dla one-shot seed. Dotyczyło wyłącznie nowego stacku.
Weryfikacja nagłówków uwzględnia dwa identyczne nosniff (aplikacja+proxy); niezależny
review ocenił to jako nieblokujący Minor. No-store i integralność plików potwierdzone.
Początkowe niepotwierdzone widokiEUR/review oraz zbyt wczesny check po loginie
w automatyzacji zostały rozstrzygnięte poprawnym oczekiwaniem na odpowiedź i nawigację.
Nie zmieniano w tym celu kodu aplikacji ani nie ignorowano rzeczywistego błędu.

Dowody i zrzuty: `/docker/finanse-preview/evidence/`, bez danych logowania w raporcie.
Hasło konta wyłącznie w prywatnym pliku0600 i przekazane właścicielowi poza Git.

## Test użytkownika i wyłączenie

Używać wyłącznie fikcyjnych zdjęć/dokumentów. Sprawdzić aparat i galerię, JPEG/HEIC,
pion/poziom, podgląd oryginału, czytelność OCR i duży/błędny plik. Pola review można
uzupełnić ręcznie — wyłączone AI jest celowe i nie oznacza błędu lokalnego OCR.

Podgląd jest tymczasowy. Po uzgodnieniu można uruchomić prywatny
`rollback_https.py`, który usuwa tylko jeden dokładnie zgodny własny fragment hosta,
zachowuje inne trasy i odłącza wyłącznie nowy ingress. `docker compose stop`
w katalogu preview zatrzyma jego usługi. Usuwanie volume/uploadów wymaga osobnej
decyzji; nie wykonywano `down -v`, prune ani usuwania danych użytkownika.
