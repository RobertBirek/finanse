# Szkice dokumentów: publikacja, pełne CI, blokada rollout

Data: 2026-11-17. **Nie wdrożono funkcji na produkcję.**

## Zgoda i publikacja

Użytkownik polecił push na main i wdrożenie, następnie jawnie zatwierdził
migrację `a6e52f41c9d0` po `efaf78432563`, po backupie i próbie restore,
oraz reaktywację Vision z nazwami/ścieżkami kategorii przy nowych odczytach.
Bez backfillu lub ponownego przetwarzania starych dokumentów.

Fast-forward bez force: b5fbc5e→cf3ae26→79a5fc9→39aceec.
Odrębne `git ls-remote` potwierdziło publikacje. Nie nadpisywano starego
lokalnego checkoutu main ani innych worktree.

## Poprawki rzeczywistych błędów CI

- Atrapa Vision nie zwracała wymaganego `category_key` przy nowym kontrakcie.
  Parametryczny test odtworzył brak pola. Odpowiedź stosuje teraz żądany schema
  i abstencję NULL. Walidacja produktu nie została osłabiona.
- Guard drzewa kategorii prawidłowo odmawiał nieznanej referencji nowego pola.
  Jawnie dodano obsługiwany FK, snapshot intentów i blocker pending.
  Cztery regresje RED→GREEN; unknown/foreign FK nadal blokuje.
- Playwright prefix-match „Sprawdź dane” obejmował nowe dłuższe akcje listy.
  Dokładne selektory zachowują pierwotny przepływ. Strict-mode RED→46E2EGREEN.
  Nie wyłączano testów ani nie zwiększano timeoutów przypadków.

## Dowody

Dokładna rewizja CI: `39aceecca4ab4f400eebfd0ee2fdb0a9e4dd6a10`.

CI: https://github.com/RobertBirek/finanse/actions/runs/44074810399

`gh run watch --exit-status` zwróciło0. Odrębne `gh run view`:
completed/success, **11jobówSUCCESS**, łącznie ze zbiorczym verifierem raportów.
Rzeczywiste artefakty JUnit backendu:

| Grupa | Przypadki | Failures/errors/skips |
|---|---:|---:|
| legacy | 84 | 0/0/0 |
| ordinary-1 | 488 | 0/0/0 |
| ordinary-2 | 440 | 0/0/0 |
| ordinary-3 | 414 | 0/0/0 |
| ordinary-4 | 500 | 0/0/0 |
| ordinary-5 | 461 | 0/0/0 |
| ordinary-6 | 461 | 0/0/0 |
| proxy | 14 | 0/0/0 |
| **Razem** | **2862** | **0/0/0** |

Frontend CI unit/build/browser PASS. Lokalnie431offline (documents+guard),
719Vitest/115plików, kanoniczne lint/typecheck/kolekcja oraz dodatkowy Ruff/mypy
operatora PASS. Pełne lokalne E2E205PASS/1zastany planowy skip desktopowego
wariantu mobilnego kalendarza w5.6min. Wcześniejszy run przerwany limitem
narzędzia240s nie jest liczony jako dowód sukcesu.

Wąski readonly review poprawek:0Critical/0Important/0Minor.
Znane ostrzeżenia: passlib/crypt, frontend chunk>500kB, komunikaty platformy
GitHub o Node24/Ubuntu26. Nie maskowano błędów CI tymi ostrzeżeniami.
Dowody lokalne: `/tmp/opencode/document-auto-finance-drafts-ci-fix/`.

## Bramka wdrożenia: BLOCKED

Brak niezależnie zatwierdzonego pliku inventory i jego SHA256, wymaganych
przez `/deploy` oraz `docs/operations/backup-restore.md`.
Preflight ma tylko `--check`, nie issuer. Nie wolno wygenerować sobie zgody
z bieżących obserwacji ani zmienić active metadata, by kontrola przeszła.

Read-only przejrzano wyłącznie bezpieczne pola metadanych i klucze/nazwy plików
archiwum poprzedniego rollout. Historyczne containers-before/config-hashes nie są
kompletną zatwierdzoną deklaracją obecnego środowiska. Nie adoptowano ich jako inventory.

Nie wykonano Dockerbuild/up/restart, rzeczywistego upgrade bazy, restore/policy
transition ani wywołań AI na danych użytkownika. Nie ma świeżego dowodu runtime
tej funkcji. Zielone CI **nie jest** zielonym odbiorem produkcyjnym.

Następny krok: niezależny operator przygotowuje i zatwierdza inventory/hash.
Potem preflight dokładnej rewizji pod deploylock, backup/restore/retencja,
wersjonowane obrazy i offline nonrootgate, zatwierdzona migracja, spójne trzy
usługi, kontrolowana reaktywacja Vision i runtime/rollback odbiór.
