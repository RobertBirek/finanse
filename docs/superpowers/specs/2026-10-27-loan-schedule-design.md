# Q7 — harmonogram i powiązanie płatności (pierwszy slice)

Aktualizacja28.10: po implementacji użytkownik osobno zatwierdził main/push/deploy
oraz addytywną migrację schematu. Poniższe ograniczenia etapu implementacji nie
blokują tego wydania; nadal obowiązuje brak importu i mutacji historycznej księgi.

## Kontekst i zgoda

Użytkownik zaakceptował roadmapę waluty → Q7 → pozostałe zobowiązania i polecił
realizację Q7. Potwierdził, że dostarczony harmonogram kredytu dotyczy Audi Q7.
Waluty są gotowe w0d52f9d, jeszcze bez integracji/deployu. Pełne prywatne kwoty
i dokumenty bankowe nie trafiają do tego projektu ani fixtures.

W sprawdzonym wcześniej odczycie pełna rata była transferem na konto zadłużenia,
podczas gdy dokument rozróżnia kapitał i odsetki. Zgodność matematyczna z planem
nie dowodzi wykonania płatności bankowej. Konto importowane jest również oznaczone
jako budżetowe; nie zmieniamy tego automatycznie.

## Cel pierwszej iteracji

Dać użytkownikowi rzeczywisty, zapisywany w PostgreSQL harmonogram kredytu:
kapitał/odsetki/opłaty, terminy, częściowe i pełne pokrycie istniejącymi płatnościami.
Nie tworzyć żadnej transakcji finansowej podczas dodawania planu lub przypisywania.

To **nie jest jeszcze moduł księgowania nowych złożonych spłat**. Rozpoznanie
odsetek w raportach kosztów i korekty dawnych pełnych transferów to następny slice.
Brakująca semantyka długu nie zostanie zastąpiona kategorią nazwaną „kapitał”.

## Zasady niezmienności

- PostgreSQL źródłem prawdy, BIGINT w groszach, pierwszy slice PLN.
- Finansowa historia, postingi, Actual mapping, daty i kwoty pozostają niezmienione.
- Umowa nie tworzy konta: wskazuje istniejące konto zadłużenia i rachunek spłaty.
- Saldo konta kredytu czytamy z księgi i nazywamy **saldo księgowe**, nie potwierdzony
  pozostały kapitał. Nie zapisujemy drugiego, ręcznie zmniejszanego salda długu.
- Sumy kapitału/odsetek/opłat w harmonogramie są planem, nie kosztami poniesionymi.
- Pokrycie raty przelewem nie jest dowodem poprawnego rozksięgowania kapitału/odsetek.
  Każde powiązanie pokazuje „Płatność powiązana; podział księgowy do uzgodnienia”.
- Dane oryginalnego harmonogramu nie są automatycznie importowane do produkcji.
  UI umożliwi ręczne wprowadzenie; przegląd pliku/zbiorczy import to osobny zakres.

## Modele w domenie finance

### LoanAgreement

`user_id`, `name`, `account_id` (konto zadłużenia), `payment_account_id` (rachunek
spłaty), `is_active`, standardowe id/timestamps. Konta różne, własne, aktywne, PLN.
Jedno konto zadłużenia przypisane do jednej umowy, rachunek spłaty może być wspólny.
Konta są niezmienne po utworzeniu umowy; można edytować nazwę/archiwizować umowę.
Archiwizacja nie oznacza spłacenia i nie usuwa historii/powiązań.

### LoanInstallment

`user_id`, `loan_id`, `number` (dodatni, unikalny w umowie), `due_date`,
`principal_pln`, `interest_pln`, `fees_pln`. Składniki >=0, suma >0 i mieści się
w bezpiecznej reprezentacji kwot API. Wszystkie kwoty całkowite w groszach.
Nie przechowujemy sumy jako niezależnego pola: wyliczamy ją ze składników.
Daty mogą obejmować przeszłość i przyszłość; sam termin nie oznacza zaległości
potwierdzonej bankiem ani wykonania operacji.

