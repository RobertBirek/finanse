# Karty kredytowe i plany ratalne

> Podział ekranów wdrożony w release `7801ba5` (2026-11-08), schemat `739144d5eaef`.
> Samo wdrożenie nie konfigurowało Velo. Po osobnej zgodzie użytkownika warunki
> istniejącego profilu zapisano 2026-11-08; nie utworzono kolejnego rachunku.

## Konfiguracja istniejącego konta

W **Ustawienia → Finanse → Konta i rachunki** edytuj istniejące konto i wybierz
typ **Karta kredytowa** (`credit_card`). Wypełnij pojawiające się warunki i zapisz
całe konto jednym przyciskiem. Nie twórz kolejnego rachunku dla istniejącej karty.
Przy dodawaniu zupełnie nowej karty ten sam typ i pola są w formularzu nowego konta.

Zapis konta i profilu jest atomowy: błędne warunki lub nieaktualna wersja nie zapiszą
częściowej zmiany nazwy/typu. Nie ustawia salda i nie przepisuje historii. Każda karta
ma odrębny profil, limit, oprocentowanie i cykl; można mieć wiele kart.
Zmiana samej nazwy/koloru nie wymaga ponownego zapisu warunków.

Waluta karty to PLN; po zapisaniu profilu waluta i typ są chronione. Konto można
dezaktywować, nie usuwać wraz z historią; nieaktywne karty mają rozliczenia tylko
do odczytu. Kont powiązanych z oddzielną umową kredytową nie można równocześnie
konfigurować jako kart. Zwykły typ **Kredytowe** (`credit`) pozostaje odrębny.

## Przegląd wielu kart

**Ustawienia → Finanse → Karty kredytowe** to wyłącznie zbiorcza lista kart z bieżącym
limitem, zadłużeniem i dostępną kwotą. Zwykłe rachunki nie są tu proponowane do wyboru.
Nieaktywne karty są oznaczone; błąd odczytu nie jest przedstawiany jako zerowe saldo.
Brak profilu ma komunikat o potrzebie uzupełnienia warunków, nie fikcyjny limit0.

- **Wyciągi i raty** otwiera szczegóły wybranej karty: wyciągi, plany, spłaty i koszty.
- **Edytuj konto** otwiera formularz dokładnie tego konta; tylko tam zmieniasz warunki.

Nowe adresy: `/settings/finances/cards/:accountId` i
`/settings/finances/accounts?edit=:accountId`. Dawne linki `cards?account=...`
przekierowują do szczegółów właściwej karty.

## Indywidualne warunki karty Velo

Dla wskazanej przez użytkownika karty Velo uzgodniono:
- limit **33 600 zł**;
- oprocentowanie roczne **14,50%**;
- dzień zamknięcia cyklu **17** (okresy od 18. dnia poprzedniego miesiąca);
- domyślny dzień spłaty **12**;
- maksymalny warunkowy okres bezodsetkowy **57 dni**.

To indywidualne warunki tej karty, nie domyślne ustawienia wszystkich kart.
Nie są automatycznie przypisywane przez dopasowanie nazwy konta. Aktualizacja
warunków wymaga aktualnej wersji formularza i jest zapisywana w audycie.

## Limit i saldo

- Zadłużenie pochodzi z ujemnego salda **zaksięgowanych** operacji w księdze do dziś.
- Niezaksięgowane obciążenia dodatkowo rezerwują dostępny limit.
- Niezaksięgowane wpłaty nie zwalniają limitu.
- Dostępny limit = limit − zadłużenie − rezerwacje, co najmniej zero.
- Przekroczenie i nadpłata są pokazywane oddzielnie. Nie zakładamy, że nadpłata
  automatycznie zwiększa bankowy limit płatniczy.
- Plany ratalne klasyfikują kapitał już obecny w księdze; nie dodają go ponownie.

Podsumowanie karty jest również dostępne przy jej transakcjach. Informacje
pochodzą z backendu, nie z niezależnej kalkulacji salda we frontendzie.

## Wyciągi i spłata

Wpisz okres, rzeczywisty termin spłaty, saldo zadłużenia i minimalną kwotę oraz
identyfikator dokumentu źródłowego. Data z wyciągu ma pierwszeństwo przed
domyślnym dniem spłaty: w udostępnionych dokumentach występują dni 12, 13 i 14.
Historyczny wyciąg nie jest aktualnym saldem karty.

Porównanie pokazuje różnicę między zaksięgowanym zadłużeniem księgi na koniec
okresu a zadłużeniem podanym przez bank. Różnica wymaga sprawdzenia źródeł, nie
powoduje automatycznej transakcji wyrównującej. Porównanie używa obecnego stanu
zaksięgowania transakcji; nie odtwarza nieistniejącej historii zmian `is_pending`.

Najpierw zapisz/zaimportuj rzeczywisty przelew z własnego rachunku na kartę.
Następnie przypisz jego kwotę do wyciągu. To **transfer**, nie ponowny wydatek.
Możliwa jest spłata częściowa. Dostępna kwota przelewu oraz pozostała kwota
wyciągu są sprawdzane przez backend, także przy równoległych żądaniach.

Ten sam przelew może opisywać spłatę wyciągu i planu, ponieważ są to dwa widoki
tego samego przepływu. Każdy z tych wymiarów ma osobny limit alokacji; nie wolno
dwukrotnie rozdzielić całego przelewu pomiędzy różne plany lub różne wyciągi.

## Nowe plany ratalne

