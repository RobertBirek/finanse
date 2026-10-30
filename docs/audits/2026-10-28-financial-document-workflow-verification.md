# Weryfikacja obiegu dokumentów finansowych

Data: 2026-10-30. Gałąź: `feat/financial-document-workflow`.
Nazwa pliku zachowuje datę zaakceptowanego planu; wyniki poniżej pochodzą z30.10.
Status: implementacja oprogramowania, gate i całościowy review z poprawką PASS.
Finalny commit funkcjonalny: `0524cb9e13d7045833ac36b05940a01edbbd401f`.
Gotowość kodu nie oznacza pełnej kwalifikacji wydania: prawdziwe telefony BLOCKED.
Bez zgody na wdrożenie lub pracę na danych użytkownika.

## Zakres

- Oryginał → OCR/propozycja → ręczna weryfikacja → rejestr → jawne rozliczenie.
- Rejestr PLN/EUR/USD; alokacje i nowa płatność wyłącznie PLN.
- Upload, OCR i zatwierdzenie dokumentu nie tworzą transakcji ani postingów.
- Nadchodzące uwzględniają pozostałość i konkretną zastąpioną estymatę, bez kopii faktury
  w regułach miesięcznych. Nierozstrzygnięte pokrycie i brakujące dane mają jawne wyłączenia.
- Brak bankowych integracji, wysyłania przelewów, importów, korekt historii i wdrożenia.

## Kontrole

| Kontrola | Wynik | Zakres dowodu |
|---|---|---|
| Nowe E2E | PASS,16 | Syntetyczne API,375/1440; częściowe/pełne rozliczenie, jawne100/120replacement, manualfallback, uploadHEIF/attach i paragon |
| Nowy backend workflow | PASS,5 | Syntetyczny PostgreSQL; źródła/ledger, owner404 i rzeczywiste dwie sesje zatwierdzenia |
| Pełny backend | PASS,949 | 8 proxy deselected,10 znanych ostrzeżeń,844.82s; final-wave-full-backend.log |
| Pełny frontend/build/E2E | PASS, potwierdzone powtórzenie | Lint/types/279unit/build i75E2E PASS,1 celowy desktopskip; po całej końcowej poprawce |
| Ruff/mypy | PASS | Aplikacja81 modułów; lint również testów i zmienionego skryptu Actual |
| Parser Docker | PASS | Python3.12.15/Pillow12.3.0/pillow-heif1.8.1; HEIF→JPEG, hash oryginału, orientacja/GPS |
| Migracja/dump-restore | PASS | PostgreSQL16.14,upgrade/downgrade/reupgrade oraz odtworzenie osobnej bazy z syntetycznymi danymi |
| Task10: review | PASS po poprawkach | Jawne100/120, HEIFcontract i pg_blocking_pids realnego oczekiwania na blokadę |
| Cała gałąź: review | PASS po jednej wspólnej poprawce | 4Important domknięte w0524cb9; scopedreview bez nowych Critical/Important/Minor |
| Android/iPhone | **BLOCKED** | Brak rzeczywistych urządzeń; viewport nie zastępuje aparatu/galerii |

## Powtarzalne scenariusze

- `frontend/e2e/financial-documents.spec.ts` i `financial-document-fixtures.ts`:
  stary PDF/manual →100PLN→40/60, replacement100/120, HEIF jako dodatkowe źródło
  bez kosztu, paragon declared_paid bez fikcyjnej alokacji i widoczny błąd OCR/LLM.
- `backend/tests/test_finance/test_bill_workflow.py`: rzeczywiste serwisy i PostgreSQL,
  w tym `test_two_independent_sessions_approve_one_draft_once_without_ledger_entries`.
- Pozostałe testy `test_bill_*` sprawdzają capacity, invarianty księgi, replay receipt,
  właściciela, legacy Inbox, źródła, wyłączenia, coverage i ochronę mutatorów Actual.
- Regresje UI obejmują real QueryClient partial allocation→remaining/forecast,
  stable nested intent keys i powtarzane409 wymagające kolejnego właściwego refetch.

## Parser i prywatność

Lokalny obraz `personal-advisor-document-verification-20261030`:
`sha256:de1985e61cbb3fd6c3f0bba632a368d2e5d16e9d3e5e2d148b4f43dba9f03970`.
Testy syntetyczne uruchomiono bez sieci, read-only, bez uprawnień root.
Artefakty: `/tmp/opencode/task10-parser-validation/`.
Oryginały pozostają prywatne i niezmienione; pochodna JPEG nie zachowuje GPS.

## Migracja i odtworzenie

W oddzielnym PostgreSQL16.14 sprawdzono `c2d7e9a4f801 → 7f8ce92bda94`, rollback
oraz ponowne przejście na head. Wszystkie stare kolumny i syntetyczne sentinel rows
dokumentu/SHA, Inbox i księgi zachowano; postings pozostały zbilansowane.
Dump przywrócono do osobnej bazy `task10restore` i potwierdzono dane oraz Alembic head.
Kontener był dostępny tylko na loopback i został usunięty po próbie.
Artefakty: `/tmp/opencode/task10-migration-validation/`. Nie użyto danych produkcji.

