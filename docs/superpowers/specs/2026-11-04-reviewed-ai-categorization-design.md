# Etap 3B — trwałe propozycje AI i przegląd wybranych pozycji

## Status, intencja i zgody

Projekt sprawdzony przez buildera i zatwierdzony przez użytkownika słowem „tak” po
commicie2dc69c4. Osobny plan `../plans/2026-11-04-reviewed-ai-categorization.md`
zatwierdzony kolejnym „tak” po becb54c. Implementacja lokalna fake-only została odebrana;
nie uruchamia to providera ani produkcji. Baseline: backend28ce7f0/UI2b960ee/docsabf65dc, zweryfikowane
1303backend/439frontend/lint/types/build/111E2E+1expectedskip i2browseroriginPASS.

Użytkownik chce mniej ręcznego kategoryzowania bez oddawania modelowi kontroli nad
księgą. Zatwierdził hybrydę: reguły z3A mogą działać na przyszłość, AI tylko proponuje
z uzasadnieniem, człowiek zatwierdza wybrane propozycje po przeglądzie. Pewność nigdy
nie stanowi uprawnienia do zapisu. Nowe kategorie i splity wymagają osobnej zgody;
manualne decyzje mają pierwszeństwo. PostgreSQL pozostaje jedynym źródłem prawdy.

Ten dokument doprecyzowuje3B z `2026-11-04-hybrid-categorization-design.md`.
Kod3A nie jest ponownie implementowany lub wydawany. Brak zgody na realne AI/OCR,
aktywację modeli, historybatch, produkcyjną migrację/wdrożenie, mainmerge lub push.
Osobny szczegółowy plan realizacji jest zapisany i został zatwierdzony do lokalnej realizacji.

## Cel i twarde granice pierwszego3B

- Trwała, owner-scoped kolejka propozycji dla NOWYCH ręcznych nieskategoryzowanych
  dodatnich wydatkówPLN, z wyraźnym uzasadnieniem i przeglądem przed zapisem.
- Dwie niezależne decyzje: zgoda na wysłanie ograniczonego kontekstu do AI, następnie
  odrębne zatwierdzenie przypisania kategorii do konkretnej płatności.
- Jeden kontekst/jedna płatność na call. Brak narzędzi SQL/ledger/toolcalling, sald,
  plików, skanów, pozycji paragonów, kwot do przeliczania lub innych transakcji.
- Akceptacja dotyczy jednej istniejącej kategorii i całej istniejącej kwoty. Nie ma
  splitu, nowej płatności, zmiany konta/dat/FX/source/kwot, refundów ani automatyzacjiActual.
- Realny adapter pozostaje domyślnie wyłączony. Lokalny odbiór wyłącznie na fakeadapterze
  w testach/MockTransport i syntetycznych fixture, bez runtimeendpointu do wstrzykiwania AI.

Anti-goals: zielona etykieta confidence nie zastępuje człowieka; „zaznacz wszystko”
nie obejmuje przyszłych wyników; odzyskanie workera nie wykonuje po cichu kolejnego
płatnego calla; włączenie funkcji nie wznawia dawnej kolejki i nie skanuje księgi.

## Uprawnienie do generowania propozycji i nowość

Kategoria techniczna pochodzi wyłącznie z ustawienia3A, poID. Nadal bez zgadywania
nazw/null/rodziców. AI można włączyć niezależnie od `rules_enabled`, ale wymaga własnej
aktywnej kategorii technicznej oraz osobnej zgody na przyszłość.

Nowe `CategorizationSuggestionSettings` peruser: enabled=false, version/epoch,
consent_at, zaakceptowany serverpolicyepoch/configurationfingerprint i audyt. Zgoda
obejmuje zakres danych oraz limity pokazane wUI, nie przyszłe dowolne modele lub koszty.

Nowe `CategorizationLlmPolicy`: singleton, enabled=false, epoch, configfingerprint.
Zmiana providera/modelu/promptu/schema/privacygranic lub zwiększenie zakresu kosztowego
unieważnia dawny grant i wymaga ponownej zgody użytkownika. Policy/konfiguracja finansów
są niezależne od documentvision/Advisor; nie pożyczamy ich tabel usage ani uprawnień.
Brak ordinary-user endpointu do aktywacji serverpolicy lub wyboru sekretów/modeli.
Przy niedostępnej/nieaktywowanej konfiguracji włączenie userAI jest blokowane, zamiast
zapisywać zgodę na nieznany przyszły model. UI pokazuje effective_enabled osobno od
zapisanej preferencji. Po zmianie epoki/destynacji stary grant sam nie odżywa.

