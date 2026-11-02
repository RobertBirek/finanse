# Automatic Document Vision Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Automatycznie odczytywać nowe zdjęcia faktur/paragonów bezpośrednio przez skonfigurowany model wizyjny i przedstawiać propozycję do ręcznego zatwierdzenia, bez automatycznego księgowania.

**Architecture:** Rozszerzamy istniejącą domenę documents, nie tworzymy autonomicznego agenta. PostgreSQL przechowuje metodę uploadu, rewizje, trwałe zadania i limity; worker wysyła pozbawioną metadanych pochodną obrazu bez zależności od OCR. Obecne review/bills obsługują zatwierdzanie, a PDF i starsze dokumenty pozostają na ścieżce legacy.

**Tech Stack:** Python3.12+, FastAPI, SQLAlchemy2 async, PostgreSQL16, Alembic, ARQ/Redis, Pillow/pillow-heif w ograniczonym procesie, obecne OpenAI SDK/httpx, React18/TypeScript/TanStack Query, pytest/Vitest/Playwright.

**Spec:** `docs/superpowers/specs/2026-10-30-automatic-document-vision-design.md` — pełny zakres zatwierdzony przez użytkownika przed przygotowaniem tego planu.

## Global Constraints

- „Aktywne vision zastępuje automatyczny OCR dla nowych obrazów”; brak równoległego OCR i automatycznego fallbacku do OCR/innego dostawcy.
- „Lokalny OCR jest osobną, jawną alternatywą”; dla dokumentu vision nie uruchamia tekstowego extractora ani kolejnego vision.
- „Nie reinterpretujemy starych dokumentów po zmianie flagi”; brak backfillu i nowych wysyłek przez GET lub duplikat uploadu.
- „Ta pochodna nie nadpisuje oryginału”; EXIF transpose, RGB, proporcje, limity i brak EXIF/GPS także dla JPEG/PNG.
- „Claim zadania, wywołanie i publikacja wyniku są rozdzielone”; żadnej długiej transakcji/blokady podczas HTTP.
- „Rezerwacja limitu musi być atomowa i trwała”; jej awaria oznacza brak wywołania. Nie obiecujemy exactly-once billing przy awarii procesu.
- „Brakujące lub nieczytelne pola=null”; model nie wybiera konta/kategorii, nie oblicza salda ani nie wykonuje narzędzi/SQL.
- „Kwoty parsowane przez Decimal i zamieniane na grosze w kodzie, bez float”; przechowywanie księgi nadal BIGINT.
- „Wynik modelu nie jest źródłem prawdy i nigdy sam nie zatwierdza dokumentu”; wydruk gotówka/karta nie uzgadnia płatności.
- „Wynik przychodzący podczas edycji nie może wyczyścić konta/kategorii ani nadpisać zmienionych ręcznie pól”.
- PDF, dotychczasowa historia i reguły finansów bez zmiany; żadnych prywatnych zdjęć, surowych odpowiedzi lub sekretów w repo/CI/logach.
- „Dokładny dostawca, model, retencja i wartości limitów są warunkiem uruchomienia”; bez hardkodowanych nazw modeli i bez użycia produkcyjnego klucza.
- Ten plan nie upoważnia do aktywacji AI/egress w preview, powtórnej wysyłki dwóch prywatnych zdjęć, merge PR5/push main lub deployu/migracji produkcji.

## Review Focus

1. Zdjęcie EXIF6/8 z GPS, drobnym drukiem i pozornie poprawnym JSON-em: zachować czytelność, nie uznać składni za prawdziwość danych — testy Task2/3.
2. Timeout po przyjęciu żądania przez dostawcę oraz równoległy restart workerów: ograniczyć ponowienia i koszt, odrzucić stary wynik — Task4/5.
3. Wyłączenie/włączenie polityki między uploadem a wykonaniem: nie wysyłać starej kolejki po ponownym włączeniu — Task1/4/5.
4. Stary dokument, duplikat, odświeżenie listy i lokalne OCR po błędzie AI: zero niejawnych nowych wywołań — Task5/6.
5. Spóźniona propozycja podczas edycji kwoty/konta/kategorii: nie kasować pracy człowieka i nie nadpisywać zatwierdzonego rachunku — Task4/7/8.

---

## Stan i sposób wykonania

- [x] Projekt zatwierdzony, plan zapisany i sprawdzony względem specyfikacji.
- [x] Użytkownik potwierdził plan i sposób wykonania przed rozpoczęciem implementacji.
- [x] Task1–8 zrealizowane i niezależny końcowy review zakończony (2026-11-02).
- [ ] Oddzielna decyzja o konfiguracji i aktywacji preview, poza zakresem wykonania kodu.

Gałąź bazowa: `feat/financial-document-workflow`, dokumentacyjny HEAD przy planowaniu `cb46777`.
Kod funkcji/preview bazuje na `6385f39`. Przed wykonaniem ponownie sprawdzić HEAD/status;
nie zakładać tych SHA po integracji innych prac. Zastane dirty docs Velo/Q7 i prywatne
artefakty `/docker/finanse-preview/` zachować. Użyć istniejącego izolowanego worktree
albo utworzyć nowy zgodnie z using-git-worktrees; żadnego clean/reset/stash bez oceny.

### Verification conventions

