# Wdrożenie wskaźnika AI/OCR i globalnego toastu

## Zgoda i zakres

Użytkownik po odbiorze lokalnego commitu `69b6f3d450fef83b0e583465aed4a2e0a680f434`
odpowiedział „tak, wdrażaj na produkcję”. Zgoda obejmuje spójny backend/worker/frontend,
backup i izolowany restore oraz weryfikację. Bez migracji, zmian polityki/promptów/modeli,
nowych wywołań AI/OCR, retry, reuploadu, importu lub napraw historycznych danych.
Nie jest potrzebne scalenie na host main — release powstaje z dokładnego zatwierdzonego Git SHA.

Poprzednia produkcja/rollback: `d7a2432c69a203068d3f1298190b1118f6e0073b`,
override `/opt/finanse/webapp/releases/d7a2432/compose.deployed.yaml`.
Policy enabled/epoch4, prompt/schema2 pozostają niezmienione; rollback do d7a2432
nie wymaga zmiany policy, bo konfiguracja i kontrakt są identyczne.

## Lista wykonania

- [x] Zweryfikować tożsamość zatwierdzonych źródeł i dowody gate/review:
  backend1151/frontend388/lint/types/build oraz E2E97PASS+1celowy skip.
- [x] Świeży backup i installed isolated restore tego samego snapshotu: e0963350,
  backup/restore success, exit0, ten sam snapshot, bez resetu startlimitów.
- [x] Przygotować pakiet przez `ops/prepare_release.py`, zachować stare obrazy,
  porównać cały render konfiguracji, przypiąć imageIDs i sprawdzić exactimage smoke.
- [x] Read-only operations review kontrolera/pakietu; hashbinding28artifactów.
- [x] Jednorazowy apply pełnego Compose, tylko backend/worker/frontend, no-deps/no-build.
- [x] HTTPS/assets/health/auth rejection, dane/originals/schema/policy/dataIDs, logi.
- [x] Browser375/1440 GET-only oraz minimum5min obserwacji; finalizacja active-release.
- [x] CHANGELOG/TASKS/JOURNAL i lokalny docscommit, bez push/mainmerge.

## Zabezpieczenia

Reużycie sprawdzonej procedury no-migration/no-policy. Prywatne dowody:
`/tmp/opencode/document-processing-deploy-20261103/`. Marker blokuje powtórne apply;
nieoczekiwany drift blokuje wdrożenie zamiast zastępować baseline. Backup musi mieć
mniej niż1h. Przed/po ten sam schemat, ledger, oryginały, user/doc/job/usage/policy;
wyjątkiem są policzone własne audyty odrzuceń anonimowego auth w smoke.
Przy błędzie apply powrót do poprzedniego override, bez cofania bazy/epoch/replay.
Zachować istniejący rollback d9a5797 oraz unrelatedVelo/Q7; brak sekretów w raporcie.

## Przygotowanie

Pakiet `/opt/finanse/webapp/releases/69b6f3d/` gotowy. Nowy pełny override
`compose.active.yaml` zachowuje całe dotychczasowe środowisko/sekrety/sieci/mounty;
render identyczny poza zatwierdzonymi obrazami/build. Trzy obrazy przypięte imageID.
W obu obrazach backend/worker wszystkie203pliki źródeł zgodne z Git, non-root/networknone.
Exactimage smoke nowego GET /documents/active i walidacji paginacji4casesEachImage PASS,
bez połączenia z rzeczywistą bazą, AI/OCR lub mutacji. Guardy kontrolera15offlinePASS.
Operationsreview ses_e5f5ffa59ffeFqwVyURlYZWlzF zakończony warunkowoApproved:
Critical0/Important0/Minor0. Hashbinding28plików kontrolera/pakietu zapisany w
operations-review-proof.json. Pozostaje wymagane potwierdzenie świeżego backupu i
installedrestore tego samego snapshotu przed apply. Backupcallback potwierdził e0963350;
one-shot apply uruchomiony jako sh_1a0a5b5210010c77nXK5rYMETq. Wynik i runtime
odebrane: exit0/verified.json PASS, rollback nie uruchomiony. Backend/worker/frontend
69b6f3d; schema/policy bez zmian. Pięć anonimowych APIodczytów odrzuconych401,
w tym nowy /api/documents/active; dokładne hashe plikówHTTPS zgodne zpakietem.
Browser375/1440 i5minobserwacji/finalize sh_1a0a67764001Gd4OTkGu8zB8id zakończone PASS.
Nie powtarzać apply/finalize/backup lub pełnego gate.

## Odbiór końcowy

- Ponad5min/10próbek kontroli PASS, rollback niepotrzebny.
- Browser375/1440: brak overflow/pageerror/foreignorigin/mutacji, fonty loaded,
  prywatne trasy przekierowują do login. Łącznie23oczekiwane własne audyty auth401
  (5API+18browser); brak pozostałych zmian danych.
- Active-release sfinalizowany atomowo `2026-11-03T09:09:22.312699+00:00`.
  Trzy usługi na dokładnym69b6f3d, override69b6f3d/compose.active.yaml;
  rollbackd7a2432/compose.deployed.yaml zachowany wraz z obrazami, d9a5797 także zachowany.
- Świeży `final-check.py` potwierdził zgodność runtimeimageIDs/OCIrevision/metadanych,
  schema92eef8e8086c/policyenabled/epoch4/promptschema2/danych/ledger/oryginałów/dataIDs,
  HTTPShealth/login200 i brak errorów/restartów. `final-readonly-proof.json` PASS.
- Gate tożsamości źródeł ponownie PASS; bez zmiany kodu po pełnym gate/review.

### Certyfikacja w uzgodnionym zakresie

| Kontrola | Wynik |
|---|---|
| Źródła1151backend/388frontend/lint/types/build/97E2E+1skip | PASS |
| Zewnętrzny CI | Nie dotyczy: lokalny gate przypiętegoSHA |
| Exactartifact/runtimeidentity | PASS |
| Schemat | PASS, niezmieniony; migracji nie wykonywano |
| Liveness HTTPS | PASS |
| Readiness zależności DB/Redis/worker (read-only) | PASS |
| Krytyczne trasy HTTPS/assets/authrejection | PASS |
| Sygnały operacyjne/obserwacja | PASS |
| Mutacje po zalogowaniu na produkcji | Wyłączone zzakresu: zeroAI/OCR/mutacji; lokalne integration/E2E PASS |

Werdykt: **GREEN w uzgodnionym read-only zakresie wdrożenia**, nie deklaracja
poprawnego odczytu prywatnej faktury. Użytkownik odświeża stronę; każda nowa próba
AI/OCR jest jego oddzielną decyzją. Bez pushu/scalania hostmain.
