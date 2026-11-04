# Etap 3B — propozycje kategorii AI i przegląd: odbiór lokalny

## Status

**Odebrano wyłącznie lokalnie.** Zatwierdzony plan `becb54c`; implementacja
native/TDD. Jeden niezależny whole-review zakończony: Critical0/Important0/Minor0,
bez żądanych zmian kodu. Pełny końcowy gate na zamrożonych źródłach zakończony:
1406backend/456frontend/lint/types/freshbuild/127E2E+1expectedskip PASS.
Backend `8a9560f`, UI `0347e58`; zgodność źródeł i proofów potwierdzona przed i po commitach.

Spec: `docs/superpowers/specs/2026-11-04-reviewed-ai-categorization-design.md`.
Plan: `docs/superpowers/plans/2026-11-04-reviewed-ai-categorization.md`.
Baseline przed zmianą: backend3A `28ce7f0`, UI `2b960ee`, plan `becb54c`.

## Zakres i ograniczenia

- Wyłącznie nowe ręczne, zaksięgowane, nieskategoryzowane wydatki PLN z jawnym markerem.
- Oddzielne zgody: wysłanie opisu/katalogu do AI oraz ludzkie przypisanie kategorii.
- Reguła ma pierwszeństwo. Brak skanowania dawnych transakcji/eventów i backlogu po OFF.
- Jedna płatna szansa dispatch na job. Niepewny commit/timeout/crash nie uprawnia do
  kolejnego calla; rezerwacja zostaje. Faktyczne późne usage nie przywraca publikacji.
- Provider otrzymuje opis i własne ścieżki kategorii z lokalnymi kluczami. Bez UUID
  płatności/kont, kwot/sald/dokumentów, SQL i narzędzi; strict output nie daje praw zapisu.
- Dopiero preview + rzeczywisty humanapply tworzą chroniony stan manualny i approved_llm
  origin. Kwota, strona kontowa, dokumenty, daty, source i bilans postings pozostają.
- UI zatwierdza skończony obejrzany wybór peritem, nie bulk SQL. Unknown zatrzymuje
  dalsze komendy, retry zachowuje body/key; nowe sesje nie przyjmują dawnych odpowiedzi.
- Nowa kategoria: osobny katalog/create i osobne manualapply, bez batchapply lub splitu.
- Finansowe AI domyślnie OFF; brak realnych providerów/OCR, historii, wdrożenia,
  produkcyjnej migracji, merge main lub push w tym odbiorze.

## Dowody etapowe

Wszystkie artefakty w `/tmp/opencode/category-proposals-20261104/`.

| Obszar | Wynik kandydata |
| --- | --- |
| Foundation/consent/storage/projection | 75 focused PASS; static4checks PASS |
| Generation/packet/usage/races i regresje3A | 125 focused PASS |
| Końcowy kandydat humanreview/consent/worker/races/migracja | 74 focused PASS |
| Frontend pełny + lint/tsc | 456 PASS, lint/types PASS |
| Nowe browsercases, obie szerokości i projekty | 16 PASS; main-area Axe, keyboard, nooverflow |
| Pełne E2E kandydata | 127 PASS + 1 expected skip |
| Świeży końcowy build + pełne E2E po review | Exact-source build PASS; 127 PASS + 1 expected skip |
| Cały końcowy backend/frontend/static/build/E2E | 1406backend/456frontend/static4checks/build/127E2E+1expectedskip PASS |
| Exactsource/dist/migration hash | PASS, final-proof.json; identyczne bytes po commitach |

Nieudane próby są zachowane: pierwsza foundation próba przerwana limitem czasu,
poprawnie ponowiona z timeout0; późniejszy szerszy run85PASS/2fail dotyczył brakującego
importu `text` w nowych testach współbieżnych. Import poprawiono; oba rzeczywiste
global-policy/dispatch admissions następnie przeszły. Nie są to przemilczane sukcesy.

## Migracja i retencja

Revision `243aa1d9461c`, po `c06315385b4e`. Wygenerowana i sprawdzona raz w nowym
schemacie `reviewed_category_suggestions_3b_test`, wyłącznie lokalna baza `finanse_test`
z bezpiecznym bindingiem kontenera na loopback55432. Autogenerate drift starych indeksów
scheduled items odrzucono jako niezwiązany.

Pięć nowych tabel i nullable proposalFK/warunkowe checki origin; brak backfillu.
Porównanie projekcji **starych kolumn** (nie całego JSON z nowym polem NULL) potwierdziło
zachowanie dawnych rekordów/kolumn/indeksów, także manual/approved_rule origins. Empty
downgrade/reupgrade PASS. Populated downgrade odmawia przed destrukcyjnym DDL, pod
lockami wszystkich nowych tabel i origin.

