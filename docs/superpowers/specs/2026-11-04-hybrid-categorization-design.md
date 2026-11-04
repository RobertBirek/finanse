# Etap 3: reguły i propozycje AI w trybie hybrydowym

## Decyzja użytkownika i status

Po odbiorze lokalnych etapów1/2 (63e2b9c/9fef438) użytkownik zatwierdził 2026-11-04:

1. Wcześniej zatwierdzone reguły mogą automatycznie przypisywać istniejące kategorie
   wyłącznie nowym nieskategoryzowanym transakcjom.
2. LLM przygotowuje propozycje z uzasadnieniem. Użytkownik może zatwierdzić wybrane
   propozycje zbiorczo po ich przeglądzie. Pewność modelu nie upoważnia do zapisu.
3. Ręcznych przypisań nie nadpisujemy. Nowe kategorie/podkategorie i splity wymagają
   akceptacji. Historię przetwarzamy tylko po osobnym poleceniu.

To zgoda na politykę produktu, nie na niepokazany plan implementacji, produkcyjną
migrację/wdrożenie, realne wywołania AI/OCR lub batch historyczny. Kod etapu2 nadal
jest sprawdzonym baseline1250backend/429frontend/107E2E+1skip. Ten dokument opisuje
etap3; pierwszy plan wykonawczy dotyczy niezależnego kroku3A. Kod jeszcze bez zmian.

## Cel i kolejność

Użytkownik ma mniej ręcznego klikania, ale rozpoznaje, kto nadał kategorię i dlaczego.
Automatyzacja nie narusza tożsamości płatności, sald, dat, dokumentów ani importu.

- **3A:** ustawienie kategorii technicznej, zatwierdzane reguły dokładnego opisu,
  trwałe zdarzenia nowych wydatków, osobna proweniencja i UI reguł. Bez LLM.
- **3B:** trwałe propozycje, joby i limity LLM, przegląd i zatwierdzanie wybranej
  partii. Provider domyślnie wyłączony, testy z adapterem fake.

Każdy krok ma osobny lokalny odbiór. Etap4 dodaje pozycje paragonu i zatwierdzane
splity; etap5 dopasowanie dokumentu do płatności; etap6 kontrolowane partie historii.
Nie oznaczamy całego etapu3 jako gotowego po samych regułach.

## „Bez kategorii” jest jawnym ustawieniem

Dedykowane `TransactionCategorizationSettings` per właściciel: kategoria techniczna
poID, `rules_enabled=false` domyślnie, wersja i audyt. To odrębny cykl życia, nie
rozszerzenie ustawień prognozy wynagrodzenia. Konfiguracja wybiera istniejącą własną,
aktywną kategorię expense; bez automatycznego tworzenia lub zgadywania nazwy.

Nieskategoryzowany wydatek ma dokładnie jeden categoryposting wskazujący ten ID i
nie ma ręcznego stanu etapu2 ani żadnego przypisania etapu3. Nie oznaczają tego null,
„Pozostałe”, podobna nazwa lub podkategoria wybranego węzła. Brak metadanych sam w
sobie nie daje prawa do zmiany dowolnej dawnej kategorii.

UI przed włączeniem wyjaśnia, że nowe wydatki z wybranym ID są placeholderem dla
automatyzacji. Stare transakcje nie są przeglądane. Osobne ręczne zatwierdzenie takiej
transakcji, nawet bez zmiany kwoty/kategorii, blokuje późniejszą automatyzację.

## Reguły 3A: wąski, zatwierdzany kontrakt

Pierwszy matcher to **dokładny znormalizowany opis**. Normalizacja: UnicodeNFKC,
casefold, trim i redukcja kolejnych białych znaków. UI pokazuje oryginalny opis i
znormalizowaną wartość do akceptacji. Nie wolno obcinać opisu dla dopasowania, używać
substring/regex/fuzzy, modelowego wyniku lub nieistniejącego pola kontrahenta.
FinancialTransaction ma obecnie tylko description; Actual składa go z payee/notes.

Reguła wybiera jedną własną, aktywną, istniejącą kategorię expense inną niż techniczna.
Nie dzieli kwoty i nie zmienia konta/typu/dat. Wskazanie istniejącej kategorii zActual
jest dozwolone, nie oznacza modyfikowania transakcji lub mappinguActual.