Każdy plan ma własne oprocentowanie, kapitał, datę pierwszej raty, liczbę rat
i opłaty. Stopa planu nie jest dziedziczona automatycznie z oprocentowania karty.
Dozwolone są również plany 0%. Utworzenie planu w aplikacji **nie zawiera umowy
z bankiem** i nie uruchamia wypłaty.

Wybierz istniejący zaksięgowany zakup lub wypłatę/przelew obciążający kartę.
Suma kapitałów wszystkich planów na tej transakcji nie może przekroczyć jej
kwoty. Przy nowym finansowaniu najpierw należy zapisać rzeczywisty przepływ.

Szacunek stosuje równy kapitał, APR/12, zaokrąglenie do grosza oraz prowizję
w pierwszej racie. Ostatnia rata zachowuje wszystkie grosze kapitału. Termin
na koniec miesiąca jest odpowiednio skracany w lutym. To **szacunek**, a nie
bankowy harmonogram annuitetowy lub kalkulator konkretnej taryfy.

Przed przypisaniem spłat można zastąpić szacunek harmonogramem bankowym. Suma
kapitału musi pozostać identyczna, numeracja i daty muszą być uporządkowane.
Po przypisaniu spłat harmonogram jest chroniony. Wcześniejsza spłata przypisuje
rzeczywisty przelew i faktyczny podział kapitał/odsetki/opłaty. Pełna spłata
kapitału zamyka plan; przyszłe szacowane odsetki nie stają się przez to kosztem.

**Granica reprezentacji:** pełny kapitał nowego planu ma być już w księdze.
Nie wolno drugi raz dopisywać go jako kosztu przy późniejszej prezentacji rat.
Niektóre wyciągi Velo pokazują osobno kapitał niewymagalny i saldo bieżącego
rozliczenia. Nie należy utożsamiać samego tego nagłówka z całym zadłużeniem
ani importować go jako automatycznej korekty księgi. Bez uzgodnionych danych
różnica pozostaje widoczna. Stare plany użytkownik potwierdził jako zamknięte;
ta zmiana nie odtwarza ich automatycznie ani nie zmienia historycznych operacji.

## Odsetki, opłaty i zwroty

Wybierz wyraźnie, czy chcesz **zaksięgować nowy koszt/zwrot**, czy **powiązać
istniejący zapis**. W drugim przypadku kwota, data, konto, kategoria oraz kierunek
muszą odpowiadać rzeczywistym zapisom. Nie powstaje druga transakcja.

Nowy koszt tworzy dwa bilansujące się postings: obciążenie karty i koszt kategorii.
Zwrot odsetek/opłaty pozostaje korektą kosztu (`expense` z odwróconymi zapisami),
zmniejsza zadłużenie i koszt netto, nie tworzy przychodu. Taka korekta jest
dozwolona tylko przez kontrolowany serwis kart, nie przez samą nazwę `source`
w żądaniu zwykłej transakcji. Starsze importy o innym typie nie są automatycznie
przeklasyfikowywane na potrzeby nowej funkcji.

Harmonogramy i kalkulator odsetek **nie księgują kosztów**. Kalkulator pokazuje
prosty szacunek ACT/365 dla podanego kapitału, liczby dni i bieżącej stopy karty.
Nie uwzględnia automatycznie warunków utraty grace period, kolejności zaliczania
wpłat, innych stóp planów, taryf gotówkowych i bankowych zasad zaokrągleń.

## Pomyłki, ponowienia i ochrona historii

Identyczne ponowienie żądania z tym samym kluczem zwraca istniejący rekord;
zmienione dane z tym samym kluczem są konfliktem. Formularz zachowuje wpisane
dane po błędzie. Nie wysyłaj ponownie z nowym kluczem bez sprawdzenia księgi,
jeśli nie wiesz, czy pierwsze księgowanie się udało.

Po usunięciu metadanej jej dawny klucz pozostaje zablokowany przez zapis utworzenia
w audycie. Opóźnione ponowienie nie może ponownie zaksięgować odsetek, których
transakcja nadal istnieje. W takim przypadku otrzymasz konflikt i należy sprawdzić
księgę oraz ewentualnie powiązać istniejącą transakcję. Zapisów utworzenia kart
w audycie nie wolno usuwać bez zachowania tych zabezpieczeń kluczy.

Można cofnąć powiązanie spłaty lub usunąć błędne **niepowiązane metadane** planu,
wyciągu albo opisu kosztu. Operacja jest audytowana i nie usuwa transakcji.
Plan z rozliczeniami lub kosztami zachowuje historię. Powiązane transakcje są
chronione przed usunięciem, zmianą daty i statusu oczekującego, również przez
oddzielny edytor dat. Właściwe korekty bankowe zapisuj jako nowe rzeczywiste operacje.

Pierwotna migracja `00a9ccb532b9` jest addytywna. Jej cofnięcie usuwa nowe tabele
tylko wtedy, gdy wszystkie są puste; zapisane warunki lub rozliczenia blokują downgrade.

Nowa migracja `739144d5eaef` jedynie nadaje typ `credit_card` kontom z istniejącym
profilem tego samego właściciela. Nie rozpoznaje karty po nazwie ani po samym typie
`credit`; nie tworzy profili, nie zmienia sald/postings i nie usuwa danych. Jej downgrade
przywraca klasyfikację `credit`, zachowując profile i rozliczenia. Migrację produkcyjną
wykonano po osobnej zgodzie: nie było istniejących profili, więc nie zmieniła żadnego
rachunku. Kontrolowany rollback wyłącznie tej klasyfikacji do `00a9ccb532b9` przed
starymi obrazami jest osobno zatwierdzony; nie był potrzebny. Nie cofać wcześniejszych
migracji ani nie odtwarzać bazy jako niejawnego kroku rollbacku.
