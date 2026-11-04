# Etap 3A — zatwierdzone reguły kategoryzacji, odbiór lokalny

## Zakres i zgoda

Użytkownik zatwierdził politykę hybrydową, następnie pełny plan5e679b5 słowem „tak”.
Plan: `docs/superpowers/plans/2026-11-04-approved-categorization-rules.md`.
Spec: `docs/superpowers/specs/2026-11-04-hybrid-categorization-design.md`.
To wyłącznie3A: reguły deterministyczne i nowe ręczne wydatkiPLN.3B z propozycjamiLLM
i przeglądem partii pozostaje osobnym krokiem. Nie uruchomiono historii, AI/OCR,
providerów, migracji/wdrożenia produkcyjnego, mainmerge ani push.

## Stan odbioru

**ZAKOŃCZONE LOKALNIE.** Pełny gate po whole-review i poprawce account-history:
`sh_1a5f2a35a001VtfDN4s5439AGc`,1303backend/439frontend/lint/typesPASS. Freshbuild,
111E2E+1expectedskip oraz2dodatkowebrowseroriginPASS. `verify-final.py PASS` potwierdził
identyczne źródła/dist,6wyników gate i hash sprawdzonej migracji. Nie ponawiać suite.
Kod: backend `28ce7f0`, UI `2b960ee`. Oba commity zapisano po końcowym gate;
zatwierdzone źródła pozostają identyczne z testowanym kandydatem.
Wcześniejszy publiczny1266PASS dotyczy zaimportowanego etapu1 implementacji, nie jest
dowodem całości późniejszego kandydata. Nie używać go zamiast końcowego gate.

## Kontrakt implementacji

- Własne ustawienie ID kategorii technicznej, reguły domyślnie wyłączone. Brak zgadywania
  po nazwie/null/rodzicu oraz brak skanowania dawnych transakcji przy włączeniu.
- Exactdescription: NFKC/casefold/redukcja białych znaków, bez regex/substring/fuzzy.
  Szkic → niemutujący podgląd → jawna zgoda na przyszłość. Pause/edit zmienia wersję,
  nowa zgoda ma osobny niezmienny receipt. Nie zastępujemy zgody aktywnej wersji w miejscu.
- Jedno zdarzenie zapisane atomowo przy utworzeniu płatności, zaobserwowane ustawienia/
  ruleversion w jednym zapytaniuMVCC. Event nie ma FK do obserwowanej reguły/receipt:
  takie FK mogłyby wziąć późny lock po lockach źródłowego konta/kategorii.
- Dispatcher czyta tylko eventtable, Redis przenosiID. Claim/commit poprzedza ledger;
  lease/CAS/attempts/recovery nie uruchamia terminalnych zdarzeń ponownie. Błąd Redis
  nie zużywa próby. Writer/audit rollback, następnie osobna krótka transakcja failureCAS.
- Worker ponownie sprawdza właściciela, aktywny marker, grant/wersje, taxonomyhash,
  snapshot płatności i ochrony księgi. Brak nadpisywania manualstate/origin, importów/
  Actualmapping, pending, FX/refund, pożyczek lub alokacji dokumentu.
- Kwoty tylko w postings; płatność i każdy mappedcolumn strony kontowej zachowane.
  Brak nowego wydatku, zmiany salda, dat, source lub fingerprintówActual.
- Osobnyorigin `approved_rule` z receiptFK/hash nie udaje ręcznej decyzji. Manualny
  apply zapisuje manualstate/origin i audyt poprzedniej zgody. Stary manualstate chroni
  bez backfillu. Opaque snapshotv2 uwzględnia origin.
- UI w istniejącym `/settings/finances/categorization`: marker/off, szkic/podgląd/
  zatwierdzenie, pause/edit/retire, ostrożne retry tym samym kluczem.409 zachowuje pola,
  wymaga odświeżenia i nowego przeglądu. SessionVersion izoluje cache/odpowiedzi.
- Origin jest read-only projekcją, ładowaną zbiorczo dla list/search/detail/account-history;
  nie dodaje mappedcolumn transakcji ani N+1. Watcher odświeża finanse z eventtable,
  poll tylko przy aktywnych zdarzeniach, bez samoinwalidacji/pętli pustej kolejki.

## Dowody przed pełnym gate

- Initial9policyRED404→GREEN; manual-origin/referenceguardRED→GREEN.
- RuleeventRED404→13GREEN; aktualna integracja86focusedPASS i następnie32worker/
  security/racesPASS: polityka, ręczna ochrona, ledger identity, mappings/FX/refunds,
  replay/lease/failureCAS/broker, brak późnego FK locka i oba porządki pause/worker.
- Real-session productionCSRF dla settings i wszystkich mutacji regułPASS.
- SQL `approved_version=NULL` odtworzył lukę checka, poprawiony `IS NOT NULL`.
  Limit konfiguracji ponad pojemność DB: RED→GREEN przez walidacjęle2000.
- Frontend439PASS, lint/tsc/buildPASS,4noweE2E375/1440PASS.
- PełneE2E:111PASS +1oczekiwanyskip (desktop wariantu mobilecalendar), bez realnejAPI.
  Dodatkowy browser acceptance na tym samym buildzie:2PASS375/1440, ruleorigin → jawna
  ręczna korekta → manualorigin, bez drugiej płatności; screenshot obejrzany375px.

## Whole-review i jedna poprawka

Reviewer `ses_e5a1dba5effeyjHjQdXkOy7cvt`: Critical0/Important1/Minor0.
Odtworzono brak origin w `/accounts/{id}/transactions` bez wcześniejszej projekcji
w identitymap. `test_account_history_loads_rule_origin_without_a_prior_search_projection`
RED→GREEN; endpoint używa wspólnego batchedloader. Nie zlecano drugiego review.
Końcowy pełny gate po tej poprawce:1303backend/439frontend/lint/typesPASS; exactsourcePASS.