Cykl życia: draft → zatwierdzona aktywna → paused/retired. Edycja zmienia wersję i
wraca do draft; ponowne uruchomienie po edycji/pauzie wymaga jawnej akceptacji wersji.
Nie ma harddelete reguły użytej w finansach. Jeden aktywny exactmatcher per właściciel
chroni przed kolizjami. Więcej niż jeden match w danych nie upoważnia do wyboru pierwszego:
job kończy się `ambiguous`, bez zapisu. Nowy target lub jego zmieniona ścieżka wymaga
ponownego podglądu/akceptacji; dawna zgoda nie przechodzi na inny sens kategorii.

Zatwierdzenie reguły ma osobny niemutujący podgląd, wersję i token obejmujący wzorzec,
kategorię techniczną i docelowy categorypath. Przycisk mówi o **przyszłych** wydatkach.
UI nie proponuje ukrytego zastosowania do istniejących wierszy. Approval/pause/edit
mają owner-scope, CSRF, idempotentny receipt i audyt; żądanie nie ustala approved_by.

## Jak odróżniamy nową transakcję od historii

Zdarzenie powstaje tylko w kontrolowanym `create_transaction`, przy pierwszym zapisie
nowego zwykłego ręcznego wydatku PLN w kategorii technicznej. Nie ma skanowania księgi
przy włączeniu reguł, starcie workera, zmianie opisu lub zatwierdzeniu nowej reguły.
Data zakupu/księgowania nie określa nowości. `created_at` wPostgreSQL używa czasu początku
transakcji, więc sam warunek `created_at > approved_at` nie rozstrzyga wyścigu.

W tej samej transakcji co źródłowy wydatek zapisujemy trwałe zdarzenie z:
- snapshotem wejścia, ID i wersją ustawień oraz obserwowanej zatwierdzonej reguły;
- czasem rejestracji zdarzenia, właścicielem, jednoznacznym ID i stanem joba;
- stanem `no_match`/`ambiguous`, gdy nie było jednoznacznej zgody w momencie rejestracji.

Rejestracja odczytuje ustawienia i dopasowanie w jednym spójnym zapytaniu MVCC, bez
późnego brania owner/category/account locków po lockach konta. Nie stosuje kategorii
wewnątrz tworzenia płatności. Reguła zatwierdzona dopiero później nie staje się regułą
tego zdarzenia. Zmiany ustawień mają wersję; zmiany wybranej reguły również.
Helper dostaje jawnie załadowane postings po końcowym selectinload w create_transaction;
nie odwołuje się do async lazy relationship. Zaobserwowane ruleID/version są w zdarzeniu
nieautorytatywnymi wartościami, bez FK do reguły/receipt. INSERT zdarzenia nie może przez
FK brać późnego locka reguły, gdy źródłowa transakcja trzyma już locki kategorii/konta.
Zgodę zawsze odtwarza i waliduje worker z aktualnej reguły oraz niezmiennego receipt.

Dispatcher czyta tylko tabelę zdarzeń, nie stare financial_transactions. Redis/ARQ
przenosi ID; PostgreSQL jest źródłem trwałego stanu. Claim/lease/CAS/recovery nie może
uruchomić ponownie zakończonej decyzji. Błąd brokera nie cofa ani nie dubluje płatności.

Worker przed zastosowaniem sprawdza: ustawienia/rules_enabled i wersję, tę samą
zatwierdzoną regułę/wersję/targetpath, aktualny snapshot płatności, dokładny placeholder,
brak manualnego stanu i origin, własność, PLN/rate1/source_amount==base_amount_pln,
brak pending, Actualmapping/source, LoanPaymentLink i alokacji dokumentu. Zmiana w
międzyczasie daje terminalskip/stale, nie korektę starego wpisu lub dobór nowej reguły.
Marker jest osobno sprawdzany pod lockami: nadal własny, aktywny, expense i równy
postingowi placeholdera. Sama zgodność wersji ustawień nie wystarcza po archiwizacji
lub zmianie kategorii technicznej.

Builder default3A: automatyzacja tylko dla nowego ordinary `source=manual` expense.
Źródła Actual/import/scheduled/AI/document_payment i rozliczenia dokumentów są poza
automatycznym zapisem tego kroku. Zachowują działający ręczny mechanizm etapu2,
o ile przejdą jego istniejące walidacje. Rozszerzanie źródeł wymaga osobnego projektu.

