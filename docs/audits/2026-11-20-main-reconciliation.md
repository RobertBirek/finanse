# Uzgodnienie `main` — 2026-11-20

## Punkt odniesienia

Lokalny `main` (`593a232`) nie zawierał własnych commitów względem GitHuba.
Pobrany `origin/main` (`86c6870`) był o 57 commitów do przodu i miał
[zielone CI](https://github.com/RobertBirek/finanse/actions/runs/44728075913):
statyka, osiem grup backendu, bramka kompletności i frontend z testami
przeglądarkowymi. Lokalny `main` zaktualizowano metodą fast-forward.
Pomocniczy checkout przełączono na ten sam `main`, bez usuwania jego gałęzi.

## Rozliczenie pozostałych zmian

| Zmiana | Decyzja |
| --- | --- |
| Dawne gałęzie dokumentów, bilansów, finansów i infrastruktury, których tip jest przodkiem `main` | Już zintegrowane; nie tworzymy pustych merge'ów. |
| Lokalna kopia dawnego obiegu finansowego dokumentów | Zmiany CI, zależności, izolacja testów i narzędzia developerskie są na `main` w tej samej lub nowszej postaci. Wcześniejsze operacyjne prace A2 oraz historyczne dowody nie są brakującą funkcją aplikacji ani kandydatem do publikacji. |
| Trzy starsze commity wyszukiwania i CI w pomocniczym checkoutcie | Zastąpione skonsolidowaną wersją `41fe650` i późniejszymi poprawkami na `main`. |
| Pięć lokalnych wersji dokumentacji bilansu otwarcia | Stash przypięty lokalną referencją `refs/archive/main-reconciliation/2026-11-20-opening-balance-drafts`; nie jest to zdalna kopia zapasowa. Dokumentacja na `main` uwzględnia późniejszą implementację i odbiór; nie zastępujemy jej wersją z etapu planowania. |
| Nowsze lokalne dokumenty preflightu i narzędzi frontendowych | Prototypy i diagnoza z warunkami STOP pozostają lokalnie. Nie potwierdzają gotowości do wdrożenia. |
| Zmiany izolacji renderera Compose | Rzeczywisty, ale niezacommitowany przyrost operacyjny. Zachowany w zastanym worktree; wymaga osobnej weryfikacji i odbioru. |
| [PR #11](https://github.com/RobertBirek/finanse/pull/11) — Node 24.22.3 | Zaktualizowany do `86c6870` bez przepisywania historii. [CI dla `12d355a`](https://github.com/RobertBirek/finanse/actions/runs/44738125559) zakończyło się wynikiem 11/11, łącznie z audytem zależności i E2E. Scalony jako `481178b` z tym samym drzewem. Diff aplikacyjny ogranicza się do wersji Node w CI i obrazu etapu build frontendu. |

Synchronizacja Git nie jest wydaniem. Nie zmieniano konfiguracji serwera,
danych, migracji ani działających usług.
