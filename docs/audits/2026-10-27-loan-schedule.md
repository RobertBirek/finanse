# Q7 — plan rat i powiązania istniejących płatności

## Zakres

- Gałąź `feat/loan-schedule`, baza `0d52f9d` (lokalny slice walut kont).
- Zatwierdzony pierwszy slice: umowa, raty kapitał/odsetki/opłaty,
  ręczne przypisanie istniejących transferów PLN, również częściowe pokrycie.
- Metadane powiązania nie tworzą operacji ani nie rozksięgowują dawnych odsetek.
- Saldo księgowe nie jest potwierdzonym pozostałym kapitałem. Brak automatycznego
  włączenia do prognozy — istniejące harmonogramy nie są dublowane.
- Oryginalne dokumenty, produkcyjna historia, mapping Actual, Velo: bez zmian.
- Brak produkcyjnej migracji, importu dokumentu, merge/push/deploy.

Powyżej zakres etapu implementacji.28.10 po osobnej jawnej zgodzie main/push/deploy
i addytywna migracja zakończone w9db255b; import/korekty nadal niewykonane.
Raport wydania: `2026-10-28-release-loans.md` (backup/restore/CI/smoke/obserwacja PASS).

## Weryfikacja

- Frontend: świeże pełne Vitest **243/243**, ESLint i TypeScript PASS po poprawkach
  review i kontrastu; `git diff --check` PASS. Build PASS. Pełne E2E **59 PASS +1
  dotychczasowy celowy skip desktop**; w tym12 nowych przebiegów Q7 (desktop/mobile,
  dwa motywy, axe, partial/paid/unlink, błędy, pending, paginacja i kwoty formularza).
- E2E korzysta z istniejącego Chrome (`PLAYWRIGHT_CHROMIUM_EXECUTABLE`), serwuje
  lokalny build pod fikcyjną domeną i blokuje wszystkie zewnętrzne połączenia.
- Dozwolone zapisy E2E to wyłącznie kontrolowane mutacje metadanych umów/rat/linków;
  zapis transakcji/postingów stanowi błąd fixture. Dane są syntetyczne.
- Pierwszy przebieg wykazał rzeczywiste naruszenie kontrastu w jasnym motywie;
  poprawiono lokalne klasy statusu i panelu na istniejące mapowania motywów.
- Backend: targeted **32 PASS**, Ruff/mypy68 PASS. Obejmuje rzeczywiste dwusesyjne
  blokady link/edit/delete, limit pokrycia, zmianę waluty, stare ORM i link/unlink;
  migracja na izolowanej bazie zachowuje istniejące konta/transakcje/postingi.
- Oddzielny gate proxy/kontenerów **5 PASS**. Końcowy pełny backend **844 PASS**,
  8 proxy deselected w głównym przebiegu,2 znane warningi bibliotek,596,88s.
- Pierwszy pełny run ujawnił regresję PATCH transakcji (841 PASS/1 FAIL):
  po odświeżeniu ORM brakowało eager-load postingów do odpowiedzi. Dwie nowe
  regresje API RED→GREEN; loan+integrity47 PASS i lint/types PASS po poprawce.
  Pełny gate po poprawce zielony; nie wypchnięto ani nie wdrożono kodu z czerwonym testem.
- Niezależny review frontendu wykrył i zweryfikował poprawki stanu formularzy,
  blokowania podwójnych wyborów i jawnych błędów mutacji. Końcowy review całości
  zakończony bez ważnych blokad. Ponowny review ostatnich poprawek stale ORM,
  serializacji i procedury rollout również bez blokad; pełny gate nadal wymagany.

## Zgoda na wydanie28.10

- Użytkownik jawnie polecił main/push/deploy po pełnych testach. Obejmuje także
  gotowy slice walut kont; nie upoważnia do importów lub korekt księgi.
- Szyfrowany backup **6ebdef50** oraz izolowany restore: success/0. Świeży pełny
  frontend gate28.10:243 unit/59 E2E+1skip, lint/types/build PASS. Pakiet wdrożenia,
  rehearsal na kopii i końcowe wyniki będą zapisane w odrębnym raporcie wydania.
- Zastane dokumenty Velo z main zachowane w treści i nazwanym stash
  `pre-loans-release-velo-docs-20261028`; prywatny webapp/ nie wchodzi do Git.

## Poza tą iteracją

- Nowe płatności z właściwym rozksięgowaniem kapitału, odsetek i opłat.
- Uzgodnienie historycznych transferów i import źródłowego harmonogramu.
- Rzeczywisty pozostały kapitał potwierdzony bankiem, nadpłaty, przeliczenie planu.
- Rozdzielenie jednego przelewu na kilka rat, waluty inne niż PLN i wspólna prognoza.