## Proweniencja nie może udawać ręcznej decyzji

`TransactionCategorizationState.source` z etapu2 pozostaje wyłącznie `manual`.
Reguła nie może wywołać manualnego apply z `confirmed=true` w imieniu użytkownika
ani zmienić checkconstraint na pozornie zgodną etykietę.

Nowe `TransactionCategorizationOrigin`1:1 przechowuje aktualny origin/version oraz
odwołanie do zatwierdzonej reguły/wersji/receipt i skrótu decyzji; kwoty nadal tylko
w postings. Ręczny apply aktualizuje origin na manual w tej samej transakcji; audyt
zachowuje wcześniejszą regułę. W3B dojdzie identyfikator zatwierdzonej propozycji.
Istniejący manualstate bez origin jest nadal ochroną, bez backfillu.

Wspólny prywatny writer kategorii zachowuje ID i wszystkie kolumny accountposting,
daty/kwoty/typ/source, docallocations oraz invariant księgi. Publiczny manualny command
nadal wymaga zatwierdzonego preview; wewnętrzny rulecommand wymaga aktualnego grant
z bazy. Client nigdy nie wybiera origin lub `allow_auto` w payloadzie. LLM nie otrzymuje
takiego narzędzia. Receipt/audit/origin/postings i końcowy stan joba commitują atomowo.
Rule.approval_receipt_id i origin.approval_receipt_id mają FKRESTRICT do
finance_command_receipts.id. Receipt trwale zawiera ruleID/version, oryginalny i
znormalizowany wzorzec, markerID, snapshot/path targetu, zakres zgody i czas/aktora;
origin zapisuje także approval_snapshot_sha256. Receipt nie jest edytowany ani używany
dla nowej wersji. Opis historycznego przypisania pochodzi z tej zgody, nie z obecnej nazwy reguły.

Kolejność3A: receipt → owner-document mutex → category-tree → jobrow (jeśli dotyczy) →
parent → postingrows → state/origin → policy/rulerows → categoryrows. Claim joba bierze
tylko jobrow i commit przed wejściem w ledger. Ustawienia/reguły i manualne apply
korzystają z owner-document mutex przed dalszymi lockami. Bez późnego account-row lock.
Istniejące mutacje samej kategorii mogą brać tylko category-tree przed własnymi wierszami;
nie wolno dopiero po nim dokładać owner-document mutex. Wspólny tree lock serializuje
zmianę sensu targetu z workerem; category mutator nie czeka przy tym na job/policy/ledger.

Nieudany writer/audyt wycofuje ledger/origin/receipt i próbę terminalizacji joba.
Dopiero osobna krótka transakcja, warunkowa na nadal własnym lease token, zapisuje
safe reason i retry/failed. Rollback sam nie może utrwalić failed. Enqueue failure nie
zwiększa attempts; zwiększa je tylko skuteczny claim. Recovery dotyczy wyłącznie
niezakończonych zdarzeń; po maxattempts terminalfailed bez zapisu księgi. Applied,
skipped i failed nie wracają do dispatch. Lease utracony nie pozwala staremu workerowi
nadpisać wyniku lub nowej rezerwacji.

## Propozycje i AI, krok 3B

Odrębne batch/items przechowują wersjonowaną propozycję, kontekst wejścia, target,
uzasadnienie, confidence, provider/model/prompt/schema i stan
pending/approved/rejected/stale/superseded/expired. Brak pasującej reguły nie oznacza
automatycznego zapisu; pewność jest tylko informacją w przeglądzie.

Model dostaje ograniczony opis i allowlistę własnych aktywnych categoryID/path.
Domyślnie nie potrzebuje kwot, sald, kont, IBANów, dokumentów lub innych transakcji.
Opis traktujemy jako niezaufane dane, nie instrukcje. Structured Outputs wybiera
jeden dozwolony existingID albo no_suggestion. New-category text jest niewykonywalną
propozycją; tworzenie kategorii wymaga osobnej akceptacji i nowego preview targetu.
Nie ma split output, SQL, narzędzi ledger ani rejestrowania reguły przez model.

Użytkownik wybiera konkretne itemy. Każdy podgląd pokazuje kategorię/uzasadnienie i
wersję wejścia. Apply ponownie sprawdza własność i aktualność; stale item nie pisze.
Zatwierdzanie partii to jawne wyniki peritem z idempotencją, nie ukryte „zaakceptuj
wszystko, co AI znajdzie później”. Akceptacja istniejącej kategorii korzysta ze
wspólnego writer/receipt; akceptacja nowej kategorii jest osobnym poleceniem.