Używać `/test`, `/lint`, `/typecheck`, `/migration "document vision jobs"` i `/docs`.
Jeżeli harness nie udostępnia uruchomienia komendy, odczytać jej definicję z
`.opencode/command/` i wykonać równoważne polecenia w **tym worktree**, nigdy automatycznie
w `/opt/finanse`. Pełny gate przed każdym commitem. Targeted RED/GREEN poniżej podaje
polecenia dla diagnostyki zadania, nie zastępuje pełnego gate.

`PY` oznacza interpreter sprawdzonego środowiska backendu tego worktree, `pytest`/`ruff`/
`mypy` z tego samego środowiska. Przed użyciem potwierdzić Python>=3.12 i zgodność lockfile;
historyczna ścieżka testowa to `/tmp/opencode/financial-document-venv/bin/python`.
Testy integracyjne wyłącznie lokalne `finanse_test` na127.0.0.1:55432 lub5432,
zgodnie z guardem `backend/tests/conftest.py`. Fixture tworzy/usuwa schemat: **nie**
używać DB preview/produkcji i nie uruchamiać równoległych zestawów na tej samej bazie.
Skip integracji z powodu braku DB nie jest PASS. Nie drukować testowego URL z hasłem.

## File map and dependency boundaries

| Pliki | Odpowiedzialność |
|---|---|
| `backend/app/documents/models.py`, `job_models.py` (nowy), `backend/app/main.py` | Metoda uploadu, metadane rewizji, trwałe zadania/polityka/licznik, rejestracja modeli |
| `backend/app/config.py`, `backend/.env.example`, `vision_config.py` (nowy) | Osobne ustawienia, bezpieczny snapshot konfiguracji i walidacja aktywacji |
| `backend/migrations/versions/<revision>_document_vision_jobs.py` | Addytywna migracja po7f8ce92bda94; faktyczny identyfikator z `/migration` |
| `images.py`, `image_process.py`, `ocr_pipeline.py` (nowy), `worker.py` | Ograniczona normalizacja i wspólne helpery OCR bez zależności cyklicznej workerów |
| `vision_schemas.py`, `vision_client.py` (nowe), `review_schemas.py` | Niezaufany payload vs walidowany wynik, adapter obraz+JSON Schema |
| `job_service.py`, `vision_worker.py`, `processing_policy.py` (nowe) | Trwałe zamiary, claim/lease/CAS/budget, przebieg bez długiej transakcji, wyłącznik |
| `backend/scripts/document_vision_policy.py` (nowy) | Jawna, audytowana zmiana polityki danego środowiska, bez wysyłki zdjęć |
| `service.py`, `router.py`, `review_service.py`, `review_router.py`, `schemas.py`, `worker.py` | Routing upload/legacy/job, status bez N+1, jawne akcje i kolejka |
| `frontend/src/api/documents.ts`, `components/documents/{documentStatus.ts,useReviewForm.ts}` (nowe) | Kontrakt API, etykiety i niedestrukcyjne nakładanie sugestii |
| `components/{DocumentUpload,DocumentList,DocumentViewer}.tsx`, `components/documents/DocumentReview.tsx` | Informacja o wysyłce, stany, odrębne akcje i istniejący formularz |
| `backend/tests/test_documents/test_vision_*.py`, `test_processing_jobs.py`, istniejące testy obrazów/review | Dokładne testy wskazane w zadaniach |
| `frontend/e2e/document-vision.spec.ts`, `document-vision-fixtures.ts` (nowe), testy komponentów/hooków | Syntetyczne contract fixtures, edycja/polling/telefon/a11y |

Nie dodawać nowej biblioteki do przetwarzania obrazów, platformy agentowej ani klienta
SQL. Wszystkie nowe moduły Python mają jawne typy i mały zakres odpowiedzialności.

## Cross-task contracts (decisions for implementers)

**DB:** `Document.processing_method`=`legacy_ocr|vision`, NOT NULL/server default legacy_ocr.
`DocumentExtractionRevision.input_method`=`text|image`, NOT NULL/server default text;
`warnings` JSON-list NOT NULL/default[], `source_sha256`, `derivative_sha256`, `provider`,
`model`, `prompt_version`, `schema_version` nullable. Nowe metadane z backendu, nie modelu.
`revision.data` nadal zgodne z ReviewSuggestion; nie dopisywać dowolnych kluczy do jego
strict payload. `ReviewResponse` dostaje osobne `input_method` i `warnings`.

`DocumentProcessingJob`: UUID id, user_id, document_id FK, revision_id nullable FK,
kind=`vision|local_ocr`, intent_key, request_hash, response_json dla idempotentnego202,
state=`pending|processing|succeeded|failed|paused|superseded`, attempt_count default0,
next_attempt_at, lease_token nullableUUID, lease_expires_at nullabletimestamptz,
call_reserved_token nullableUUID (ostatni lease obciążony limitem),
policy_epoch nullableint, error_code nullableboundedstr, created_at/updated_at.
Unique(user_id,kind,intent_key), unique(revision_id) dla nie-null; indeks(state,next_attempt_at).
Job vision wymaga rewizji image, local_ocr jej nie tworzy. FK nie mogą umożliwić
wykonania dla innego właściciela; walidować spójność w serwisie pod blokadą dokumentu.

