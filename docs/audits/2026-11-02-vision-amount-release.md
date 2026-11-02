# Przygotowanie wydania kontraktu kwoty — bez wdrożenia

## Zakres zgody

Użytkownik zatwierdził przygotowanie pakietu `d7a2432`, backup/restore i kontrolę
wersji prompt/schema oraz polityki AI. **Nie zatwierdził wdrożenia, zmiany konfiguracji
produkcyjnej/polityki ani kolejnego wywołania AI.** Nie uruchamiać apply/replay/importów.

- Kandydat: `d7a2432c69a203068d3f1298190b1118f6e0073b`.
- Produkcja: `d9a5797a8de03f8868124e179d71a799c9c031ac`.
- Źródła kandydata zgodne z końcowym gate: 1147 backend, 335 frontend, lint/types obu PASS.
- Read-only preflight: policy enabled/epoch2, settings fingerprint zgodny z DB,
  brak pending/processing document jobs. To punktowy wynik, nie trwała gwarancja.

## Stan przygotowania

- [x] Tożsamość źródeł i produkcyjnych obrazów sprawdzona bez wypisywania sekretów.
- [x] Świeży zaszyfrowany backup `9832d2c6`; zainstalowany izolowany restore drill
  tego samego snapshotu success/exit0. Brak resetu start-limit i ponowienia usług.
  Poprawiono wyłącznie odczyt dowodu: parser nie uwzględnił uppercase `Snapshot`.
- [x] Świeży build frontendu/E2E: 93 PASS + 1 celowy skip, source/dist provenance PASS.
- [x] Pakiet `ops/prepare_release.py` pod `/opt/finanse/webapp/releases/d7a2432/`;
  immutable obrazy, OCIrevision zgodne, 202 pliki backendu w obu obrazach zgodne z Git.
  Dokładne obrazy backend/worker: po 7 valid, 13 invalid i 1 null przypadków PASS,
  MockTransport/networknone/nonroot, zero AI i połączeń z DB.
- [x] Bazowy Compose różni wyłącznie obrazy/build. Osobny overlay propozycji zmienia
  tylko dwie etykiety backend/worker. Render wyłącznie w pamięci; dowód jako HMAC.
- [x] Read-only porównanie po prepare: active-release, app/data container IDs,
  źródła danych, schema, oryginały, policy/audits i live kontrakt bez zmian.
- [x] Scoped operations review `ses_e619ea852ffepxqm1yhCDfEndA`: PASS do przedstawienia
  zakresu wdrożenia użytkownikowi, NIE zgoda na rollout ani dowód działania faktury.
  Critical/Important: brak. Minor: odziedziczony napis „diagnostic” w logu prepare;
  nieszkodliwa nazwa etapu, odroczona. Checklist raportu uzupełniony po review.

Obrazy backendu i workera są content-identyczne (wspólny runtime/source):
`sha256:18aaf98a33235875415164ee109f753ad08dfb847a7ed47b6ef93ebe1358f195`.
Pełna mapa wszystkich obrazów, digest-pinned override i rollback do d9a5797 znajdują
się w pakiecie oraz prywatnym `images.json`. Nie używać mutable tag jako jedynego
powiązania rewizji.

## Wersjonowanie kontraktu — propozycja, nie zmiana produkcji

Obecnie: `DOCUMENT_VISION_PROMPT_VERSION=vision-openai-responses-1`,
`DOCUMENT_VISION_SCHEMA_VERSION=vision-1`. Reguła kwoty i instrukcja zmieniają kontrakt,
więc przyszłe wydanie nie powinno udawać tej samej tożsamości konfiguracji.

Proponowane etykiety: `vision-openai-responses-2` i `vision-2`, wyłącznie dla backendu
i workera. Osobny, nieużyty overlay ma zostać dołączony do pakietu przygotowawczego.
Przygotowanie ani renderowanie overlay NIE upoważnia do jego zastosowania.

## Warunki przyszłego wdrożenia

Wymagana osobna zgoda na dokładne obrazy/SHA, dwie etykiety konfiguracji i audytowaną
zmianę polityki. Same obrazy z niezmienioną etykietą to pakiet bazowy, nie kompletny
zatwierdzony rollout kontraktu.

1. Ponownie sprawdzić brak aktywnych zadań i driftu konfiguracji/obrazów/danych oraz
   aktualność backupu. Przy jakimkolwiek drift nie podmieniać baseline w ciemno.
2. Po osobnej zgodzie: istniejącym serwisem policy CLI wyłączyć vision z CAS na
   rzeczywisty epoch. Dla obecnego stanu 2 oczekiwany wynik to disabled/epoch3.
3. Dopiero wtedy zastosować spójne obrazy i overlay etykiet, bez migracji/importów.
   Sprawdzić zgodność konfiguracji backendu/workera i brak ruchu do AI.
4. Po odbiorze włączyć vision istniejącym policy CLI z CAS na aktualny disabled epoch
   i nowy fingerprint; dla niezmienionego scenariusza wynik to enabled/epoch4.
   Nie wywoływać AI w smoke i nie odtwarzać historycznych zadań.
5. Sprawdzić HTTPS/assets/auth, oryginały/dane, identyfikatory usług danych, audyty
   policy i stabilność; dopiero po odbiorze aktualizować active-release atomowo.

Rollback musi obejmować poprzednie obrazy **i** stare etykiety/fingerprint: wyłączyć
vision przez CAS na faktyczny epoch, odtworzyć poprzednią konfigurację aplikacji,
odebrać i ponownie włączyć stary kontrakt przez CAS. Epoch jest monotoniczny:
nie przywracać go do2, nie cofać DB i nie uruchamiać zadań/AI jako „naprawy”.
Jeśli CAS zawiedzie, zatrzymać procedurę; nie resetować oczekiwanego epoch automatycznie.

## Dowody

Prywatny katalog: `/tmp/opencode/vision-amount-release-20261102/`.
Preflight, gate/source proof, frontend-build-proof, backup-proof, image-content-proof,
amount-smoke, contract-proposal, preparation-unchanged-proof i operations-review.
10 offline guard tests i syntax PASS. Przygotowanie nie posiada CLI apply/finalize;
nie utworzono artifactu deployment approval. Surowe sekrety/render Compose nie
trafiają do raportu. Zmiana wersji/policy to tylko propozycja, nadal niezatwierdzona.

**Brak wdrożenia i brak dowodu prawidłowego odczytu konkretnej faktury.**