WyłączenieAI dotyczy generowania i publikacji nowych wyników, nie ręcznego korzystania
z już zapisanej propozycji. Taką propozycję można nadal przejrzeć i jawnie zaakceptować
lokalnie, jeżeli źródło/taxonomy/TTL są aktualne; samo apply nie wywołuje providera.
To decyzja wykonawcza wynikająca z dwóch oddzielnych zgód, nie wymóg dopisany użytkownikowi.

Eligibility jest wspólna z3A dla źródła/kształtu księgi: ordinary source=manual,
booked expensePLN, jedna strona kontowa + jeden markerposting, rzeczywiste rate1 i
source_amount==base_amount_pln, brak Actualmapping, loan, alokacji, pending, manualstate
i dowolnegoorigin. Modele/propozycje nie rozszerzają tej allowlisty źródeł.

Enrollment tylko w kontrolowanym `create_transaction`, atomowo z płatnością. Nowy
3Bintent zapisuje snapshot źródła, zaobserwowane wersje/epoki oraz powód przekazania
doAI. Ustawienia, dopasowanie exactreguły i grantAI czytane w jednym zapytaniuMVCC.
Brak późnych owner/tree/policy rowlocków ani FK do obserwowanych zgód przy enrollment;
wartości te są dowodem obserwacji, nie samodzielną autoryzacją workera.

Reguła ma pierwszeństwo. IntentAI powstaje tylko przy braku kandydata exactreguły lub
wyłączonych regułach. Ambiguous albo istniejąca, lecz nieaktualna/niezastosowana reguła
nie daje cichego fallbacku doAI. Nie zmieniamy terminalnych `no_match` eventów3A w
nowe joby i nie przeglądamy dawnych transakcji/eventów przy starcie/włączeniu funkcji.
Gdy serverpolicy lub zgodaAI są wyłączone/nieaktualne, nowa płatność nie tworzy
gotowego do odblokowania w przyszłości płatnego backlogu.

Nowość to jawny hook przy tworzeniu, nie data zakupu/księgowania lub created_at DB.
Odzyskiwać można wyłącznie joby zapisane przez3B w momencie kwalifikowanego utworzenia.
Usunięte/zmienione źródło kończy job bez wysyłania; nie szukamy zamiennej płatności.

## Mały pakiet danych i walidacja modelu

Provider otrzymuje tylko opis tej płatności i ograniczoną allowlistę pełnych ścieżek
własnych aktywnych kategorii expense z nieutrwalonymi kluczami lokalnymi c01,c02… .
Kategoria techniczna jest wykluczona z targetów; model nie może jej „zatwierdzić” jako
wyniku klasyfikacji. Dotyczy to konkretnego markerID, nie automatycznie jego poddrzewa.
Nie potrzebuje UUID transakcji/kont, kwot, walut do kalkulacji, sald, dokumentów,
historii, tokenów sesji, haseł lub treści innych domen. Klucze mapujemy na UUID dopiero
w backendzie, z zapisanej zaufanej mapy konkretnego requestu.

Opis i nazwy kategorii są niezaufanymi danymi, nigdy instrukcjami. Nie obiecujemy
anonimizacji dowolnej treści opisu: zgoda jawnie obejmuje jego wysłanie. Sekrety i pola
kont/banków nie są pobierane do pakietu. Request ma `store=false`, bez obietnicy zerowej
retencji u dostawcy poza jego umową. Nie zapisujemy chain-of-thought ani surowych
responsebody/sekretów w logach lub błędach walidacji.

Pierwszy structuredoutput:
- decision=existing_category | new_category | no_suggestion;
- category_key z enum allowlisty lub null, nigdy dowolny UUID;
- confidence=low | medium | high, informacja opisowa, bez progów uprawnień;
- krótkie explanation;
- optional newcategory{name,parent_key|null,explanation} jako niewykonywalny tekst.

JSONschema strict, extra forbidden i walidacja semantyczna: wykluczające się warianty,
dopuszczalne klucze/parent, długości, brak kwot/splitów/tooloutputs. Refusal, partial,
nieobsługiwany output, ucięta odpowiedź lub obcy klucz nie tworzą aktywnej propozycji.
Taxonomy, cały request, prompt/schema/config i źródło mają oddzielne hash/wersje.
Nie obcinamy po cichu opisów lub katalogu dla pozornej skuteczności klasyfikacji.
Przekroczenie granic daje bezpieczny blockedreason i ścieżkę ręczną, bez calla.

