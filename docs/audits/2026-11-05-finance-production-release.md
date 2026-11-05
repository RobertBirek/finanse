# Produkcyjne wydanie finansów 1–4B — 8121512

## Zgoda i zakres

Użytkownik jawnie potwierdził rewizję `8121512d1479ed101851f3617f970c7c132f40c2`,
aktualizację checkoutu serwera oraz wdrożenie gotowych etapów i aktywację serwerowego AI.
Zgoda nie usuwa indywidualnych zgód, ręcznego zatwierdzania ani zakazu przetwarzania historii.
Punktem wyjścia było rzeczywiste wydanie `8106532`, schema `2f4b2c2a527c`.

Udostępniany zakres:
- daty zakupu/księgowania, ręczne korekty i raporty;
- zatwierdzane zmiany kategorii i podziały płatności;
- 3A: reguły dla przyszłych wydatków, po wskazaniu kategorii technicznej i zatwierdzeniu reguł;
- 3B: propozycje AI, limity i ręczny przegląd; właściciel nadal musi wyrazić zgodę;
- 4A: ręczne produkty, rabaty, sklepy, wskazówki z historii i dwa oddzielne zatwierdzenia;
- 4B: odczyt jednego zdjęcia na żądanie, osobna zgoda eksportu i jawny import do nowego szkicu.

Nowe cele AI wykorzystują istniejącą konfigurację OpenAI / `gpt-6.1-terra`.
Doradca i dotychczasowy odczyt nagłówków pozostają bez zmiany modelu i kontraktu.
Nie tworzono zgód użytkowników, reguł lub kategorii ani nie uruchamiano historii.

## Dowody przed przełączeniem

- Zachowany gate tych samych źródeł: 1628 backend / 493 frontend, lint, typy, build,
  141 E2E + 1 oczekiwany skip. Weryfikator exact-source potwierdził zgodność commitów.
  Trzy obrazy wydania zbudowane bez sieci; offline import / endpoint / pojedynczy head PASS.
- Host `/opt/finanse` kontrolowanie fast-forward z `1865d90` do `8121512`.
  Zainstalowany restore drill po tej naprawie zna aktualną produkcyjną migrację.
- Pełny Compose dziedziczy aktywny overlay; porównanie zachowanych ustawień bezpieczeństwa,
  sieci i usług danych PASS. Jawny override wolumenów Stirling zapobiegł ponownemu
  dodaniu starego trainingData przez Compose extends. Stirling nie był odtwarzany.
- Faktyczny edge: Caddy. Backend tylko `finanse_internal`, bez publikowanego portu;
  frontend bez portów hosta, Caddy bez sieci backendu, domena kierowana do frontendu.
- Jedno niezależne review procedury i poprawki: fence także w nowym frontendzie,
  metadane przed otwarciem, drain po zatrzymaniu, audyt operatora i izolacja sieci.
  Testy operacyjne: 4 RED → 7 GREEN; dodatkowo semantyka markerów ARQ: 2 RED → 2 GREEN.

## Backup, drain i migracje

Publiczny frontend zwracał 503. Zatrzymano stary backend/worker; weryfikacja po zatrzymaniu
wykryła jedno pozostawione zadanie cron. Ograniczony drain starym runtime, bez planowania
nowych cronów, zakończył je prawidłowo. Nie kasowano kluczy Redis ani prac domenowych.
Pozostałe markery zakończonych cronów są deduplikacją ARQ, nie aktywną pracą; probe
potwierdza brak payloadu i wpisu kolejki, nie ignoruje aktywnych lub zwykłych zadań.

Po zerowych kolejkach i zadaniach wykonano świeży zaszyfrowany backup **`a4ca11f6`**.
Zainstalowany restore drill: checksumy dump/uploadów, odtworzenie w izolowanej bazie,
sześć migracji i invariant księgi PASS. Przed powtórzeniem trzeba było wyczyścić wyłącznie
przejściowy systemd start-limit po wcześniejszych błędach restore; konfiguracja i timer bez zmian.

Produkcyjne migracje wykonane jednym przejściem:

```text
2f4b2c2a527c → 84f28fe23ab8 → 2268bca97cb8 → c06315385b4e
→ 243aa1d9461c → a3ffcaf427aa → 7b57f2f0bde6
```

Zachowane wszystkie projekcje starych kolumn, liczności i hashe wierszy 32 istniejących tabel
oraz hashe oryginalnych uploadów. Brak backfillu, importu lub księgowania w ramach wydania.
Zachowane ID kontenerów PostgreSQL, Redis i Stirling oraz poprzednie obrazy aplikacji.

## Aktywacja

Spójne backend/worker/frontend mają exact SHA `8121512` i nie montują hostowego `/app`.
Serwerowe polityki 3B i 4B włączone atomowo, obie epoch 1, z fingerprintami konfiguracji.
Audyt ma aktora `operator-cli`, bez podszywania się pod użytkownika. Nie stworzono opt-in.
Dotychczasowa polityka nagłówków pozostaje epoch 4 z tym samym fingerprintem.