## Ograniczenia i dalsze czynności

Całościowy review wykrył4 ważne luki, których passing taskgate nie wykluczył:
router nie przekazywał due/queryfilters, detail miał puste forecastreasons,
update pokrytejfaktury nie blokował zmiany tożsamości oraz backend nie wymagał
potwierdzenia wpływu archiwizacji/anulowania. Commit0524cb9 objął komplet poprawek
i regresji: typedrouterfilters, sharedread-onlyeligibilityhelper, ownerlocked guard
identitycoverage i server-enforcedconfirmation audytowany z pozostałością. Świeży
gate949/279/75+1skip PASS oraz ponowna syntetyczna migracja/restore PASS.
Końcowy scopedreview potwierdził zamknięcie wszystkich4findings bez nowych
Critical/Important/Minor. Nie jest to zgoda na merge, push, deploy lub import.

### Wynik końcowego przeglądu

- `bills_router.py`: boundedquery i typed due-range trafiają do rzeczywistego API;
  regresja sprawdza przefiltrowany total przed paginacją.
- `bill_forecast.py` i `bills.py`: jedno read-only eligibility path dla odpowiedzi
  rejestru i prognozy, jawny domain today/configuredhorizon, bez zapisu przy GET.
- `bills.py`: shared ownerlock przed rowlocks i guard tożsamości coveredbill,
  same-value dozwolone; niezależne sesje potwierdzają bezpieczeństwo race.
- Lifecycle: backend wymaga literaltrue, audytuje pozostałość i skutek, requesthash
  obejmuje potwierdzenie; UI wysyła je dopiero po jawnym potwierdzeniu człowieka.
- Szeroki review nie znalazł Criticalsecurity/ledger; potwierdził owner-scope,
  prywatne oryginały, bounded subprocess i brak automatycznego kosztu.
- Pozostawiono jawnie10baselinewarnings, istniejący błąd script-wide mypy i brak
  przechwyconego pre-fixRED w jednej historycznej rundzieTask4. To nie nowe defekty
  produktu ani nie powód, by deklarować je naprawionymi.

## Decyzje wykonawcze i koszt pomyłki

1. Testy na repo-pinned zależnościach zamiast starego współdzielonego venv;
   koszt pomyłki: ponowny test zgodności rzeczywistego runtime przed wydaniem.
2. Istniejący izolowany worktree/nowa gałąź i kopia venv, bez zmian shareddeps;
   koszt: odbudowa środowiska i czas testów.
3. Model podagenta bez jawnego wskazywania, zgodnie z kontraktem narzędzia;
   koszt: potencjalnie większy kontekst/koszt wykonania.
4. Stary test cashflow z deterministyczną datą, bez poszerzania produkcyjnego due_day;
   koszt: przeróbka testu, nie zmiana księgi.
5. Rozszerzenie typów ReviewSuggestion o statement/loan_schedule/other zgodnie
   z wymaganiem odróżniania źródeł; koszt: korekta enum/mapowaniaUI, nie finansów.
6. Ochrona operatorowego Actualreplacement jako istniejącego mutatora Task6;
   koszt: utrzymanie dodatkowych guardów/testów, bez uruchamiania importu.
7. Oddzielne okna focusedimplementation i fullgate z zachowaniem gate przedcommitem;
   koszt: dodatkowa koordynacja i czas testów, bez osłabiania invariantów.

Pierwszy pełny E2E run miał70 PASS/1skip/3FAIL. Przyczyny potwierdzono:
shared fixture nie obsługiwała `/documents/upload-capabilities`, a mobilny test
klikał niejednoznaczny przycisk zanim zakończyło się szukanie duplikatów.
Dodano odpowiedź capabilities i oczekiwanie na właściwą akcję `type=button`;
zachowano ścisłe `assertClean`, bez sleep/retry/wyciszania błędów.

- Brak certyfikacji rzeczywistego Android/iPhone: aparat/galeria, orientacja, duże
  zdjęcia i zużycie pamięci wymagają osobnego sprawdzenia na urządzeniach.
- E2E używają syntetycznego API. Test binarnego HEIF w przeglądarce potwierdza
  transport/interakcję; rzeczywisty dekoder jest sprawdzany oddzielnie w Dockerze.
- Znane ostrzeżenia Passlib/FastAPI pozostają jawne; nie dodano filtrów wyciszających.
  Istniejący błąd mypy w operatorowym skrypcie Actual poza zakresem app-only gate
  pozostaje do końcowego triage; nie deklarujemy clean script-wide mypy.
- Przygotowanie starych dokumentów użytkownika, migracja produkcji, push/merge i deploy
  nie wynikają z tej weryfikacji; wymagają osobnej zgody.