Ratę można zmienić/usunąć tylko bez powiązań. Nie ma automatycznego generatora
stopy procentowej, równych rat, nadpłat ani przeliczenia przez LLM.

### LoanPaymentLink

`user_id`, `installment_id`, `transaction_id` (globalnie unikalny), standardowe
id/timestamps. Kwota jest odczytywana z bankowego postingu, nie kopiowana do licznika.
Jedna transakcja może pokrywać jedną ratę, wiele transakcji może pokryć jedną ratę
częściowo. Podział jednego przelewu na kilka rat i nadpłaty są poza pierwszym slice.
FK do transakcji i raty RESTRICT — nie wolno przypadkowo stracić powiązania.

## Walidacja i powiązanie

Użytkownik wybiera istniejący transfer, nigdy automatyczne dopasowanie po kwocie.
Weryfikujemy: właściciel, nie-pending, data <= dzisiaj, typ transfer, dokładnie dwa
postingi kont bez kategorii: debit rachunku spłaty i credit konta kredytu, PLN,
jednakowa rzeczywista kwota i księgowa, bez przewalutowania. Niedopasowane inne
operacje nie są traktowane jako nowe ani błędne.

- Suma powiązanych płatności nie może przekroczyć planowanej raty.
- Ponowne powiązanie tej samej transakcji z tą samą ratą jest idempotentne.
- Próba ponownego użycia w innej racie/umowie daje409.
- Częściowa wpłata zmniejsza „do pokrycia”, nie planowany kapitał i nie saldo księgi.
- Ręczne odpięcie usuwa tylko powiązanie; przelew pozostaje nietknięty.
- Nazwa/status aktywności umowy nie zmieniają rachunku ani historii.
- Po powiązaniu zablokować usunięcie transakcji, zmianę jej daty lub pending;
  opis może być edytowany. Najpierw trzeba jawnie odpiąć powiązanie.
- Blokady loan row i transaction row serializują równoczesne przypisanie,
  chronią limit raty i wyścig z edycją/usunięciem transakcji. Zasady kolejności
  blokad opisuje plan; odczyt po blokadzie odświeża identity map ORM.
- Nowa umowa blokuje zmianę waluty obu wskazanych kont, także gdy mają saldo0.
  Tworzenie umowy współdzieli istniejące blokady walidacji waluty.
- Owner-scope wszystkich endpointów; inne zasoby404, walidacja422, konflikt409.

## Odczyt i statusy

Rata: `total_pln`, `paid_pln` (suma prawidłowo powiązanych postingów), `remaining_pln`,
`payment_status`: `unpaid|partial|paid`. Osobno informacja o terminie przeszłym.
Nie ma ręcznego przełącznika „zapłacono” bez rzeczywistej transakcji.
Nie nazywamy `sum(principal rat bez pokrycia)` pozostałym kapitałem kredytu.
Umowa: saldo księgowe, sumy planu i pokrycia, informacja o konieczności uzgodnienia
podziału. Odczyty w grupowych zapytaniach, bez SELECT per rata.

### Kontrakt API

- `LoanResponse`: `id`, `name`, `account_id`, `payment_account_id`, `is_active`,
  `currency="PLN"`, `ledger_balance_pln` (ze znakiem z księgi),
  `planned_principal_pln`, `planned_interest_pln`, `planned_fees_pln`,
  `total_planned_pln`, `paid_pln`, `remaining_pln`, `requires_accounting_review=true`.
- `LoanDetailResponse`: powyższe oraz `installments: LoanInstallmentResponse[]`.
- `LoanInstallmentResponse`: `id`, `number`, `due_date`, `principal_pln`,
  `interest_pln`, `fees_pln`, `total_pln`, `paid_pln`, `remaining_pln`,
  `payment_status`, `payments`.
- Element `payments`: `id` linku, `transaction_id`, `transaction_date`, `amount_pln`.
- Kandydaci: `{items:[{transaction_id,transaction_date,description,amount_pln}],total,limit,offset}`.
  Kolejność `(date DESC, created_at DESC, id DESC)`, limit1–100, offset>=0,
  wyłącznie poprawne nieprzypisane transfery o kwocie<=remaining raty.
  Istniejące powiązania widoczne w payments; endpoint link pozostaje idempotentny.
  Bez automatycznego okna „bliska data” i bez pobierania całej historii do klienta.