`DocumentVisionUsage`: user_id, usage_date DATE (UTC), reserved_calls INTEGER>=0,
unique(user_id,usage_date). `DocumentVisionPolicy`: singleton id=1, enabled=false,
epoch=1, changed_at, configuration_fingerprint nullableboundedstr. Fingerprint to hash
kanonicznego provider/HTTPSendpoint/model/schema+prompt version, nigdy klucza. Jawne
enable wiąże konfigurację; startup wykrywający zmianę przy enabled dezaktywuje policy,
unieważnia starą epokę i nie włącza jej ponownie. To wewnętrzne dane operacyjne PostgreSQL,
nie JSON-file. Doprecyzowanie po review Task1: brak pola pozwalałby odziedziczyć kolejkę
przez zmieniony endpoint.

**Configuration:** `DOCUMENT_VISION_ENABLED=false` jako infrastrukturalny bezpiecznik;
DB policy musi być enabled, aby NOWE uploady wybierały vision. Flaga nigdy nie aktywuje
polityki automatycznie. Snapshot konfiguracji wymaga: `DOCUMENT_VISION_PROVIDER`,
`DOCUMENT_VISION_BASE_URL`, `DOCUMENT_VISION_MODEL`, secret `DOCUMENT_VISION_API_KEY`;
brak wartości => kontrolowany configuration_missing, nie crash aplikacji i nie fallback.
Konfigurowane propozycje domyślne (do potwierdzenia przy aktywacji): MAX_EDGE2048,
MAX_BYTES4MiB, MAX_OUTPUT_TOKENS1600, TIMEOUT_SECONDS60, CONCURRENCY2,
MAX_ATTEMPTS2, RETRY_DELAYS_SECONDS=(30,), DAILY_CALL_LIMIT_PER_USER50, LEASE_SECONDS120.
Walidować lease>timeout+parser timeout i job timeout>lease; edge/bytes dodatnie i nie
większe od odpowiednich limitów parsera/obrazu. Zero nazw realnych modeli w domyślnych.

**Policy:** `set_vision_policy(db, *, enabled: bool, performed_by: str) -> PolicySnapshot`.
Zmiana enabled albo konfiguracji endpoint/modelu wymaga jawnej nowej epoki. Podczas
wyłączenia wszystkie oczekujące/retry vision i ich review => paused/incomplete,
error_code=vision_disabled, lease jest unieważniony. Stary epoch nie wraca po enable.
Konfiguracji nie przełączać metodą off/on env bez tego kroku; env=false jest dodatkowym
awaryjnym stopem sprawdzanym przed każdą próbą. Przy starcie env=false dezaktywuje DB
policy przed dispatch; przy env=true nie reaktywuje jej. Resume to nowa jawna rewizja.

**Job interfaces** (wywołujący zarządza krótką transakcją i commitem):
- `create_vision_intent(db, user_id: UUID, document_id: UUID, *, key: str) -> DocumentProcessingJob`
- `create_local_ocr_intent(db, user_id: UUID, document_id: UUID, *, key: str) -> DocumentProcessingJob`
- `claim_processing_job(db, job_id: UUID, *, now: datetime) -> JobClaim | None`
- `reserve_vision_call(db, claim: JobClaim, *, now: datetime) -> bool`
- `finish_processing_job(db, claim: JobClaim, outcome: JobOutcome, *, now: datetime | None = None) -> bool`
- `recover_processing_jobs(db, *, now: datetime, limit: int) -> list[UUID]`
- `get_review_summaries(db, user_id: UUID, ids: Sequence[UUID]) -> dict[UUID, ReviewSummary]`.

`JobClaim` frozen dataclass: job_id/user_id/document_id/revision_id(nullable)/kind/
lease_token/policy_epoch(nullable)/attempt_no. `JobOutcome`: suggestion(nullable),
warnings tuple, source_sha256/derivative_sha256/provider/model/prompt_version/schema_version
nullable, safe error_code(nullable), retryable bool. Метadane nie zawierają sekretów.
Lock order wszędzie: advisory admission lock -> DB policy -> document -> job -> revision
-> usage. Nie trzymać admission lock podczas HTTP/obrazu; testować kolejność z dwiema
sesjami. Publisher ustawia CAS tylko gdy claim nadal aktualny, revision nadal najnowsza
i epoch niezmieniony; nie dotyka FinancialDocument. Weryfikacja claim ponownie przed HTTP.

**Processing statuses:** ReviewResponse nadal pending/processing/ready/incomplete/error.
ReviewSummary: revision_id, revision, input_method, status, error_code, warnings,
job_state(nullable). DocumentResponse rozszerzony o processing_method, review(nullable),
has_extracted_text bool, local_ocr_state(nullable); bez tekstów pól na liście.
Techniczny documents.done nie oznacza odczytu dobrej jakości. Nowy vision po zakończeniu
ustawia done również gdy trzeba ręcznie uzupełnić; szczegółowy stan jest w review/job.
Historyczne statusy pozostają niezmienione.

### Task 1: Trwałe modele, bezpieczna konfiguracja i migracja

**Files:** Create `job_models.py`, `vision_config.py`, `processing_policy.py`;
modify `models.py`, `config.py`, `backend/.env.example`, `main.py`;
create migration generated przez `/migration`;
test `backend/tests/test_documents/test_vision_models.py`, `test_vision_migration.py`.

**Interfaces:** Produces modele, PolicySnapshot(enabled,epoch), VisionConfig (secret
bez repr), `get_vision_config(settings: Settings) -> VisionConfig | None` oraz
`set_vision_policy(...)` zgodnie z contracts. Consumes obecne Base/Settings/Review.