Proof `migration-proof.json` będzie porównany z końcowym hashem migracji; nie powtarzać
niezmienionego rehearsal/seed. Zmiana ORM `none_as_null=True` dotyczy kodowania PythonNone
do SQLNULL, nie DDL. Po zapisaniu approved_llm danych nie wolno wdrażać starego backendu3A
bez osobnej procedury zgodnego rollbacku. Ten raport nie jest zgodą na produkcyjne DDL.

## Decyzje wykonawcze

1. Zamiast powtarzać niezmieniony pełny baseline wykorzystano sprawdzony exact-source
   proof3A. Ryzyko dryfu ogranicza świeże porównanie hashy przed pierwszą zmianą.
2. Niezależny pakiet/adapter przygotowywano podczas długiego gate foundation; żadnych
   równoległych testów zapisujących do publicznego schematu finanse_test.
3. Builder pakietu wymaga jawnego marker_id; LedgerContext nie ma autorytatywnego
   ustawienia markera. Ryzyko błędnej interpretacji oznacza odmowę lub zmianę sygnatury,
   nie zgadywanie kategorii po nazwie/postingu.
4. Pochodzenie prompt/schema w zatwierdzeniu to hashe faktycznie zapisanego requestu,
   a nie etykiety bieżącego kodu. Ryzyko: do korelacji operator używa hashy, nie nazwy wersji.
5. Paginacja jest dostępna poza frozenreview i czyści wybór przed potwierdzeniem.
   Koszt: przed przejściem do kolejnej strony trzeba zakończyć/porzucić bieżący przegląd.
6. Productcommits następują po pełnym gate (AGENTS testy przed każdym commitem).
   Koszt: większe commity backend/UI; małe kroki i wyniki pozostają w ledgerze.
7. Whole-review czyta zamrożony working diff po becb54c, bo natywny review-package
   odmawia pustego zakresu commitów. Cały product diff zapisano oddzielnie, nowe pliki
   mają intent-to-add; Velo/Q7 wykluczono. Koszt: reviewer ocenia snapshot, nie commit SHA.

Reviewer `ses_e593852d3ffe24k0l8Y2ebvh2V` nie zgłosił żadnych Critical/Important/Minor.
Nie było rundy poprawek ani re-review. Jego „Declined to judge” rozstrzygnięto jawnie:

8. Realne modele/providerzy, produkcja i historia pozostają osobnymi bramkami zgody.
   Koszt: ten odbiór nie potwierdza zgodności konkretnego aktywowanego modelu ani wydania.
9. Przyjęty kod3A sprzed becb54c nie był ponownie reviewowany; nowe interfejsy mają
   regresje i obowiązkowy pełny finalgate. Koszt: nie certyfikujemy cudzych dawnych defektów.
10. Audyty Velo/Q7 pozostają nietknięte i poza oceną. Koszt: ich poprawność nie jest
    przedmiotem tego odbioru.

11. Zatwierdzony plan nakazuje zachować branch/worktree i nie wydawać zmian; to istniejący
    wybór „keep as-is”, bez ponownego pytania o merge/push. Koszt: integracja pozostaje
    osobną decyzją, a poprawność produkcyjnego rollout/rollbacku nie jest tu potwierdzona.

Dowody końcowe: gate `sh_1a6cc2a4e001ExTlQVyinPMfVK` zakończony sześcioma kodami0,
1406backend z8wcześniej zadeklarowanymi deselected (bez skipów backendu),456frontend.
Build/E2E `sh_1a6ce773e001Y6siQ9cks4jxbf`:127PASS/1expectedskip. Ostrzeżenia zależności
FastAPI/Starlette/passlib nie są ukryte; brak niezaliczonych testów. `verify-final.py`
porównuje bieżące źródła z gate i buildem oraz końcowy hash migracji z zachowanym
rehearsal; nie uruchamia ponownie godzinnego suite. Oryginalny pełny diff review i ledger
zostają w `execution-ledger/` prywatnego katalogu dowodów. Odroczonych Minor: brak.

## Następne bramki

Lokalny odbiór zamknięty. Realna aktywacja modelu i ewentualne wydanie wymagają osobnego
uzgodnienia i procedury, w tym kompatybilności konkretnego modelu, jawnego zakresu
zgody/limitów oraz spójnego rollout/rollbacku. Etap4 paragonów i przetwarzanie historii
nie zostały wykonane. Branch/worktree i unrelated Velo/Q7 zachowane.