Batch approval może zatwierdzić poprawne wybrane elementy i zgłosić pozostałe jako
stale/blocked. UI pokazuje wynik każdego i nie utożsamia częściowego sukcesu z pełnym.
Nie utrzymujemy długiej transakcji/locków na czas przeglądu lub wywołania providera.

Finance-specific job/policy/usage korzystają z wzorca documentjobs, nie z ich tabel
ani polityki vision. Durable intent → claim/commit → rezerwacja quota/commit → provider
poza lockami → finishCAS. Powtórzone delivery nie powoduje kolejnego wywołania.
Niepewny timeout po wysłaniu nie dostaje ślepego automatycznego retry/refundu quota.

Provider jest wyłączony domyślnie; konfiguracja modelu i limity są konfigurowalne,
sekrety tylko w backendzie. Brak fallbacku do innego modelu lub Vision. Zapisujemy
rzeczywiste usage tokens/calls, ale nie podajemy dokładnego kosztuPLN bez jawnego
wersjonowanego cennika lub kwoty rozliczonej przez providera. Lokalnie tylko fakeadapter.

## UX i odbiór

W3A ustawienia finansów otrzymują „Kategoryzacja”: wybór kategorii technicznej,
rules_enabled, listę reguł ze stanem oraz draft→preview→zatwierdzenie. Podział widoku
ustawienia/codzienne finanse zostaje. Historia transakcji pokazuje origin reguły i
pozwala przejść do ręcznej korekty. Osobna kolejka propozycji należy do3B.

Klient używa sessionVersion i per-session QueryClient. Stare odpowiedzi nie zmieniają
cache/dialogu nowej sesji;409 zachowuje wpisy i wymaga nowego przeglądu. UI rozróżnia
ręczne przypisanie, zastosowanie zatwierdzonej reguły i przyszłą zaakceptowaną propozycjęAI.
Origin może być opcjonalnym, read-only polem także TransactionResponse, ładowanym
zbiorczo/selectin bez nowych mappedcolumns transakcji i bez N+1. Krótki watcher czyta
tylko aktywne własne zdarzenia, po ich odczycie/ukończeniu odświeża finanse; create
invaliduje także ten watcher. To zapobiega pozostaniu UI na placeholderze po asynchronicznym
zastosowaniu reguły. Nie skanuje księgi i nie uruchamia istniejących transakcji.

Testy3A obejmują: brak kategorii technicznej/off, exactnormalization i braksubstring,
approval/pause/edit race, nowe vs stare, brak ponowienia po recovery, manualną ochronę,
all mapped accountposting columns/date/ledger invariants, origin bez manualstate,
rollbackaudit/receipt, outbox przy niedostępnymRedis, Actual/loan/FX/doc safeguards,
owner/CSRF/session, category/account mutation races i additive/no-backfill migration.
Testy3B dodatkowo: malicious outputs/foreignID/promptinjection, quota/CAS/timeout,
taxonomy/snapshotstale i częściowe zatwierdzanie wybranej partii. Pełne test/lint/types,
build/E2E375/1440 i jeden whole-review na krok, realne calls/produkcja poza odbiorem.

## Wynik builder check i decyzje wykonawcy

Read-only `ses_e5aa56365ffeFvTF8OHW4I6XXL` potwierdził reuse etapu2, brak scalarmerchant,
manual-only state i brak cennika. Nie ma kolejnego pytania produktowego blokującego3A.
Wybrano exactmatcher, osobny origin, brak zapisuActual i dwa kroki zamiast dużegoMVP.
To decyzje wykonawcze do przeglądu z planem, nie dodatkowe preferencje usera.

Builder proponował bezpośredni creation-time dispatch i created_at cutoff. Doprecyzowano
go do trwałego zdarzenia z zaobserwowanymi zgodami, a nie inline ledgerapply albo
zawodnego samego timestampu. Koszt: tabela zdarzeń i handler istniejącego workera;
zysk: brak późnych account/doc locków i niejawnego przeglądania historii.
Przyszła automatyzacja importówActual wymaga osobnej architektury immutable source/
category overrides lub jawnie uzgodnionej zgodności importu, nie obejścia pins.