- [x] **1. RED tests.** `test_legacy_rows_remain_text_and_never_create_jobs`: seed stary
  Document/DocumentText/revision i ledger na7f8ce92bda94, upgrade, porównaj każdą starą
  kolumnę i SHA; method legacy_ocr/text, zero jobs/usage i policy.enabled=false.
  `test_model_constraints`: błędne kind/method/state/negativecounter odrzucone.
  `test_vision_config_does_not_inherit_advisor_key`: brak własnego klucza => None,
  brak sekretu w repr/log; HTTP/credentials/query/fragment URL odrzucone.
  `test_policy_disable_changes_epoch_and_cannot_resume_old_jobs`: off/on pozostawia
  stare zadania paused, nic nie wysyła. Settings bez wartości vision nadal startuje.
- [x] **2. Observe RED.** W backendzie `PY -m pytest tests/test_documents/test_vision_models.py tests/test_documents/test_vision_migration.py -v`;
  FAIL z powodu brakujących modeli/kontraktów, nie niedostępnej DB.
- [x] **3. Implement.** Dokładnie contracts powyżej, CHECK/unique/FK i indeks gotowych
  zadań; import job_models do rejestracji metadata. Addytywna migracja po aktualnym
  head (dziś7f8ce92bda94), bez DROP/UPDATE starych wartości. Metadata defaults zgodne
  z server defaults. W config brak automatycznego callu do dostawcy/startup probe.
- [x] **4. GREEN + migration rehearsal.** Powtórz testy; sprawdź jeden head i upgrade
  osobnej syntetycznej DB z dawnych tabel. `/lint`, `/typecheck`, `/test` muszą PASS,
  testy migracji nie mogą trafić do DB preview/produkcji.
- [x] **5. Commit.** Wyłącznie pliki zadania, `feat: dodaj trwałe modele odczytu wizyjnego`.

### Task 2: Jedna bezpieczna normalizacja obrazów dla vision i OCR

**Files:** Create `ocr_pipeline.py`; modify `images.py`, `image_process.py`, `worker.py:_process_content`;
test `test_images.py`, `test_parser_container.py`, `test_review_worker.py`.

**Interfaces:** Consumes VisionConfig limity; extend `normalize_image(content: bytes,
mime: str, *, thumbnail: bool=False, max_edge: int|None=None,
max_output_bytes: int|None=None) -> bytes`. None zachowuje dotychczasowe zachowanie
preview/OCR; limity podane przez backend, nigdy nie przez publiczny upload payload.
`ocr_pipeline.py` przejmuje obecne `_convert_image_to_pdf(client, file_path,
image_content=None) -> bytes`, `_ocr_pdf(client,file_path,pdf_content=None) -> bytes`
i `_pdf_to_text(client,pdf_content) -> str`. Legacy worker importuje je pod tymi
samymi nazwami (zgodność istniejących monkeypatch testów); nowy vision_worker używa
ocr_pipeline zamiast importować worker, aby uniknąć cyklu przy rejestracji ARQ.

- [x] **1. RED tests.** Parametryzuj EXIF1/3/6/8 z syntetycznymi narożnikami i drukiem:
  oczekiwany obrót/proporcje, maxedge, JPEG/RGB, brak wszystkich EXIF/GPS/ICC/XMP,
  hash oryginału identyczny. JPEG/PNG/HEIF mają tę samą ścieżkę. Przekroczenie outputbytes,
  memory/CPU/time/pixels jest kontrolowanym błędem. `test_jpeg_ocr_receives_exif_normalized_bytes`
  przechwytuje wejście convert zamiast wołać prawdziwe OCR; oryginał zostaje identyczny.
- [x] **2. Observe RED.** `PY -m pytest tests/test_documents/test_images.py tests/test_documents/test_review_worker.py -v`;
  nowe limity/normalizacja JPEG muszą najpierw zawieść.
- [x] **3. Implement.** Istniejący ograniczony subprocess, EXIF transpose przed thumbnail,
  równe proporcje i stripping metadanych. Wszystkie obrazy przed legacy OCR normalizowane,
  nie tylko HEIF; nie rasteryzować PDF. Zero otwierania obrazów w głównym procesie.
  Przenieś wyłącznie trzy wskazane helpery do ocr_pipeline, bez przebudowy legacy
  transakcji i retry w tym zadaniu; kompatybilne importy pozostają w worker.py.
- [x] **4. GREEN.** Targeted + container parser/HEIF smoke na syntetykach, następnie
  pełny gate. Nie wkładać prywatnych paragonów do fixtures; pikselowy test obrotu nie
  ma być fałszywym testem jakości OCR.
- [x] **5. Commit.** `fix: normalizuj orientację zdjęć przed odczytem`.

### Task 3: Adapter obrazu i walidacja sugestii, bez agenta

**Files:** Create `vision_schemas.py`, `vision_client.py`, `test_vision_client.py`;
modify `review_schemas.py` (tylko pola odpowiedzi z defaultami dla legacy).