Builder defaults do konfiguracji, nie hardcodedgałęzi: opis500znaków, do200kategorii,
request do32KiB, maxoutput1024tokens, explanation500znaków, do5calli/user/dobęUTC,
TTLpropozycji7dni, maxwiek jobaprzedwysłaniem24h, reviewpage20pozycji. Model/provider
pozostają nieustawione i disabled, dopóki osobna aktywacja nie zatwierdzi wartości.
Jawne ograniczenia storage są walidowane na starcie, jak limit2000w3A.

## Durable job, quota i niepewny wynik

`CategorizationSuggestionJob`: unikalny creationintent peruser/transaction, observed
epoki i sourcehash, stan, lease/token/attempts/next_attempt_at, request/config/schema
fingerprints, safe error. Redis przenosi ID, dispatcher czyta tylko tabelę jobów.

`CategorizationLlmUsageReservation`: jedna rezerwacja na job, owner/dzieńUTC,
stan reserved/dispatching/known/unknown/released, rzeczywiste input/outputtokens lub
unknown, wersje konfiguracji. Nie kasujemy śladu kosztowego przy usunięciu płatności.
Job zachowuje opaque źródłowy UUID, ale nigdy nie traktuje samego UUID jako uprawnienia.

Dobowy twardy limit to liczba potencjalnych wywołań; serializowany quotaadvisorylock
owner+UTCday obejmuje count aktywnych rezerwacji i insert unikalnej rezerwacji. Brak
dublującej tabeli dziennych sald: calls/tokens/unknown raportujemy z tych rekordów.
Maxoutput i rozmiar wejścia ograniczają pojedynczy request. Nie udajemy twardego limitu
dobowych tokenów na podstawie zgadywanej tokenizacji. Znane tokeny raportujemy dokładnie,
brak usage jako unknown; nie wyliczamy dokładnego PLN bez wersjonowanego cennika/billingu.

Flow: claim/commit → rewalidacja źródła/policy i przygotowanie pakietu → reserve/commit
→ ponowna krótka kontrola grantów i markdispatching/commit → call poza transakcją/lockami
→ finishCAS. Przy providerze tylko istniejący bounded OpenAI-only no-retry transport,
bez redirect/envproxy/automatycznego model fallbacku i bez narzędzi.

Punktem przyjęcia wywołania jest commit markdispatching pod sprawdzonym grantem.
Cofnięcie zgody zatrzymuje jeszcze nieprzyjęte call-e, ale nie odwoła już przyjętego/
wysłanego requestu; taki request może zużyć limit i zakończyć się po wyłączeniuAI.
Nie może wówczas opublikować nowej propozycji. UI nie obiecuje cofnięcia danych już
wysłanych. Serverpolicy update nie trzyma swojego rowlocka podczas masowej zmiany
jobów/ledger; epoki są sprawdzane indywidualnie, bez kopiowania lockinversion z bulkpause.

Retry może dotyczyć wyłącznie bezspornych błędów PRZED dispatch. Po dispatch timeout,
crash, brak odpowiedzi lub odzyskanie wygasłego lease daje unknown/uncertain i zachowaną
rezerwację; nie wykonuje drugiego płatnego calla. Znany nosend może zwolnić rezerwację
raz przez CAS. Duplikat delivery nigdy nie rezerwuje ani nie wysyła drugi raz.

Finish ponownie sprawdza epoki/zgodę, źródło/manualorigin oraz taxonomyhash. Zmiana
oznacza odrzucenie wyniku, a nie jego dopasowanie do nowych danych. Faktyczne znane
usage trzeba odnotować także po cofnięciu zgody/utracie lease, dokładnie raz, ale bez
prawa publikacji propozycji przez stary token. Późna odpowiedź po terminalnym uncertain
może uzupełnić usage, nigdy po cichu wznowić joba. Pierwszy3B nie ma przycisku ślepego
retry niepewnego calla; pozostaje ręczna kategoryzacja i informacja o nieznanym zużyciu.

## Propozycja i jawna ludzka akceptacja

`CategorizationProposalItem`: owner, generationjobID unique, źródłowy transactionID
(nullable po usunięciu), immutable source/request/taxonomyhash, allowlista, existingtarget
lub tekst nowej kategorii, explanation/confidence, stan pending/approved/rejected/stale/
expired/superseded, wersja, TTL, approvalreceiptID. Brak kopii kwoty jako źródła raportów.