- POST umowy: `name`, `account_id`, `payment_account_id`; PATCH: `name?`, `is_active?`.
- POST/PATCH raty: `number`, `due_date`, `principal_pln`, `interest_pln`, `fees_pln`
  (PATCH pola opcjonalne, jawne null zabronione). POST linku: `transaction_id`.
- POST umowy zwraca LoanDetailResponse; POST/PATCH raty zwraca LoanInstallmentResponse;
  POST linku zwraca LoanDetailResponse; DELETE raty/linku204; GET/list zgodnie z nazwami.
- Ścieżki: prefix `/api/finance/loans`, dalej `/{loan_id}`,
  `/{loan_id}/installments`, `/{loan_id}/installments/{installment_id}`,
  `/{loan_id}/installments/{installment_id}/payments`,
  `/{loan_id}/installments/{installment_id}/payment-candidates`,
  `/{loan_id}/payments/{link_id}`.

`remaining_pln` umowy nazywamy „Do pokrycia w harmonogramie”. Liczby ścisłe całkowite,
każdy składnik i suma<=9_007_199_254_740_991; CHECK w bazie, nie tylko Pydantic.
Transfer ma fx_rate1 i source_amount==base_amount_pln w obu nogach.
Delete_account sprawdza obie role umowy i daje409. Guard waluty dotyczy także
archiwalnych umów. Owner checks serwisowe obowiązkowe; unikalne FK/RESTRICT
odzwierciedlają reguły tożsamości, nie wyłącznie domyślny stan ORM.

## Interfejs pierwszej iteracji

Ustawienia finansów → „Kredyty i pożyczki”: lista umów i formularz powiązania
istniejących kont. Po wyborze umowy lista rat, formularz raty (numer/data/3 kwoty),
sumy i ręczne powiązanie przelewu po jego ID lub z listy kandydatów z datą/kwotą.
Kandydaci to tylko pomoc w wyborze, nie dowód tożsamości ani domyślna decyzja.
Wszędzie jawne rozróżnienie planu, zapłaconej kwoty i nieuzgodnionego księgowania.

Zachowujemy istniejące style i dostępność, mobile/desktop, dwa motywy.
Brak automatycznego dopisywania nowych pozycji do istniejącej prognozy płynności:
unikamy podwójnego naliczenia raty obecnej już w Harmonogramach. Włączenie rat do
wspólnej prognozy, migracja ich starego harmonogramu i właściwe rozksięgowanie
nowej spłaty będą osobną iteracją, nie ukrytym efektem tej strony.

## Migracja i granice wdrożenia

Addytywna migracja trzech tabel po b8e4c2f1a7d9, bez backfillu i mutacji starej
treści. W tej sesji tylko kod/migracja w gałęzi i testy lokalnej finanse_test.
Bez produkcyjnego upgrade, importu harmonogramu, korekty odsetek lub deployu.
Rzeczywiste umowy/raty użytkownika nie są zakładane przez agenta w produkcji.

## Kryteria akceptacji

- Plan i powiązania nigdy nie zmieniają liczby/treści finansowych transakcji/postingów.
- Rata syntetyczna 100000 =90000 kapitału +9000 odsetek +1000 opłat.
  Transfer40000 daje partial/remaining60000, kolejny60000 paid/remaining0,
  dodatkowy1 jest odrzucony. Żaden koszt nie pojawia się w raporcie od samego linku.
- Powtórzenie i wyścigi nie tworzą duplikatów ani nadmiernego pokrycia.
- Pending/przyszłe/foreign/cross-currency/nieprawidłowe postingi odrzucone.
- Zmiana/usunięcie połączonej transakcji nie unieważnia po cichu stanu raty.
- Migracja na izolowanej bazie zachowuje stare rekordy i ma jeden head.
- Pełne pytest, lint/types, frontend test/build/E2E i niezależny review.