**Interfaces:** `VisionPayload`: strict document_type, fields ReviewFields,
warnings lista kodów z enum(unreadable,missing_required_fields,unsupported_document).
Bez przyjmowania provenance/parser_version/tools z modelu.
`extract_image_review(jpeg: bytes, *, config: VisionConfig) -> VisionExtraction`;
VisionExtraction zawiera backendowy ReviewSuggestion, warnings tuple i ready bool.
`VisionProviderError(code: str, *, retryable: bool)` ma wyłącznie bezpieczny kod.
`to_minor_units(total: str) -> int` waliduje Decimal/range<=9_007_199_254_740_991.

- [x] **1. RED tests.** MockTransport przechwytuje jeden POST: skonfigurowany model,
  obraz inline data:image/jpeg;base64, stały system prompt, JSON Schema strict,
  wszystkie właściwości required z nullable brakami, additionalProperties=false,
  max tokens/timeout z config. Brak filename/GPS/account_id/tools/URL dokumentu.
  `test_vision_reads_without_ocr_text` wymaga wyłącznie bytes.
  Odmowa, pusty output, truncation, zły JSON/typ/data/exponent/overflow -> safe code,
  brak drugiego wywołania; nullcurrency nie zamienia się na PLN, brak daty na dziś.
  Receipt bez IBAN/due_date może ready; brak supplier/total/currency => incomplete.
  Unsupported/multiple/statement/loan_schedule => incomplete, nie zwykły rachunek.
  Podmienione provenance i instrukcja w obrazie nie dodają funkcji/tool calls.
  `test_no_sensitive_logs_or_redirect_following` przechwytuje caplog i HTTP302/307.
- [x] **2. Observe RED.** `PY -m pytest tests/test_documents/test_vision_client.py -v`;
  spodziewany brak adaptera, zero prawdziwej sieci.
- [x] **3. Implement.** Obecne SDK z max_retries=0, httpx follow_redirects=false,
  trust_env=false (proxy tylko jawnie zatwierdzony), bounded HTTP response bytes
  przed deserializacją również błędów; nie logować raw exceptions/body. 429/timeout/
  5xx retryable; 401/403/config/schema/refusal/unreadable trwałe. Backend ustala
  provenance=`vision`, parser_version i metadata; nie zapisuje output jako OCR text.
  ready tylko dla invoice/receipt z wymaganymi polami i bez unreadable. Zero bilansu/
  sumowania przez model, zero obietnicy sprawdzenia pozycji bez ich ekstrakcji.
- [x] **4. GREEN.** Adapter unit tests i legacy test_extractor/test_review PASS;
  pełny gate; całość offline. Log test używa marker-secret, nie prawdziwego sekretu.
- [x] **5. Commit.** `feat: dodaj kontrolowany odczyt obrazu przez model wizyjny`.

### Task 4: Claim, retry, limity i publikacja wyniku bez długich transakcji

**Files:** Create `job_service.py`, `vision_worker.py`, `test_processing_jobs.py`,
`test_vision_worker.py`; modify `processing_policy.py`.

**Interfaces:** Consumes Task1/2/3; implements job interfaces z contracts.
`async process_document_job(ctx: dict[str, object], job_id: str) -> None` w vision_worker
sam otwiera krótkie sesje; lokalne OCR używa helperów ocr_pipeline z Task2 dopiero Task5.

- [x] **1. RED tests.** Dwie prawdziwe sesje: `test_duplicate_claim_reserves_one_call`,
  `test_global_concurrency_and_user_daily_limit_atomic`, `test_usage_failure_prevents_http`.
  `test_network_runs_after_claim_commit`: w czasie mockHTTP druga sesja może dostać
  NOWAIT lock dokumentu/job; mockHTTP nie ma aktywnej DB sesji pierwszego claimu.
  `test_timeout_after_remote_acceptance_is_bounded`: maxattempts, każda wysłana próba
  zwiększa usage raz, duplicate delivery nie; SDK nie powiela retry. Dzień usage UTC.
  `test_old_lease_result_cannot_replace_new_revision` i `test_approval_during_network_unchanged`.
  `test_off_on_epoch_pauses_pending_and_rejects_inflight_publication` oraz brak callu
  przy env=false/config missing. Stary lease nie odzyskuje slotu przez sam wynik.
- [x] **2. Observe RED.** `PY -m pytest tests/test_documents/test_processing_jobs.py tests/test_documents/test_vision_worker.py -v`;
  testy konkurencji bez xdist i bez wspólnego innego pytest.
- [x] **3. Implement.** Krótki claim z admission advisory lock i limitem aktywnych
  nieprzeterminowanych lease; brak slotu => pending bez zwiększeniaattempts/usage.
  Claim zwiększa attempt_count, nadaje nowy token/expiry i commit. Wczytanie oryginału
  przez read_verified_document_content i normalizacja poza transakcją. Przed HTTP
  ponowny CAS/epoch/env/config + atomowy UPSERT licznika z WHERE reserved_calls<limit,
  commit rezerwacji (fail closed). W tej samej transakcji ustaw call_reserved_token;
  ponowne reserve dla tego lease zwraca false i nie wysyła HTTP ani nie zwiększa usage.
  Testować duplikat reserve tego samego claimu. Tej rezerwacji nie zwracać po niepewnym błędzie sieci.
  Utrata procesu po rezerwacji może zużyć limit bez wywołania — bezpieczne przeszacowanie.
  Publikacja przez CAS aktualnego lease/revision/epoch; wynik nie nadpisuje nowszej
  rewizji i nigdy nie mutuje rachunku/postings.
  Publisher sprawdza także lease_expires_at>now (brak odzyskania starej dzierżawy
  nie daje prawa do zapisu po terminie); default now to aktualne UTC, nie czas claimu.
  Recovery przełącza jednocześnie job i review: pending przy requeue, incomplete
  z attempts_exhausted przy limicie. Brak konfiguracji pozostaje configuration_missing,
  nie vision_configuration_changed. Doprecyzowanie po review Task4.
  Błędy transient -> pending/backoff, terminal -> failed oraz incomplete/error
  review z bezpiecznym kodem. Limit =>
  incomplete/vision_daily_limit bez samoistnej kolejnej wysyłki następnego dnia.
