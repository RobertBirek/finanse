# Dopasowanie dokumentu do istniejącej płatności — etap 5A

Data: 2026-11-07. Status: **propozycja zakresu do zatwierdzenia**, nie plan wykonania.

## 1. Intencja i granica zgody

Użytkownik zaakceptował przygotowanie zakresu po przeglądzie istniejącego mechanizmu
(„ok, działaj” po pytaniu „Przygotować taki zakres?”). Kierunek: kwota, waluta,
kontrahent, różnica dat zakupu/księgowania, zrozumiałe powody i ręczna decyzja,
bez tworzenia drugiej transakcji. Szczegóły poniżej są **rekomendacją autora**.
Wymagają akceptacji całego zakresu, następnie osobnego planu, przed kodem produktu.
Nie ma zgody na produkcyjne operacje, AI/OCR, przetwarzanie historii lub wdrożenie.

Cel pierwszej jednostki: łatwiej rozpoznać właściwą istniejącą płatność w obecnym
dialogu „Rozlicz płatność”, szczególnie przy zakupie w piątek i księgowaniu w poniedziałek.
Nie budujemy nowego systemu uzgodnień, księgi lub rejestru kontrahentów.

## 2. Co już istnieje — sprawdzone w kodzie

- `bill_payments.py:get_payment_candidates` i GET `/finance/bills/{id}/candidates`:
  właścicielskie wyszukiwanie, paginacja, tekst, zakres dat, uwzględnienie starszych.
- Kandydat to jeden kwalifikujący się kontowy debet PLN z istniejącej expense,
  nie suma obu stron księgi. Pending/future/transfer/income/FX/loan links i błędnie
  zbilansowane transakcje są odrzucane. Zachowane limity pojemności postingu.
- Ręczna alokacja istniejącego postingu, częściowe rozliczenia, odpięcie, blokady,
  wersja dokumentu, receipt/idempotencja, audyt i ochrona powiązanych transakcji.
  Alokacja nie tworzy nowej transakcji ani nie zmienia jej kwoty lub dat.
- Osobna, jawna „Zarejestruj płatność” tworzy expense; nie jest ścieżką dopasowania.
- Obecny ranking: legacy Inbox reference, różnica kwoty do sumy dokumentu, odległość
  od terminu, ID. Przy braku terminu bieżący tie-break daty jest jednak zerowy.
- Obecne okno używa `transaction.date` i due/issue/today, bez daty sprzedaży lub zakupu.
- `TransactionDateMetadata` przechowuje zakup/księgowanie i proweniencję. Relacja
  `FinancialTransaction.date_metadata` ma już `lazy="selectin"`; matcher nie korzysta
  z tych danych. Nie trzeba nowego równoległego magazynu dat.
- `BillPaymentDialog` pokazuje konto, jedną nieopisaną datę i wolną kwotę. Nie pokazuje
  otrzymanych `reasons`, opisu transakcji ani podstawy porównania dat. Brak odrębnych
  stanów pobierania/błędu/pustego wyniku kandydatów. Ręczny wybór jest już obecny.
- Brak dedykowanego kontrahenta transakcji bankowej. Jest opis transakcji; dokument
  ma nazwę sprzedawcy/NIP/rachunek. Nie wolno udawać zweryfikowanej tożsamości kontrahenta.

Podstawa: `backend/app/finance/{bill_payments,bills_router,bills_schemas,models,
transaction_dates,document_guards}.py`, `frontend/src/api/bills.ts`,
`frontend/src/components/finance/bills/{BillPaymentDialog,BillDetail}.tsx`.

## 3. Proponowany mały zakres

1. Rozszerzyć **istniejący odczyt kandydatów**, nie alokacje, o dane i uzasadnienia.
2. Wykorzystać znaną datę zakupu przy porównaniu i kolejności wyników, bez zmiany
   dat źródłowych oraz znaczenia istniejących filtrów.
3. Dodać ostrożną wskazówkę nazwy sprzedawcy występującej w opisie płatności.
4. Pokazać w obecnym dialogu powody, kontekst kwot i jednoznaczne daty; odróżnić
   pobieranie, błąd i brak wyników. Nie zmieniać układu aplikacji ani wielokrotnego wyboru.
5. Zachować jawne potwierdzenie jednej istniejącej płatności i wszystkie obecne zabezpieczenia.