GET kolejki/detail jest niemutujący. Effectiveeligibility pokazuje zmienione/usunięte/
ręcznie chronione źródło lub przeterminowaną propozycję jako nieakceptowalną. Nie tworzy
nowej analizy i nie zatwierdza wyniku. Preview jest osobnym niemutującym commandem:
bieżąca kwota z ledger, przed/po, pełna ścieżka targetu, explanation, inputversions i
opaque token. Zmiana źródła lub całej użytej taxonomy unieważnia stary preview/proposal.

Apply wymaga realnego owner/auth/CSRF, expected itemversion, previewtoken, confirmed=true
i Idempotency-Key. Pod receipt→ownerdocument→categorytree→item/ledger/state/origin lockami
serwis jeszcze raz sprawdza źródło, target i pendingstatus. Tylko sprawdzony własny
existingtarget z propozycji. Nie przyjmuje od klienta source/origin/amount/callconfidence
ani parametru uprawniającego autoapply. Stale/blocked niczego nie pisze do postings.

Humanreview command wykorzystuje prywatny writer z3A, nigdy sfabrykowane potwierdzenie
w imieniu człowieka. Powstaje manualstate(source=manual), ponieważ decyzja zatwierdzenia
rzeczywiście pochodzi od człowieka, oraz osobnyorigin=approved_llm wskazujący proposalID
i immutableapprovalreceipt/hash. Reguła nadal nie tworzy manualstate. Późniejsza ręczna
korekta zapisuje manualorigin, zachowując poprzedniąproweniencję w audycie.

Postingamounts, accountPostingID/wszystkie mappedcolumns, transakcja i jej daty/source,
dokumenty/salda pozostają bez zmian. Receipt/audit/state/origin/proposalapproved i
categorypostings commitują atomowo. Replay zwraca tę samą decyzję; UI odświeża aktualne
odczyty zamiast instalować historyczny receipt do cache. Snapshot namespacev3 obejmie
proposalreference; stare preview dostają409, bez backfillu lub luzowania source=manual.

### Zatwierdzanie wybranej partii

Builder choice: partia jest ograniczoną operacjąUI nad trwałymi, niezależnymi propozycjami,
nie kolejnym DBbytem/batchjobem ani SQLbulkapply. Jedno „Zatwierdź wybrane(N)” potwierdza
zamrożoną listę obejrzanych preview, po czym klient wykonuje kontrolowane peritemapply
sekwencyjnie z własnym trwałym w tym dialogu kluczem każdego itemu. Backend pozostaje
małym narzędziem na jedną płatność. Nie trzymamy długiej transakcji na całą partię.

Domyślnie nic nie jest zaznaczone. Podgląd pokazuje wszystkie wybrane pozycje/targety,
niezależnie od confidence; zmiana wyboru unieważnia stary plan zatwierdzenia. Wyniki są
peritem: approved/stale/blocked/unknown/not_attempted. Konflikt jednego itemu nie cofa
poprawnych innych ani nie udaje pełnego sukcesu. Unknown przerywa dalsze żądania;
ponowienie niedokończonych używa tych samych kluczy/tokenów, nie nowych propozycji.
Zmiana sesji kończy wykonanie, stare odpowiedzi nie zapisują cache/wyboru nowej sesji.
Po reloadzie trwałe statusy/receipts rozstrzygają wynik; resztę trzeba przejrzeć ponownie.

### Nowa kategoria to dwie osobne decyzje

Tekst nowej kategorii jest widoczny, lecz nie bierze udziału w batchapply. Użytkownik
może otworzyć istniejące ustawienia kategorii i jawnie utworzyć kategorię/podkategorię,
następnie osobno ręcznie zatwierdzić przypisanie istniejącej płatności mechanizmem2.
Nowy target nie staje się automatycznie targetem starej propozycjiLLM. Takie ręczne
rozwiązanie ma originmanual, a dawna propozycja staje się nieakceptowalna. Bez inline
create-and-pay, nowej reguły z confidence lub splitu. Dedykowany inlineworkflow nowych
kategorii nie należy do pierwszego3B; wymóg osobnej akceptacji pozostaje zachowany.

## UI, API i zmiany w istniejącym kodzie

- Finanse → ustawienia → Kategoryzacja: niezależna zgodaAI na przyszłość, availability/
  epoka, zakres danych, limitycalls i known/unknownusage. Bez sekretów/modelpickerów.