Reviewer świadomie nie oceniał3B/providerów/historii/splitautomatyzacji (poza zakresem),
produkcji/liveRedis (brak zgody), cudzych audytów/brandingu oraz nie uruchamiał suite
(read-only). To nie dowód działania produkcyjnego; finalne wykonanie testów należy do
implementera. Brak odroczonych minorów z review.

## Migracja

`c06315385b4e` po `2268bca97cb8`,4nowe tabele, bez backfillu lub zmiany dawnych kolumn/
wierszy/indeksów. Autogenerate wykrył unrelated drift indeksów scheduled_finance_items;
usunięto go z tej migracji przed zastosowaniem. Nie luzowano manual-only checka etapu2.

Wyłącznie nowy owned schema `approved_rules_stage3a_test` w lokalnym `finanse_test`:
upgrade/retention/no-backfill/emptydowngrade+reupgrade/populateddowngradeguardPASS.
Downgrade blokuje wszystkie4tabele przed sprawdzeniem danych, odmawia usuwania zgód,
origin lub kolejki. Nie regenerować migracji ani nie powtarzać seed w tym schemacie.

## Artefakty i ograniczenia

Dowody prywatne: `/tmp/opencode/categorization-rules-20261104/` — RED/GREENlogs,
migration-proof.json, review.patch/source/package, acceptance-source.json, dist,
e2e-full.log, origin-acceptance2.log oraz końcowe results/sourceproof/verify-final.py.
Natywne narzędzie wywołania slashcommands nie jest udostępnione; użyto guarded
worktree-local odpowiedników `/test`, `/lint`, `/typecheck`, `/migration`, `/migrate`.

Pre-existing pełny Axe desktopowego brandu zgłasza label-content-name-mismatch dla
Personal<br>Advisor poza zmienianą powierzchnią. Nowy main-area scan wszystkich reguł
i dotychczasowe globalne taggedscansPASS; nie naprawiano unrelated brandingu. Pozostają
też wcześniejsze ostrzeżenia bibliotek i bundle-sizewarning, nie błędy nowego odbioru.
Cudze pliki Velo/Q7 pozostają nietknięte.

## Użycie po osobno zatwierdzonym wydaniu

1. Ustawienia → Finanse → Kategoryzacja: wskaż kategorię techniczną, potwierdź przyszły
   zakres i zapisz włączenie reguł. Samo wejście na stronę niczego nie aktywuje.
2. Dodaj regułę istniejącej kategorii, zapisz szkic, sprawdź oryginalny i znormalizowany
   opis oraz docelową ścieżkę, jawnie zatwierdź dla przyszłych wydatków.
3. Po zmianie markerID, celu/nazwy/struktury kategorii wstrzymaj lub edytuj regułę
   i ponownie przejrzyj/zatwierdź. Nieaktualny grant nie zostanie zastosowany.
4. Historia pokaże przypisanie przez regułę. Ręczna korekta, także powrót do markera,
   ma pierwszeństwo i blokuje późniejszą automatyzację tej płatności.

Produkcja nadal działa na poprzednim wydaniu; powyższy opis nie oznacza wdrożenia.

## Decyzje wykonawcze i ich koszty

W kolejności decyzji zapisanych w ledgerze:

1. Aktywnej zgody nie zastępujemy w tej samej wersji. Pause/edit poprzedza nowy grant;
   koszt: dodatkowy jawny krok użytkownika, zamiast niebezpiecznego ożywienia starego eventu.
2. Współdzielone zadania1/2 zamykamy dopiero z pełnym zintegrowanym gate. Koszt:
   większy lokalny diff przed pierwszym commitem; wcześniejszy1266PASS nie udaje finalproof.
3. Canonical `/settings/finances/categorization`, bez drugiego layoutu. Koszt: URL ma
   kolejność istniejących ustawień, nie pierwotną literówkę/transpozycję w planie.
4. 3B/providery/historia/automatyczne nowe kategorie i splity odłożone zgodnie z zakresem;
   koszt: wymagają osobnej realizacji/zgody, a nie oznaczenia całego etapu3 jako gotowego.
5. Brak produkcyjnego/liveRedis odbioru: testDB i fakebroker nie są wydaniem. Koszt:
   rzeczywista infrastruktura musi mieć własne osobno zatwierdzone przyjęcie operacyjne.
6. Cudze Velo/Q7 i dawny sidebarbrand poza zmianą. Koszt: istniejący problem etykiety
   brandu pozostaje do późniejszej naprawy, nie znika z raportu.
7. Reviewer nie uruchamiał suite (read-only), finalgate wykonuje implementer. Koszt:
   niezależna ocena kodu nie stanowi niezależnego wykonania testów.
8. Zamknięcia współdzielonych zadań sprawdzają hashe i zapisane wyniki tego samego
   końcowego gate, zamiast uruchamiać identyczne1303testy osobno per zadanie. Koszt:
   jeden pełny przebieg po review, bez sztucznego mnożenia identycznej weryfikacji.

Wcześniejsze decyzje projektowe zatwierdzone z pełnym planem: rozdzielenie3A/3B
(AI pojawi się później), creationoutbox zamiast inline/timestampcutoff (czwarta tabela
i handler), osobnyorigin zamiast fałszywego manualstate (refaktor prywatnego writera),
obserwowane ruleUUID bez FK (brak/zmiana referencji daje skip, nie uprawnienie) oraz
eventwatcher/batchedprojection (jedno ograniczone zapytanie, polling tylko pending).
Nie są to zgody na dodatkową autonomię, przetwarzanie historii lub wydanie.