- [x] **4. GREEN.** Zegary kontrolowane fixture, bez sleep; recovery i powtórka co
  najmniej dwóch sesji PASS. Sprawdź że requeue po expiry nie przekracza maxattempts.
  Wygaśnięty HTTP może nadal istnieć u dostawcy; lokalny limit lease nie jest obietnicą
  dokładnej liczby aktywnych obliczeń u dostawcy. Pełny gate i review transakcji.
- [x] **5. Commit.** `feat: ogranicz i uodpornij zadania odczytu dokumentów`.

### Task 5: Nowe uploady vision, stare dokumenty i jawne alternatywy

**Files:** Modify `service.py:store_document`, `router.py:upload_document`, `review_service.py`,
`review_router.py`, `worker.py`; create `test_vision_upload.py`, `test_vision_actions.py`;
modify `test_review_worker.py`, `test_retry.py`.

**Interfaces:** Consumes create_*_intent/processing policy/worker from Task4.
Register ARQ process_document_job i cron dispatch_document_jobs (durable pending oraz
expired lease). Legacy dispatchy filtrują processing_method=legacy_ocr i text revisions;
nie mogą uruchamiać vision lub lokalnego fallbacku drugi raz.
POST `/{id}/vision/prepare` z Idempotency-Key, body pusty =>202 ReviewResponse;
nowa jawna rewizja image dla dowolnego obrazu, także starego. PDF=>422, obcy=>404,
disabled=>409, rate=>429. Stary `/review/prepare` pozostaje tekstowy dla legacy;
dla vision nie uruchamia textLLM i zwraca409/use_vision_action.
`/{id}/retry-ocr` dla vision tworzy local_ocr job (202), legacy pozostaje kompatybilne.

- [x] **1. RED tests.** Nowy JPEG przy policy enabled => document+revision+job
  w jednej transakcji, bez DocumentText; rollback uploadu nie zostawia zamiaru.
  Flaga/policy disabled => legacy. Policy enabled, missing key => vision incomplete,
  brak fallbacku. Duplikat starego/nowego pliku po zmianie flagi nie zmienia metody,
  rewizji i nie tworzy joba/callu. Redis error po commit => dispatcher odzyskuje.
  Idempotency retry replay zwraca ten sam202 bez nowego joba; inny hash=>409.
  `test_vision_local_ocr_does_not_chain_llm_or_replace_review`, `test_pdf_stays_legacy`.
  GET list/detail/review/original/preview zero kolejki i wywołań; obcy owner404,
  brakCSRF403, limit akcji429. Wyłączona polityka nie wznawia starego pending po enable.
  Równoległe jawne akcje dla jednego obrazu nie trzymają dwóch aktywnych zadań:
  zwracają bieżący zamiar albo409; nowa rewizja dopiero po terminalnym stanie.
- [x] **2. Observe RED.** `PY -m pytest tests/test_documents/test_vision_upload.py tests/test_documents/test_vision_actions.py -v`.
- [x] **3. Implement.** W store_document wybór trwale przed flush/commit tylko dla
  nowego obrazu, po dedupe; nie zakładać zadania w GET. Rozdziel legacy worker od
  processing_job. Jawne localOCR wywołuje normalizację+convert/OCR/text i aktualizuje
  wyłącznie DocumentText i localjob, bez prepare_review/ekstraktora/zmiany metody.
  Serializuj operacje przez document lock; aktualny job chroniony przed delete (409),
  spóźniony job po usunięciu nie odtwarza dokumentu. Existing linked delete policy
  pozostaje, bez masowego kasowania. Wyniki oldReview i FinancialDocument nietknięte.
- [x] **4. GREEN.** Targeted + całe test_documents/test_finance (w tym bills/payment/
  coverage) i gate. Brak prywatnych zdjęć i rzeczywistego endpointu. Snapshot ledger,
  balances, inbox przed/po upload/vision/localOCR/retry => identyczne.
- [x] **5. Commit.** `feat: kieruj nowe zdjęcia do automatycznego odczytu AI`.

### Task 6: Lekki status API i bezpieczny operator polityki

**Files:** Modify `schemas.py`, `review_schemas.py`, `review_service.py:_response`,
`service.py:get_documents/get_document`, `router.py`; create `processing_queries.py`,
`backend/scripts/document_vision_policy.py`, `test_vision_status.py`, `test_vision_policy.py`.

**Interfaces:** Implement get_review_summaries z contracts w processing_queries;
GET/upload responses przez wspólny mapper do DocumentResponse. Capabilities dodaje
`automatic_image_vision: bool`, `vision_provider_label: str|null` (tylko skonfigurowana
nazwa), `vision_notice: str|null` bez URL/key. CLI `--enable|--disable --expected-epoch N`
przyjmuje kontrolowany target DB ze środowiska, ma dry-run domyślny i osobne `--apply`;
enable sprawdza konfigurację, ale nie wysyła dokumentów. Operator nadaje nowy epoch.