Rekomendacja autora: **nadal tylko PLN dla rozliczenia**. Rejestr EUR/USD pozostaje,
ale nie rozszerzamy alokacji walutowych ani nie zgadujemy kursów. Bez nowych usług,
bibliotek runtime, modeli LLM lub wywołań dostawców.

## 4. Twarde kwalifikacje i kwoty — bez poluzowania

Wszystkie obecne warunki `_eligible`, owner scope, capacity i wyłączenie loan links
pozostają. Sygnały tekstowe/daty nie mogą dopuścić transakcji odrzuconej przez te reguły.
Nie uznajemy spłaty karty/transferu za drugi zakup ani nie rozpoznajemy zwrotów po słowach.

GET zwraca puste `items` i jawny powód niedostępności dla własnego dokumentu:
nieaktywnego, niezatwierdzonego, nie-PLN lub całkowicie rozliczonego. Kolejność powodów:
lifecycle, review, currency, remaining. Obcy/brakujący dokument nadal404. Powód jest
oddzielony od „brak kandydatów w filtrach”; nie odsłania cudzych danych.

Kontekst pokazuje osobno:
- sumę dokumentu i jego pozostałość do uzgodnienia;
- pierwotną kwotę płatności i jej nieprzydzieloną pojemność;
- walutę PLN, bez mieszania walut lub liczenia obu stron ledgeru.

W tej jednostce zachowujemy istniejący priorytet różnicy **pierwotnej kwoty płatności
do całkowitej kwoty dokumentu**. Nie przebudowujemy rankingu płatności częściowych/
zbiorczych; ich różnica i wolna pojemność są jawne, a kwotę alokacji nadal podaje człowiek.
Nie ustawiamy automatycznie kwoty jako min(pozostałość, pojemność).

## 5. Daty i ich znaczenie

- Istniejące pole kandydata `date` zachowuje `FinancialTransaction.date` dla kompatybilności.
- Nowe pola zakupu i księgowania oraz źródła pochodzą wyłącznie z istniejących metadanych
  tego właściciela. Metadata innego ownera nie jest dowodem i nie trafia do odpowiedzi.
- Brak daty zakupu to brak danych, nie kopia księgowania. Brak jawnego księgowania:
  pokazujemy „Data zapisu — znaczenie nieustalone”, nie „potwierdzona data bankowa”.
- Dokument nadal ma odrębne sale/issue/due. Termin nie jest datą zakupu.

Jedna jawna para do sortowania/wyjaśnienia, wybierana kolejno (decyzja autora):

| Dostępne dane | Porównanie |
|---|---|
| zakup transakcji + sprzedaż dokumentu | zakup ↔ sprzedaż |
| księgowanie transakcji + termin dokumentu | księgowanie ↔ termin |
| zakup transakcji + wystawienie dokumentu | zakup ↔ wystawienie, jawnie słabsze odniesienie |
| księgowanie transakcji + wystawienie dokumentu | księgowanie ↔ wystawienie |
| pozostałe przypadki | dotychczasowa data zapisu ↔ due, else issue, else sale, else local_today |

W ostatnim wierszu, jeśli data zapisu ma potwierdzenie booking w metadanych, nie
pozbawiamy jej tego opisu. Bez metadanych pozostaje fallbackiem o nieustalonym znaczeniu.
Odniesienie do dziś jest jawnym fallbackiem, nie dowodem daty dokumentu.

Odpowiedź podaje obie użyte daty, rodzaj dat po obu stronach, różnicę dni i informację
o oknie. Bez procentów „pewności”, bez automatycznej korekty którejkolwiek daty.
Przy linkowaniu nie kopiujemy sale_date dokumentu do purchase_date transakcji.

### Dostępność i filtry

Istniejący `BILL_PAYMENT_CANDIDATE_DATE_WINDOW_DAYS` (W) pozostaje konfigurowalny.
Nie ukrywamy dotychczas widocznych kwalifikujących się wyników wskutek nowej pary dat.
Obecny filtr okna pozostaje; dodatkowo kandydat może przejść okno dzięki jawnej dacie
zakupu w ±W dni od sale_date, a przy jej braku od issue_date. Brak obu dat dokumentu
nie daje takiego dodatkowego przejścia. Twarde kwalifikacje nadal stosowane pierwsze.

`include_older`, tekst i legacy reference zachowują dotychczasowe zasady rozszerzenia
okna. Jawne `date_from/date_to` nadal filtrują `FinancialTransaction.date`, także
przy zakupowym dodatkowym przejściu; UI opisuje je jako zakres **daty zapisu w historii**.
Nie dodajemy teraz selektora wielu semantyk filtra. Wartości błędne nie powodują POST.
Dotychczasowe kody reasons pozostają kompatybilne; nowe uzasadnienia wyraźnie odróżniają
okno daty zapisu od porównania zakupowego, zamiast pokazywać sprzeczne ogólne „pasuje”.