- Kolejka „Propozycje kategorii” w kontekście finansów: opis, bieżąca płatność, przed/po,
  uzasadnienie, confidence jako informacja, zaznaczenie i preview wybranych, wyniki peritem.
  Niewspierane/nieaktualne wyniki nie oferują aktywnego przycisku akceptacji.
- Etykiety rozróżniają manual, approved_rule i approved_llm zatwierdzone przez człowieka,
  także account-history/search/detail. Nowe fields opcjonalne, batchprojection bez N+1.
- Wszystkie querykeys i lokalny reviewintent są sessionVersion-scoped; pendingmutations,
  historyreceipt i same-session authrefresh zachowują obecny kontrakt3A.
- Wstępne API: `GET/PATCH /categorization/suggestions/settings`, `GET .../usage`,
  `GET /categorization/proposals` z ograniczoną paginacją, detail, peritempreview/apply/
  reject. Brak endpointu generowania dla dowolnego starego transactionID lub uruchamiania
  historii, brak ordinary-user serverpolicy activation. Dokładne DTO/prefixy w planie.

Proponowane5nowych tabel: userconsent, serverpolicy, generationjob, usagereservation,
proposalitem. Nie dokładamy osobnego proposalbatch lub dailycounter tylko dlaUI.
Origin otrzyma nullable proposalFK i warunkowy check approved_llm oraz trzy literalne
warianty wDTO/projection/UI; receiptFK będzie dowodem faktycznej ludzkiej decyzji.
Manualstate i dawne kwoty/pins bez zmian. Migration po c063 addytywna/no-backfill,
poszerzenie wyłącznie originchecka. Downgrade pod lockami odmawia utraty nowych danych
lub istniejących approved_llm origins, a nie kasuje ich dla wygody rollbacku.

Reuse: categorization context/writer/receipt/audit; rule marker/eligibility; documentjobs
tylko jako wzorzec lease i policyepochs; `app/openai_client.py` jako transport/parser.
Nie kopiować automatycznego retryvision po timeout do płatnego3B. Nie zmieniać modułu
documents ani istniejącego proweniencjiActual przy implementacji finansowego adaptera.

## Odbiór lokalny i pytania buildera

TDD: własność/real-sessionCSRF, defaultoff/configfailclosed/consentrevocation, creation-only
vs oldevents/oldtxn, rulepriority i rulesoff+AIon, brak późnych FKlocków, rezerwacjaquota
pod wyścigiem, duplikatyRedis/lease/dispatchtimeout/crash, brak refund/retry po uncertain,
spóźnione usage bez publikacji, malicious/schema/refusal/obceklucze, taxonomy/source staleness,
manual/Actual/loan/FX/pending/allocationguard, exactgrosze/unchangedaccountcolumns, audyt/
receiptrollback, mixedbatchresults/retrykeys/sessionfences/newcat noapply, migrationretention.
Fakeadapter/MockTransport dowodzą zero calls przyoff. Pełny backend/frontend/lint/types,
freshbuild/E2E375/1440 i jeden whole-review po implementacji. Brak realnychproviderów/
historybatch/produkcji w odbiorze i brak powtarzania sprawdzonej migracji/seed tego samego schematu.

Builder powinien sprawdzić zwłaszcza: wykonalność5tabel bez dziennego dualcountera,
utrzymanie etapu3A przy niezależnej zgodzieAI i rulesoff, off/enable bez backlogu, uczciwą
proweniencję human-approvedAI, quota/CAS przy unknown/late usage, peritembatch UX/replay,
retencję kosztów po usunięciu płatności i brak circular-FK/lockorder przy approvalreceipt.
Sprawy implementacyjne rozstrzyga builder; do użytkownika wracają tylko kwestie, które
realnie zmieniają produkt. Read-only buildercheck `ses_e59d8b4d3ffeBS7Tn33DBmUslJ`
spisanego projektu i reuse aktualnego kodu zakończony: „nothing important left”. Nie ma
dodatkowej rundy pytań produktowych. Po checku dopisano jawne interpretacje wykonawcze:
oddzielenie revokegenerowania od lokalnego review, marker nie jest targetem, liniowy
punkt dispatch oraz brak bulkjobmutation pod globalpolicylockiem. Przed kodem potrzebne
było zatwierdzenie szczegółowego planu; obie zgody zostały już uzyskane. Odbiór lokalny
nie obejmuje aktywacji rzeczywistego modelu lub wydania produkcyjnego.