- [x] **1. RED tests.** Lista50 dokumentów: stała liczba SQL<=4 dla samego mappera
  (bez auth/rate limit), brak N+1/pełnychfields/base64. Latest revision dobierana
  z owner filter; stare nullsummary bez sztucznego gotowe. has_extracted_text bazuje
  na istnieniu tekstu, nie na documents.done. Vision done+incomplete pokazuje review
  incomplete, nie „OCR success”. Capabilities bez sekretów. CLI bez apply zero mutacji,
  expected-epoch mismatch=>odmowa; disable unieważnia stare pending/retry/inflight.
  Ponowne enable nie wznawia paused, nawet po pełnym restarcie. GET bez side effects.
- [x] **2. Observe RED.** `PY -m pytest tests/test_documents/test_vision_status.py tests/test_documents/test_vision_policy.py -v`.
- [x] **3. Implement.** Jeden batched latest-revision/status query perpage; nie
  zmieniać starego typu odpowiedzi listy. Wspólny mapper z aktualnymi polami i defaultami
  legacy. Zwracać wyłącznie enum safe errors, nie tekst exception. Log polityki to
  metadata audytu bez sekretów; env=false startup atomowo disable, env=true nigdy enable.
- [x] **4. GREEN.** Pełny gate. Sprawdź zgodność ReviewResponse dla starych JSON i
  parser_version/provenance niepochodzące z modelu. Operator testowany wyłącznie
  na testDB; żadnego wywołania CLI apply na preview lub produkcji w tej sesji.
- [x] **5. Commit.** `feat: udostępnij stany i kontrolę polityki odczytu zdjęć`.

### Task 7: Obecny frontend bez utraty edycji i mylącego „Gotowe”

**Files:** Modify `frontend/src/api/documents.ts`, `components/DocumentUpload.tsx`,
`DocumentList.tsx`, `DocumentViewer.tsx`, `components/documents/DocumentReview.tsx`;
create `components/documents/documentStatus.ts`, `useReviewForm.ts` i ich testy;
modify `pages/Documents.test.tsx`, `DocumentUpload.test.tsx`, `DocumentReview.test.tsx`.

**Interfaces:** `getDocumentStatus(doc: DocumentData) -> {label: string; tone: ...}`;
useReviewForm(documentId,review) zwraca form/update/isDirty/applyNewSuggestions.
Puste currency=`""` w formularzu i UI „Wybierz walutę”, nie cichy PLN dla vision.
POSTvision hook ma stabilny klucz pojedynczej intencji, nie nowy przy transport retry;
osobna akcja użytkownika=>nowyklucz. Review polling tylko pending/processing, nie po błędzie.

- [x] **1. RED tests.** Upload capabilities aktywne => widoczna informacja przed
  aparatem/plikiem: „Zdjęcia są automatycznie wysyłane do [dostawca] do odczytu AI.
  Dane wymagają sprawdzenia. Informacje widoczne na zdjęciu są przekazywane dostawcy.”
  Brakconfiguration label=>bez wymyślania marki. Pending=>„Odczyt w kolejce”,
  processing=>„Odczytywanie”, ready=>„Propozycja do sprawdzenia”, incomplete=>
  „Uzupełnij ręcznie”, błędy=>„AI niedostępne”/„Limit odczytów AI”, z manualpath.
  `test_polling_does_not_reset_dirty_fields`: ręczna kwota+account+category pozostają
  po refetch tego samego/nowszego review; nietknięte pola wypełniają się tylko raz
  perrevision. Jawne zastosowanie nowych sugestii nie usuwa konta/kategorii.
  `test_switch_document_resets_form_but_not_refetch`, currency null=>puste, nie PLN.
  `test_vision_without_ocr_text_does_not_request_text`, osobne AI retry/localOCR.
- [x] **2. Observe RED.** W frontend `npm run test -- --run src/components/documents/DocumentReview.test.tsx src/pages/Documents.test.tsx`
  oraz nowe testy useReviewForm/status; potwierdzić race/reset RED na obecnym useEffect.
- [x] **3. Implement.** Rozbij obecny setForm useEffect do hooka z dirty perfield,
  stabilną tożsamością documentId/revisionId i porównywaniem wersji. List/render status
  bazuje na ReviewSummary; nie dodawać GET perrow. has_extracted_text steruje viewerem.
  Inwalidacja list/review po actions, bounded polling wyłącznie aktywnych stanów,
  dedupe TanStack Query. Odrębne etykiety legacy „OCR zakończony — sprawdź dane”.
  Nie zmieniać layoutu, nie dodawać nowego silnika dialogów.
- [x] **4. GREEN.** Wszystkie unit, lint/tsc/build, a11y istniejącego formularza.
  Sprawdź disabled save z pustą currency i guard server-side. Klucz idempotencji
  nie jest sesją i nigdy nie zawiera zdjęcia/nazwy/sekretów. Pełny gate.
- [x] **5. Commit.** `fix: pokaż stany odczytu AI i zachowaj ręczne poprawki`.

### Task 8: Regresja end-to-end, odbiór i przekazanie bez aktywacji