## 6. Wskazówka nazwy, planowane konto i kolejność

W tej wersji nie ma „zweryfikowanego kontrahenta bankowego”. Wyłącznie deterministycznie
sprawdzamy, czy **cała niepusta nazwa sprzedawcy jako fraza tokenów** występuje w opisie
transakcji: Unicode normalization, casefold, interpunkcja/odstępy jako separatory;
bez dopasowania części słowa. Techniczny prefiks `[actual:...]` nie jest dowodem nazwy.
Bez aliasów, fuzzy matching, zewnętrznych słowników, NLP, NIP/IBAN extraction lub AI.
Brak trafienia nie oznacza niezgodności kontrahenta. To świadomie ostrożna pierwsza wersja.

Uzasadnienie: „Nazwa sprzedawcy z dokumentu występuje w opisie płatności”, nigdy
„To na pewno ten kontrahent”. Nazwy/opisy są niezaufanym zwykłym tekstem, bez HTML/link execution.

Zgodność z `bill.payment_account_id` jest tylko informacją. Inne niż planowane konto
nie blokuje historycznej alokacji; brak planu nie oznacza niezgodności. Nie zmieniamy
planu konta ani jego budżetowości.

Stabilna kolejność kandydatów (decyzja autora):
1. Istniejący jawny legacy Inbox reference — jak dziś, bez omijania kwalifikacji.
2. Mniejsza różnica pierwotnej kwoty do sumy dokumentu — jak dziś.
3. Wśród powyższych remisów trafienie frazy nazwy sprzedawcy.
4. Mniejsza bezwzględna różnica dni wybranej, jawnie opisanej pary dat.
5. ID transakcji i postingu jako deterministyczny tie-break.

Brak wstępnie zaznaczonego zwycięzcy. Pozycja na liście to pomoc, nie zgoda na powiązanie.

## 7. Kontrakt odczytu i zachowanie dialogu

Rozszerzenia istniejących `BillCandidate` / `BillCandidatePage`, nie nowe endpointy zapisu:
- opis transakcji, waluta, nullable zakup/księgowanie ze źródłami;
- struktura porównania dat (rodzaje/datowane wartości/różnica/okno);
- sygnał nazwy w opisie oraz zgodność planowanego konta;
- powód niedostępności całej strony, oddzielony od pustej listy.

Nowe pola addytywne, z sensownymi domyślnymi brakami; `date`, IDs, amounts, reasons,
recurring warnings, `total/limit/offset` pozostają. Frontend nie zgaduje powodów ani dat,
gdy starsza odpowiedź ich nie zawiera. Nie wymaga to migracji ani backfillu.

W obecnym dialogu dodatkowo czytelne opisy kwot/dat i kontrolowane etykiety reasons;
opisy kandydata i sprzedawcy jako escaped text. Odrębne loading / błąd z ponowieniem /
brak wyników w filtrach / niedostępność dokumentu. Pusta lista nie dowodzi braku płatności.

Zmiana filtrów/strony, ponowienie lub odświeżenie kandydatów usuwa zaznaczenie i
potwierdzenie recurring-conflict. Podczas pobierania lub błędu nie można wysłać alokacji
na podstawie starej listy; guard także w handlerze, nie tylko disabled button.
Kwota wpisana przez człowieka może pozostać; nic nie jest samoczynnie przydzielane.

409 nadal zachowuje pola, wymaga odświeżenia dokumentu i nowej jawnej decyzji/wyboru.
Nie zmieniamy istniejącej semantyki receipt/retry po niepewnym wyniku zapisu. GET nie
rezerwuje pojemności i nie tworzy trwałej propozycji; mutator ponownie waliduje stan
po blokadach jak dziś. Nie obiecujemy zamrożenia opisu/rankingu osobnym tokenem.

„Powiąż istniejącą” nigdy nie przełącza się automatycznie na „Zarejestruj płatność”,
także po błędzie/pustej liście. Osobny stary tryb rejestracji z ostrzeżeniem i potwierdzeniem
pozostaje bez zmiany zasad. Nie dorabiamy tutaj nowego procesu tworzenia expense.

## 8. Zabezpieczenia i świadome non-goals

