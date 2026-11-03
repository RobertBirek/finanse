# Wdrożenie kontraktu kwoty — d7a2432

## Zgoda i zakres

Po odbiorze przygotowania użytkownik odpowiedział „tak” na wdrożenie dokładnego
pakietu `d7a2432c69a203068d3f1298190b1118f6e0073b`, etykiet
`vision-openai-responses-2` / `vision-2` i kontrolowane wyłączenie/włączenie policy.
Zgoda nie obejmuje nowego wywołania AI, odtworzenia historycznych zadań, migracji,
importów, napraw finansowych ani usuwania dokumentów.

Przygotowanie: `docs/audits/2026-11-02-vision-amount-release.md`.
Poprzednia produkcja/rollback: `d9a5797a8de03f8868124e179d71a799c9c031ac`.

## Odbiór kontrolera wdrożenia

- Final gate źródeł: 1147 backend, 335 frontend, lint/types obu PASS; bez zmian źródeł.
- Świeży build/E2E: 93 PASS + 1 celowy skip. Dokładne obrazy backend/worker:
  202 pliki zgodne z Git i po 21 syntetycznych przypadków adaptera PASS, bez sieci/AI/DB.
- Backup `9832d2c6` i zainstalowany izolowany restore tego samego snapshotu PASS.
- Nowy kontroler: 23 offline guard tests PASS. Orkiestracja RED6fail/2pass → GREEN8;
  czysty verifier 15 PASS (początkowo brak modułu, nie deklarować 15 behavior-RED).
- Apply operations review `ses_e6186a627ffey0UmhqkB8yDnA5`: Critical/Important brak,
  PASS pod warunkiem świeżego preflight i powiązania hashy. Skrypty, YAML i źródło
  odziedziczonego browser smoke przypięte w deployment-package/apply-review-proof.
- Reviewer nie wykonywał live weryfikacji, nie oceniał semantyki zewnętrznego CLI
  ani źródła browser smoke. Kontroler używa istniejącego, wcześniej sprawdzonego
  CLI domenowego; główny agent przeczytał GET-only browser script i przypiął hash.
  Brak niezależnego ponownego review odziedziczonego browser source pozostaje minor.

## Zaplanowane zabezpieczenia

Jednorazowy marker przed pierwszym CAS; brak automatycznego powtarzania apply.
Preflight sprawdza dokładne źródła/obrazy/render, zgodę, backup nie starszy niż godzinę,
active-release, kontenery, wszystkie dane/originals/policy, kolejki i brak aktywnych jobów.
Drift blokuje procedurę; nie zastępować baseline lub oczekiwanego epoch w ciemno.

Policy: enabled/epoch2/oldfingerprint → CAS disabled/epoch3 → spójne obrazy+etykiety
→ weryfikacja disabled → CAS enabled/epoch4/newfingerprint. Istniejący operator CLI
wykonuje oba audytowane przejścia. Verifier pozwala tylko na dokładne przejścia policy,
ich audyty i policzone własne audyty anonimowego auth; reszta danych/plików bez zmian.

Rollback po potwierdzonym pause: znany disabled3 lub enabled4/newfingerprint; w drugim
przypadku CAS disable4→5. Odtworzyć stare obrazy/etykiety, potem enable przez świeży CAS
3→4 lub5→6. Nie resetować epoch, nie cofać DB i nie odtwarzać jobów. App-only rollback
ma osobną blokadę: nie uruchomi się przy aktywnym vision. Nieznany CAS/state zatrzymuje
automatyczne działania do ręcznego wyjaśnienia.

## Wynik

- [x] Zatwierdzony apply **sh_19e7ee38b0019uL7GbHcVPA19B** zakończony exit0,
  verified.json PASS; bez rollbacku. Trzy usługi d7a2432 i nowy kontrakt aktywne.
- [x] HTTPS/assets/auth i ścisła weryfikacja danych PASS. Policy włączona/epoch4,
  fingerprint `487086caeac2cce1a7a7724d397bf103865f6b359f94e290042faf6769f91553`.
  Dwa oczekiwane audyty przejść policy i cztery własne audyty anonimowego auth;
  brak innych zmian danych użytkownika/ledger/doc/job/usage/originals/schema/dataIDs.
- [x] Read-only browser375/1440 PASS: brak błędów strony, overflow, zewnętrznych origin
  i mutacji; chronione trasy przekierowują do login. Osiemnaście odpowiedzi401
  zaobserwowanych w browser smoke, łącznie22 oczekiwane własne security audyty z API smoke.
- [x] Ponad pięć minut obserwacji/9 próbek PASS. Atomowe active-release zapisane
  `2026-11-03T06:10:33.419581+00:00`; exact imageIDs/OCIrevision/contract zgodne z live.
  Final read-only verification PASS: policyenabled/epoch4, health/loginHTTPS200,
  schema/userdata/doc/job/usage/ledger/originals i dataIDs bez nieoczekiwanych zmian.

Read-only browser + finalize **sh_1a002b28c001mPqQ2RJzh2TLlE** zakończone exit0,
rollbackfalse. Odczytano browser-smoke.json/finalized.json i zapisano świeży
final-readonly-proof.json. Produkcyjny override: compose.deployed.yaml w pakiecie d7a2432.
Stare obrazy/override d9a5797 i policy-aware warunki rollbacku zachowane.

Dowody: `/tmp/opencode/vision-amount-deploy-20261102/`.
Agent nie wykonał żadnego nowego AI/OCR, retry, uploadu, migracji lub importu.
Kolejny krok użytkownika: odświeżyć stronę i jawnie kliknąć PonówAI jeden raz na istniejącym
dokumencie, bez reuploadu. Nie twierdzić, że poprawność jego odczytu już potwierdzono.
