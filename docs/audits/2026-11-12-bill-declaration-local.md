# Deklaracyjne opłacenie faktury — odbiór lokalny

## Zakres

Zatwierdzony plan: `docs/superpowers/plans/2026-11-12-bill-declaration-without-transaction.md`.
Komenda deklaracji i undo, audyt, bez migracji i bez transakcji. UI oddziela kwotę
do zapłaty od pozostałej do powiązania z księgą. Prognoza pomija deklarację, zachowuje
coverage, późniejsze rzeczywiste alokacje nie podwajają rozliczenia.

Wszystkie dane w testach są syntetyczne. Nie zmieniono danych produkcyjnych,
nie wykonano merge, push ani deployu. Kod przygotowany na linked worktree
`feat/financial-document-workflow`, od bazowego `1b43f0d`.

## Dowody

- Backend TDD:21FAIL przed implementacją (brak endpointu/PATCH bypass), następnie
  40focusedPASS, w tym rollback audytu. Pełny backend: **2351PASS**,0failure/error/skip,
  23standardowo wykluczone testyproxy;422hash źródeł bez driftu.
- Frontend TDD: brak helpera/dialogu i3FAIL prezentacji;19focusedPASS. Dodatkowy
  same-version409:1FAIL/7PASS → poprawka decisionEpoch →631fullvitestPASS.
- E2E:28PASS desktop/mobile na produkcyjnym buildzie obsługiwanym wyłącznie przez
  syntetyczne API. Declared→reload→częściowy/pełny link oraz partial→declared→undo.
  Screeny375/1440 obejrzane, modal czytelny, brak horizontaloverflow.
- RuffPASS, mypy192PASS, ESLintPASS, tscPASS, buildPASS. Znane ostrzeżenia:
  passlib/crypt deprecated i frontendbundle >500kB; bez poszerzania zakresu o bundle split.
- Jeden read-onlyreview `ses_e30892741ffeA1j2SI0aMSufFP`:0Critical/0Important/0Minor,
  lista „Declined to judge” pusta. Reviewer nie uruchamiał testów niezależnie.

## Środowisko i odrzucone próby

Zgodny Python3.12/requirements runner. Własne no-portPostgreSQL na tmpfs, z wyłączoną
trwałością wyłącznie syntetycznych danych. Fixture migracyjne korzystają z własnej
roli `bank_import_task_<hex>`. Nie używano produkcyjnych danych ani połączeń.

Niepełne serialpróby przerwanoSIGINT i nie zaliczono jakoPASS. Pełna kolekcja:
2351testów,23proxy standardowo wykluczone.8 rozłącznych grup na osobnych bazach.
7grup/2057PASS. Ostatnia grupa początkowo exit4 bez wykonania: wcześniejszy testOCR
ma w parametrze gzip z bieżącym timestampem, więc nodeID różni się między kolekcjami.
Ponowiono tylko tę grupę294testów: wybór funkcji i jawne odrzucenie2stabilnych cases
przypisanych do innych grup, bez zmiany źródeł. Gate:2351JUnit,0fail/error/skip,
zachowana rozłączność kolekcji i frozen sourcehash. Ostatnia grupa294PASS,
2jawne deselect dotyczą przypadków już wykonanych w pozostałych grupach.

Cleanup:18własnych kontenerów końcowych testów usunięto po sprawdzeniu exactID/label/
nohostports/idle/exitnot137 i potwierdzeniu braku kontenera; bezforce/prune. Pierwszą
parę setup usunięto wcześniej: pierwszy runnerPID1sleep nie obsłużył SIGTERM (exit137),
ujawnione w dzienniku; dalsze runnery używały --init i poprawnie się zatrzymały.

## Podjęte decyzje

1. Pozostawiono istniejący linked worktree zamiast tworzyć zagnieżdżony — zgodnie
   z regułą isolation; koszt błędu: mieszana historia gałęzi. Staging obejmuje tylko
   tę funkcję, wcześniejsze dirtydocs/audity pozostają nienaruszone.
2. Frontend przygotowywano podczas weryfikacji backendu — niezależne pliki i ustalone
   API; koszt błędu: konieczność dostosowania konsumenta. Brak niejawnego zaliczenia etapu.
3. Pełny backend wykonano w8 izolowanych grupach — oszczędza czas; koszt błędu:
   mniej pokrycia zależności od kolejności serialnej. Każdy test wybrany dokładnie raz,
   wymagane pełne sumyJUnit i niezmienione źródła.
4. Ledger zakończenia wykorzystuje świeży wynik tej komendy zamiast ponawiać cały
   zestaw przez task-done — koszt błędu: ręczny zapis statusu; mitigacja przez logi,
   XML i sourcefreeze. Nie zaliczono abortów ani runtime-skips.

## Status integracji

Odbiór lokalny i cleanup własnego środowiska zakończone. Gałąź/worktree zostają
zachowane. Wdrożenie i oznaczenie rzeczywistej faktury wymagają odrębnej decyzji.
Instrukcja: `docs/operations/financial-documents.md`.
