# Daty zakupu i księgowania — lokalny odbiór etapu 1

## Status i granice

Implementacja lokalna odebrana po końcowych gate’ach. Nie wdrożono, nie zmieniano produkcyjnego
schematu ani historii, nie wykonywano realnych AI/OCR. To etap 1 z sześciu, nie gotowy
agent kategoryzujący. Spec i plan w `docs/superpowers/{specs,plans}/2026-11-03-*`.

## Kontrakt wdrożonego lokalnie kodu

- Nowe ręczne wydatki mają opcjonalne jawne daty zakupu i księgowania; formularz podaje
  obie. Data księgowania jest zgodna z legacy `FinancialTransaction.date`. Pozostałe
  typy operacji i legacy API pozostają kompatybilne.
- Osobna tabela `transaction_date_metadata`, proweniencja/date-pair checks, wersja,
  indexy; brak dodatkowych kolumn transakcji lub zmiany Actualfingerprint. Istniejące
  wiersze pozostają bez metadanych, ich typ daty jest nieustalony.
- Osobne polecenie ręcznej korekty wydatku, owner-scope, advisory/parent/metadata locks,
  expected_version/updated_at, idempotentny no-op, audyt. Nie zmienia postings/kwot/linków.
  Chroni import/Actualmapping, płatności dokumentów i pożyczek. Narracja edytowalna.
- Wydatek i budżet według daty zakupu; przy jej braku jawny fallback do istniejącej
  daty. Salda/historia banku/search/loans zachowują dotychczasową datę księgowania.
  LEFTJOIN 1:1 nie mnoży80/20splitu. Splitapprovalworkflow pozostaje etapem2/4.
- Płatność tworzona z dokumentu zachowuje jawną ręczną datę księgowania; nie kopiuje
  sale_date dokumentu jako daty zakupu. Późniejsze evidence-based dopasowanie to etap5.
- UI nie zgaduje znaczenia starych dat. Nowa korekta wymaga potwierdzenia nieznanej
  daty księgowania, zamraża sprawdzony snapshot i po409 zachowuje wartości, ale wymaga
  zamknięcia/odświeżenia przed nową decyzją.

## Testy i przegląd

- TDD: początkowe9RED/1existingforeign404PASS→10GREEN; raporty2RED→GREEN; UI5RED→GREEN.
  Rozszerzone149backendPASS: nowe daty, granica miesiąca, split80/20, stale/foreign,
  import/loan/allocation guards, raceedit/delete, no-op, genericdate divergence,
  stare budżety/search/Actualpins i lineage migracji.
- Przed review:416frontend/lint/types/buildPASS,105E2E+1expectedskipPASS, desktop1440/
  mobile375; nowy scenariusz create→daty→409retain→purchasebasis, a11y/nooverflowPASS.
- Jedno niezależne whole-change review ses_e5ccc37e3ffeA4gw1JvV5CC2p6: Critical0,
  Important1 cross-ownerfinancecache, Minor1 same-session auth refresh. Obie przyczyny
  potwierdzone,3regresjeRED→GREEN. Jawny sessionVersion zmienia się przy logowaniu/
  wylogowaniu/zmianie właściciela; provider ma osobny QueryClient i subtree per sesja.
  Stary request/mutation nie może zasilić nowej sesji; odświeżenie tego samego użytkownika
  nie dezaktywuje dialogu. Focusedfrontend14PASS/lint/typesPASS po poprawce.
- Freshbuild/fullE2E po review:105PASS+1expectedskip,375/1440. Build ma nieblokujące
  ostrzeżenie o516kB chunku i outDir poza projektem, bez ukrywania ostrzeżeń.
- Finalne6gate po poprawkach:1205backend/420frontendPASS, ruff/mypy/eslint/tscPASS.
  `verify-final.py` potwierdził dokładne testowane źródła i dist-final,105E2E+1skip oraz
  odrębny dowód migracji. Odbiór etapu1 zakończony, brak nierozwiązanych blockersreview.

## Migracja i odzyskiwanie

- Autogenerate `84f28fe23ab8` po `2f4b2c2a527c` tylko w owned schema
  `transaction_dates_stage1_test` w identity-checked localhost55432/finanse_test.
- Usunięty z wygenerowanej migracji niezwiązany drift indexów scheduleditems; upgrade
  zawiera wyłącznie nową tabelę i jej dwa indexy, bez UPDATE/backfill albo dotykania
  istniejących kolumn/indexów. Unitregresja wymusza ten zakres.
- Realny test na syntetycznej starej transakcji: oldrows/columns/indexesretainPASS,
  zerobackfillPASS, emptydowngrade/reupgradePASS, populateddowngrade odmówiony pod
  EXCLUSIVElock i zachowany head/metadata. Bez DROP istniejących tabel lub danych.
- Przyszłe wydanie wymaga osobnej zgody/migracji/backup/rehearsal. Stary backend nie
  rozumie dat zakupów i mógłby przesunąć explicitbooking przez legacy date edit;
  nie wracać do starego kodu po użyciu metadanych bez zgodnego fence/forwardrepair.
  Nie usuwać adnotacji, by umożliwić rollback. Nie ruszać istniejącego release810.

## Dowody i następny krok

- Prywatne dowody: `/tmp/opencode/smart-categorization-20261103/` (test logs,
  migration-proof, dist-final i E2E outputs, final-gate oraz final-proof.json).
- Aktualny plan/ledger oznacza etap1 jako odebrany. Po localcommit następny
  etap to zatwierdzana zmiana/split kategorii zachowująca posting płatności; dalej
  propozycje LLM/pozycje paragonu/dopasowanie/batche historii. Żaden nie jest wykonany.