**Files:** Create `frontend/e2e/document-vision.spec.ts`, `document-vision-fixtures.ts`,
`backend/tests/test_documents/test_vision_invariants.py`,
`docs/audits/2026-10-31-document-vision-verification.md`;
modify `docs/CHANGELOG.md`, `docs/TASKS.md`, `docs/JOURNAL.md` oraz plan checkboxes.

**Interfaces:** Consumes wszystkie API/worker/frontend zadania; brak nowych API.
Syntetyczne fixtures mają znane ground truth kwoty/daty i żadnych danych prywatnych.

- [x] **1. RED integration/E2E.** Uploadimage=>pending=>ready bez OCR, manualapprove
  i zero automatycznych postings. Błąd/limit/refusal=>oryginał+manual; localOCR GETtext
  bez textLLM; staryphoto wymaga POSTvision, duplikat/GET zero wywołań. Uruchom
  `test_vision_invariants.py`: porównaj pełne rekordy ledger/inbox/balances przed/po
  każdym upload/vision/retry/approve, nie tylko count. Osobna świadoma płatność
  przez istniejący endpoint pozostaje poprawna i zbilansowana.
  Browser375/1440/light/dark: datareview podczas edycji, focus/Escape, pustawaluta,
  wolna odpowiedź, retry429, brak overflow, axe. PDF nadal dotychczasowy kontrakt.
- [x] **2. Observe failures, then wire fixtures only.** `PY -m pytest tests/test_documents/test_vision_invariants.py -v`;
  frontend `npx playwright test e2e/document-vision.spec.ts`. Fixture musi odpowiadać
  realnym schematom Task6; nie „naprawiać” testu pomijając rzeczywistą walidację.
  Jeśli znaleziono błąd implementacji: regresja RED i poprawka w odpowiednim zadaniu,
  nie duży refactor na końcu. Żadnych prawdziwych wysyłek modelu w CI/E2E.
- [x] **3. GREEN full gate.** `/test`, `/lint`, `/typecheck`, frontendbuild i pełne E2E,
  parserDockerHEIF i migracja na syntetycznym snapshot7f8. Porównaj wszystkie stare
  kolumny i hashe originals; odtworzenie syntetycznego dump PASS, jeden head.
  Podaj rzeczywiste liczby PASS/skip i powody — nie kopiować949/279/75 z poprzedniej sesji.
- [x] **4. Independent acceptance.** Końcowy fresh-context review kodu i całej zgodności
  spec/plan, szczególnie lease/koszt/stop/noautoactions/editrace. Zamknij ważne findings
  z regresjami. Raport rozdziela: atrapa provider PASS vs realprovider NOT RUN, viewport
  PASS vs Android/iPhone NOT CERTIFIED. Wpisz do raportu wartości domyślne jako propozycje.
- [x] **5. Document and commit.** `/docs`, audit zawiera dowody bez sekretów i ograniczenia,
  aktualne task statuses; commit `test: zweryfikuj automatyczny odczyt zdjęć`.
  Nie stage'ować zastanych Velo/Q7 ani prywatnych artefaktów. Brak automatycznego push,
  merge, migracji produkcji i zmiany `/docker/finanse-preview/compose.yaml`.

## Oddzielny, niewykonywany teraz gate aktywacji

Po odbiorze kodu pokazać właścicielowi wynik i uzyskać osobną zgodę obejmującą:
provider/model i potwierdzenie obsługi image+strictschema, warunki retencji, własny klucz,
limit wywołań i koszt na podstawie aktualnego cennika oraz bezpieczny egress preview.
Dopiero potem powstaje osobny plan infra/release z review, snapshot/backup i rollbackiem.
Nie podłączać backendu/DB do sieci produkcji lub do nieograniczonego Internetu „na test”.
Warunek liveodbioru: rzeczywisty adapter przetestowany na syntetycznych dokumentach,
następnie aparat/galeria/HEIC Android/iPhone przez użytkownika. Dwa obecne prywatne
zdjęcia wolno powtórzyć tylko po oddzielnej zgodzie. Rollback polityki zachowuje
wszystkie oryginały/review/ledger i nie robi downgrade ani kasowania danych.

## Self-review completed before handoff

- [x] Spec1–3: automatyczny vision-only dla nowych obrazów, PDF/legacy i brak backfillu — Task1/5.
- [x] Spec4–5: pochodna, prywatność, konfiguracja bez modelnames, schemat, limity — Task1–4/7.
- [x] Spec6: trwałość/intencje, krótki claim, odzyskiwanie/CAS, epoch i boundedretry — Task1/4–6.
- [x] Spec7: Decimal/nulls/unsupported/manual approval, zero ledger — Task3/5/8.
- [x] Spec8: summarybezN+1, osobne stany, lokalnaalternatywa, dirtymerge — Task5–7.
- [x] Spec9–11: stare zdjęcia/zgoda, fixtures/migracja/review i osobna aktywacja — Task5/8/gate.
- [x] Signatures i nazwy: wspólne contracts wykorzystane w zadaniach; job/image revision
  niezależne od DocumentText; localOCR nie tworzy rewizji i nie uruchamia legacyreview.
- [x] Review Focus przypisany do nazwanych testów; instrukcje RED/GREEN/commit per zadanie.
- [x] Plan wykonany i odebrany lokalnie; aktywacja oraz wdrożenie pozostają osobną decyzją.
