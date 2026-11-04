# Produkty paragonu 4A — lokalna implementacja

Status: **odebrane lokalnie**, nie wydanie produkcyjne. Projektb972368 i plan3be47c9 zatwierdzone
oddzielnymi „tak”. Kod w istniejącym `feat/financial-document-workflow`, bez merge/push/deploy.

## Zakres

- Ręczne produkty, jawne kwoty i udziały rabatów; grosze, bez zaokrągleń/dopisania różnicy.
- Własne sklepy wybierane jawnie, bez łączenia po nazwie dostawcy/NIP.
- Bounded historia aktualnych zatwierdzeń innych własnych paragonów w tym sklepie;
  normalizacjaNFKC/casefold/whitespace, exact przed literalnym prefiksem. Konflikty i limity
  jawne, bez automatycznego przyjęcia; pełna lista kategorii z filtrem pozostaje dostępna.
- Append-only rewizje/produkty/rabaty/udziały. Nowe zatwierdzenie nie nadpisuje dawnych dowodów.
- Osobno zatwierdzenie produktów i przegląd/zatwierdzenie podziału jednej pełnej istniejącej
  płatnościPLN. Kategorie zapisują istniejące kontrolowane writery z originmanual.
- Nie powstaje transakcja ani alokacja. Konto/kwoty/daty/alokacje i raporty pochodzą wyłącznie
  z księgi. Actual/loan/FX/pending/partial/sharedpayment pozostają chronione.

## Dowody lokalnego odbioru

- `retained-green.log`:35PASS math/draft, w tym dynamiczne limity po replay i bezpieczny zakres.
- `task34.log`:52PASS history/approval/payment/races; finalTask3 19PASS/Task4 37PASS,
  w tym22bariery PostgreSQL (sourcehintarchive/newapproval w obu admissions).
- `ui-full/`:476frontend, ESLint i TypeScript PASS.
- `build-ui.log`, `e2e-ui2.log`:4PASS desktop1440/mobile375, dialogAxe/overflow/keyboard,
  produkty8000/2000 minus1000 z udziałami800/200 →7200/1800. Osobne zgody i niepewnyapply
  po servercommit: ten sam token/body/key, jedna faktyczna operacja. Brak realnego API/providerów.
- Jeden końcowy review read-only `ses_e585e723dffeuBe5dgiLRdd7yQ`: Focus1–5PASS,
  jedno finding o mylącym statusie aktualności po zmianie nagłówka. Autor podniósł
  Minor doImportant ze względu na prawdziwość danych finansowych:4RED/1controlPASS →5GREEN.
  Status uwzględnia aktualność dowodu, ale nie nieistotny wzrostbill.version. Brak
  pozostałych findings/deferredminors, declinedtojudgeempty; bez drugiego review.
- Pełny zamrożony gate po poprawce: **1506backend/476frontend**, Ruff/Mypy/ESLint/TypeScript,
  freshbuild i **131E2E+1expectedskip** PASS. Backend8deselected to jawne testyproxy poza
  domyślnym suite, nie brakDB;1E2Eskip to desktopdla mobileagendacontract.10znanych warnings
  deprecacji backendu oraz advisorylargechunk buildu nie są pominiętymi testami.
- `accept.py` **sh_1a7a782fa001hvL3PHkKLfLag5** zakończony, `final-proof.json` i `verify-final.py`
  potwierdzają te same bajty sources/dist/migracji przed/po gate/build/E2E i commitach.
- Commity kodu: backend`09a624d`, UI`5ea6454`. Bez ponownego godzinnego gate przydocs-only;
  finalny verifier sprawdza zachowane dowody i identyczne źródła produktu.

Prywatne artefakty: `/tmp/opencode/receipt-items-20261104/`. Nie są źródłem prawdy aplikacji;
to wyłącznie syntetyczne logi i dowody odbioru. Dane produktu są wPostgreSQL.

## Migracja

`a3ffcaf427aa`, rodzic243aa1d9461c: tylko6nowych tabel receipt_stores/item_states/item_revisions/
item_lines/item_discounts/item_discount_shares. Wygenerowana raz, odrzucono niezwiązany drift
indeksów scheduledfinance. CompositeFK(owner,revision,key), RESTRICT, strictsafeBIGINT.
Approvedstoreversion ma jawneISNOTNULL, aby SQLNULL nie omijał checka.

Próba tylko w nowym `receipt_items_stage4a_test` wfinanse_test: brak backfillu, zachowane
wszystkie stare kolumny/wiersze/indeksy, originmanual/rule/approvedLLM, allocation/audit/receipt.
Pusty downgrade/reupgrade PASS; populateddowngrade odmówiony przedDDL pod6ACCESS EXCLUSIVElocks.
Hash migracji zgodny z zatrzymanym proof; ponowny seed/rehearsal niepotrzebny, jeśli bajty są te same.

## Decyzje wykonawcze

1. Zachowano exactsourcebaseline3B zamiast powtarzać niezmieniony godzinny gate przed pracą.
   Koszt błędu: nieaktualny baseline; verifier sprawdził go przed pierwszą edycją.
2. Literalne prefiksy PostgreSQL `starts_with` zamiastLIKE zescape — `%/_` nie są wildcardami.
   Koszt błędu: wymaga PostgreSQL13+; projekt korzysta16, testy literalnych znaków PASS.
3. Schematy mają stałe storagecaps, aktualne limity wejścia sprawdzane po identycznym replay.
   Koszt błędu: dodatkowy obowiązek walidacji w serwisie; regresja GET200/replayidentyczny/
   nowy oversized422 dowodzi zachowania po zaostrzeniu konfiguracji.
4. Natywny TSPlaywright/mockbuild zamiast ogólnego Python/server z pomocniczego skillu.
   Koszt błędu: nie jest to browser+realbackendintegration; osobne testy PostgreSQL weryfikują domenę.

## Granice i następny etap

4A nie zamyka całego etapu4. **4B — odczyt pozycjiOCR/AI — nie jest wykonane ani aktywowane**.
Nie zmieniono ekstraktorów/promptów/polityk/providerów/jobów. Nie przetwarzano historii batch.
Produkcja, preview, oryginały, Actual i zastane Velo/Q7 pozostają bez zmian.