- Bez nowych postings/transakcji/zmian kwot, kategorii, dat, walut lub Actual mappings
  w ścieżce sugestii/linkowania istniejącej płatności. Dotychczasowe allocation+audit
  powstają dopiero po ręcznym zatwierdzeniu przez istniejący mutator.
- Bez automatycznego linkowania, wysyłania przelewów, opt-in, reguł, zmian polityk AI,
  nowego OCR/LLM, importu wyciągów, korekt historii lub batchu wcześniejszych danych.
- Bez rozszerzenia rozliczeń na FX/EUR/USD/refunds/raty/nadpłaty lub nowego modelu payee.
- Bez nowych tabel, migracji, trwałych scoringów, cache'u będącego źródłem prawdy.
- Zachować lock graph, owner checks, actual/loan/pending/coverage guards, retry/audit,
  obecną księgę i istniejące rozliczenia. Nie nadpisywać oryginalnych plików.
- Nie zwiększać liczby zapytań per kandydat dla nowych pól; wykorzystać istniejącą
  relację selectin lub owner-scoped batched read. Bez szerokiej przebudowy query engine.

## 9. Scenariusze odbioru do przyszłego planu

1. Zakup2026-10-30/księgowanie2026-11-02 i sprzedaż2026-10-30: obie daty pokazane,
   porównanie zakup↔sprzedaż, wydatek/postings/date metadata nienaruszone.
2. Dwie płatności tej samej kwoty: sygnał nazwy i data rozstrzygają kolejność remisu;
   bez trafienia nie powstaje negatywna tożsamość kontrahenta ani autozaznaczenie.
3. Brak metadanych: jawny legacy fallback, nie fałszywa data księgowania. Obce metadata
   nie trafiają do odpowiedzi. Brak dat dokumentu: jawne odniesienie do dziś.
4. Kandydat dawniej poza oknem staje się widoczny dzięki explicitpurchase w ±W;
   wcześniej widoczne nadal widoczne. Jawny zakres daty zapisu nadal ogranicza wynik.
5. Dokument100/płatność100 już częściowo alokowana: pokazane różne pojemności;
   nie liczyć dwóch stron/splitów jako200 ani nie przekroczyć limitu przy zapisie.
6. Pending/future/FX/transfer/income/loan/innyowner/błędny ledger pozostają wykluczone,
   nawet przy trafieniu tekstu i zakupu. Różne planowane konto tylko ostrzega.
7. Draft/inactive/nonPLN/fullyreconciled: jawny stan niedostępności. Brak wyników,
   loading i błąd nie są tym samym; retry zachowuje filtry, usuwa zaznaczenie.
8. Zmiana filtrów/strony/refetch/409 nie pozwala użyć starego wyboru; niepewny zapis
   nadal ponawiany istniejącym receipt, bez nowego expense/duplikatu alokacji.
9. Wiele źródeł jednego dokumentu nie mnoży kandydatów lub kosztu. GET read-only;
   allocate/unlink zachowują stare testy owner/capacity/concurrency/audit i ledger.
10. Frontend unit i E2E desktop/mobile: jasne daty/powody, PLN, błędy/retry/stale,
    jedna ręczna alokacja, bez requestu do tworzenia transakcji. Syntetyczne fixtures.

Przyszły plan obejmie TDD, testy integracyjne PostgreSQL, regresje istniejących mutatorów,
frontend unit/E2E, pełne lint/types/tests i jeden końcowy review. Ta sesja dokumentacyjna
nie uruchamia tych testów ani żadnego endpointu/DB. Wydanie wymaga osobnej zgody na
dokładną rewizję i spójny backend/frontend; worker zależnie od rzeczywistego pakietu.

## 10. Builder check / decyzje pozostawione wykonawcy

Read-only builder check zakończony: **„nothing important left”**
(`ses_e4ac3f43bffeZniSpFmVMzIllg`). Nie zgłoszono pytań blokujących plan ani potrzeby
rozszerzenia zakresu. Projekt nadal czeka na akceptację użytkownika; review nie jest
zgodą na kod, migrację lub wdrożenie.

Wykonawca wybiera nazwy nowych pól/enumów, lokalną strukturę helperów i komponentów,
bezpieczne skracanie długich opisów i szczegóły batch query w istniejącym stacku.
Nie może zmienić powyższych znaczeń dat/filtrów, reguł kolejności, PLN-only, braku
autozapisu lub ochrony dotychczasowej księgi bez ponownego uzgodnienia zakresu.