Limity 4B: obraz do 2048 px / 4 MiB / 4 194 304 pikseli, output 8192 tokeny,
response 256 KiB, timeout 60 s, współbieżność 1, 10 prób/osobę/dzień i 100 globalnie/dzień.
To limity wywołań/rozmiaru, nie gwarancja pieniężnego limitu kosztu. Retry po dispatch zabronione.
3B zachowuje limity aplikacji, w tym domyślne 5 prób/osobę/dzień.

## Kontrola działania — PASS, wydanie aktywne

Nowy frontend uruchomiono z blokadą 503 skopiowaną przed startem. Wyłącznie losowy
prywatny nagłówek operatora dopuszczał read-only smoke przez produkcyjne HTTPS;
bez dodatkowych portów i bez logowania lub mutacji użytkownika. Po smoke metadane
zapisano atomowo, a blokadę usunięto przez przywrócenie konfiguracji obrazu.

Pierwszy helper błędnie oczekiwał publicznego `/openapi.json`; nginx zgodnie z konfiguracją
zwraca tam SPA i proxy dotyczy tylko `/api`. Sprawdzenie kontraktu przeniesiono do
uruchomionego backendu; nie zmieniano routingu ani nie wystawiano nowego publicznego endpointu.
Końcowy odbiór PASS:
- trzy właściwe imageID i revisionlabels; read-only backend/worker, brak hostowego `/app`;
- produkcyjne HTTPS/health200 i assets zgodne bajtowo z zaakceptowanym dist;
- pięć chronionych endpointów odrzuca anonimowego użytkownika401;
- read-only browser375/1440: login, brak overflow/pageerrors/obcego ruchu lub mutacji,
  chronione ścieżki kierują do logowania;
- oba nowe cele serwerowego AI epoch1 z właściwą konfiguracją; opt-in i nowe zadania0
  w chwili odbioru przed publicznym otwarciem; trzy audyty operatora bez userID;
- nagłówki vision nadal epoch4/ten sam fingerprint, oryginały i usługi danych bez zmian;
- po otwarciu publiczne HTTPS200/auth401, trzy obrazy i zero restartów, zero błędów
  w logach, produkcyjny invariant księgi bez naruszeń, schema7b57;
- atomowe aktywne metadane mają `release_status=verified-active`.

Pierwsza obserwacja publiczna: 2026-11-05 18:36:01 UTC. Nie traktować smoke bez logowania
jako dowodu wykonania prywatnego odczytu lub zatwierdzenia finansowego na produkcji.
Powtórna obserwacja po aktualizacji dokumentacji również PASS; dowody i skrypty operacyjne
zachowano prywatnie w `finance-operations-evidence/` katalogu wydania, z manifestem SHA256.
Usunięto roboczą kopię zmiennych z sekretami i losowy nagłówek smoke; konfiguracja nginx
wróciła do domyślnej z obrazu. Nie istnieje trwały bypass ani dodatkowy port diagnostyczny.
Etykieta `4B LOCAL/OFF` wypisywana przez stary verifier odbioru lokalnego opisuje dawny
gate źródeł, nie stan produkcyjny. Aktualne polityki i active-release potwierdzają ACTIVE.

## Odzyskiwanie i granice odbioru

Pakiet i evidence: `/opt/finanse/webapp/releases/8121512/`, robocze dowody prywatne
`/tmp/opencode/finance-all-release-20261105/`. Aktywny override:
`/opt/finanse/webapp/releases/8121512/compose.active.yaml` — zawsze z bazowym i prod Compose.

Rollback nie może usuwać nowych kategorii, zatwierdzeń, archiwum ani dowodów odczytów.
Zachowano wcześniejszy kontrakt STOP: fence, wyłączenie nowego admission, zachowanie schematu
`7b57` i dowodów, naprawa naprzód; stary runtime wyłącznie po udowodnieniu kompatybilności.
Nie ma automatycznego downgrade, restore produkcji, DELETE ani odrzucania nowych danych.

Podjęte decyzje operacyjne: pozostawić STOP zamiast niebezpiecznego automatycznego cofnięcia
(koszt awarii: maintenance i naprawa naprzód); pozwolić na prywatny nagłówek tylko do smoke
przy publicznym 503 (koszt błędu procedury: przedwczesne udostępnienie, ograniczony testami
i usunięciem blokady przed końcem). Nie odłożono uwag minor z review.

Ten odbiór nie obejmuje ponownego płatnego testu modelu, eksportu prywatnego zdjęcia,
mutacji finansowej użytkownika ani oceny jakości realnych paragonów. Prywatny pilot nadal
wymaga odpowiedniego zdjęcia; poprzednia faktura nie jest jego zamiennikiem.
