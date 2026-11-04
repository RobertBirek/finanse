# Etap 2 — zatwierdzana kategoryzacja i podział istniejącego wydatku

## Intencja i status

Kontynuacja kontraktu `2026-11-03-smart-categorization-design.md` po lokalnym etapie
dat63e2b9c. Użytkownik odpowiedział „ok, działaj dalej” na następny etap: zmiany i podziały
kategorii bez dublowania płatności. Użytkownik zatwierdził pełny plan656e9e6 słowem „tak”
przed zmianą kodu aplikacji. Zgoda obejmuje realizację lokalną, nie jest zgodą na wdrożenie,
produkcyjne mutacje ani uruchomienie przetwarzania historii.

## Co użytkownik otrzyma

- Dla obsługiwanego wydatku: osobna akcja „Zmień kategorie”, aktualny podział i kwota
  płatności. Jedna kategoria oznacza zwykłą zmianę; kilka wierszy oznacza split.
- Użytkownik wybiera istniejące kategorie/podkategorie wydatkowe i wpisuje kwotyPLN.
  Widzi sumę i brakującą/nadmiarową kwotę. Przykład:100PLN→80PLN spożywka/20PLN chemia.
- Nic nie zapisuje się przy dodaniu wiersza, edycji lub zamknięciu okna. Dopiero
  przycisk „Zatwierdź podział” wysyła kontrolowane polecenie, po pokazaniu skutków.
- Zmienia się wyłącznie rozkład kategorii w budżetach/raportach, nie saldo ani liczba
  płatności. Dotychczasowa data zakupu i księgowania oraz oryginały/linki bez zmian.
- Po zatwierdzeniu widoczna ręczna decyzja z wersją. Powtórna ręczna zmiana jest możliwa,
  ale przyszły agent nie może sam nadpisać tej decyzji. Brak metadanych nie oznacza,
  że istniejąca kategoria jest „bez kategorii” albo że wolno ją zmienić automatycznie.
- Stare dane nie są masowo poprawiane. Nieskategoryzowana historia i Actual zachowują
  osobny workflow etapu6; ten ekran nie jest ukrytym uruchomieniem takiej partii.

## Zakres i wybory implementacyjne

Uzgodnione: jedna płatność, min.2postings, suma=0, PLN, groszeBIGINT, zawsze zatwierdzany
split, owner-scope, audyt/stale protection i zachowanie accountposting/alokacji. Dobór
tabel, endpointów i algorytmu aktualizacji poniżej to decyzje wykonawcze, nie dodatkowe
deklaracje użytkownika. Istniejący stack i wygląd formularzy/dialogów, bez zależności.

Pierwszy zakres polecenia: zaksięgowane dodatnie wydatkiPLN z jednym postingiem kontowym i
przeciwnymi kategoriami. Transfer/income/exchange/refund/FX/nieprawidłowa stara księga
nie są przerabiane na taki wydatek. Ręczne wydatki oraz płatności utworzone z dokumentu
to kandydaci do obsługi; przypięta historiaActual i pożyczki wymagają odmowy z powodem.
Obsługiwane źródła: `manual` i `document_payment`. Ręczna zmiana już podzielonego
wydatku i scalenie kategorii należą do tego samego polecenia. Wyłączone: `actual`,
każdyActualImportMapping transakcji, LoanPaymentLink, pending i inne źródła. Aktywna
kategoria zaimportowana kiedyś zActual pozostaje dopuszczalnym celem: wybór jej ID
nie zmienia jej definicji, mappingu ani przypiętej historii.

## Źródło prawdy i model

- Kwoty raportów nadal wyłącznie w kategorii postings księgi. Nie tworzyć równoległej
  tabeli splitów, z której raporty liczą alternatywne sumy.
- Nowa zależna tabela stanu kategoryzacji1:1 przechowuje tylko wersję, ręczną proweniencję
  i skróty stanu przed/po decyzji, nie drugi zestaw kwot. Ręczne pochodzenie oznacza
  ochronę przed przyszłą automatyzacją; ponowna ręczna zmiana nadal jest możliwa.
  Bez nowych mappedcolumns
  naFinancialTransaction i bez zmiany algorytmu fingerprintActual.
- Stary stan i nowy stan kategorii w audycie, bez treści dokumentu/paragonu/promptu.
  Wiersz stanu powstaje przy jawnej decyzji; GET nie backfilluje metadanych.
- Addytywna migracja po84f28fe23ab8: wyłącznie nowa tabela/check/index/FK. Brak backfillu
  lub zmiany dawnych dat/kategorii. Downgrade z użytymi metadanymi ma odmówić pod lockiem.

## Polecenie i ochrona starej decyzji

- Odczyt kontekstu zwraca sumęPLN, dotychczasowe kategorie, wersję0 bez nowego stanu,
  token bieżącej księgi i eligibility/reason. Odczyt nie obiecuje, że zapis się uda:
  serwer ponownie waliduje wszystko po zablokowaniu wierszy.
- Po edycji użytkownik wybiera „Sprawdź podział”. Serwer robi niemutujący podgląd:
  sprawdza pierwotny snapshot, wybrane kwoty i stan kategorii, po czym zwraca różnicę
  przed/po oraz nowy token obejmujący także docelowe kategorie i ich hierarchię.
- Dopiero z tego podglądu użytkownik wybiera „Zatwierdź podział”. Zapis przyjmuje
  identyfikatory kategorii i dodatnie kwoty w groszach, expectedversion oraz token
  sprawdzonego podglądu i `confirmed=true`. Client nie ustala source/proweniencji,
  direction, account_id, payment_id, sourcecurrency, FX, is_budget_impact ani typu.
- Token musi uwzględniać konto/kwotę/całepostings, daty i status transakcji, alokacje,
  mapping/linki i stan kategoryzacji, żeby zmiana inna niż rodzic.updated_at nie mogła
  obejść409. Token końcowego podglądu uwzględnia też znormalizowane części i całe ścieżki
  docelowych kategorii wraz z type/active/updated_at. Zmiana wyboru unieważnia podgląd.
- Suma kwot równa dokładnie kwocie istniejącego postingu kontowego. Backend niczego
  nie dopisuje ani nie zaokrągla; brakujący/nadmiarowy grosz→422, zero mutacji/audytu.
- Każda kategoria własna, istniejąca, aktywna i typuexpense. Bez automatycznego
  tworzenia/scalania/przenoszenia kategorii. Powtórzone kategorie w payloadzie odrzucane.
- Istniejący `FinanceCommandReceipt` zapisuje wynik dla pary właściciel/akcja/klucz.
  Identyczny `Idempotency-Key` i request zwraca zapisany wynik bez ponownego wykonania;
  ten sam klucz z inną intencją→409. Odpowiedź replay jest historycznym potwierdzeniem,
  nie nowym stanem do nadpisania cache: klient ponownie pobiera bieżące odczyty.
- Nowa intencja wymaga świeżej wersji/tokenu; stary podgląd→409. Nowy request z już
  ręcznie zatwierdzonym identycznym podziałem jest no-op po sprawdzeniu wersji/tokenu.
  Pierwsze potwierdzenie niezmienionej kategorii tworzy ręczne metadane/audyt raz.
- Owner404, nieobsługiwana/chroniona/stara operacja409, niepoprawne dane422. CSRF i
  istniejący auth obowiązują także dla tego polecenia; żadnego osobnego dostępuLLM/SQL.

## Tożsamość płatności i powiązania

- Posting kontowy zachowuje ID i wszystkie mappedcolumns. W szczególności nie może być
  usuwany/odtwarzany, boDocumentPaymentAllocation wskazuje właśnie jego ID.
- Genericupdate/delete guard płatności dokumentów nie jest luzowany. Nowy serwis ma
  węższą odpowiedzialność i odrębnie dowodzi, że nie zmienia żadnej cechy płatności.
- Modyfikacja stron kategorii jest zamierzona. Zachować istniejące categorypostingID
  tam, gdzie można dopasować ten sam wiersz; nowe części wymagają nowychcategoryrows,
  a scalenie wymaga usunięcia wyłącznie zbędnychcategoryrows z pełnym audytem.
  To nie jest zgoda na usunięcie postingu kontowego/dokumentu/alokacji.
- Alokacje i ich dokumenty zachowują ID, kwoty, daty, status i rozliczenia. Kategoria
  dokumentu jest jego dotychczasowym kontekstem, nie alternatywnym źródłem raportów.
  UI wyjaśnia ręczne nadpisanie rozkładu transakcji, nie przepisuje dokumentu.
- Pożyczki i Actualpins nie tracą ochrony. Mechanizm nowego polecenia nie może służyć
  do obejścia zgodności zachowanej historii albo zmiany semantyki raty.

## UX błędów i sesji

Ekran korzysta z natywnegoDialog i CategoryPicker, pokazuje obecne kategorie i pełną
kwotę. Odczytany snapshot jest zamrożony na czas edycji. Dwa widoki dwóch kart nie mogą
zatwierdzić dwóch różnych rozkładów na jednej starej wersji. Po409 wpisy zostają, zapis
blokuje się do zamknięcia/odświeżenia; nie ponawiać automatycznie starej zgody.

Sesję identyfikuje sessionVersion z etapu1, nie referencja userobiektu. GETy/cache oraz
delayed mutationcallback nie przenoszą danych między właścicielami lub kolejnymi loginami.
Po sukcesie odświeżyć kategorię/raporty/budżety/listę/szczegóły i powiązane odczyty,
bez ponownego tworzenia wydatku lub uruchomienia przetwarzania dokumentu.

## Odbiór i dalsze etapy

TDD ma wykazać:100→80/20→100, pojedynczy accountposting, niezmienne salda/datymetadata/
alokacje, dokładna suma co do grosza, no-op/retry, stale/foreign/CSRF, blokadaActual/loan/
FX/transfer, dwa równoległe zatwierdzenia, delete/allocation/categoryedit race i rollback
audytu. Raporty/budżety na nowych postings oraz etapie1purchasebasis muszą dawać80/20,
a bank nadal100. Browser375/1440, klawiatura/a11y, błędy409/422 i zmiana sesji.

Pełne/test/lint/typecheck/build/E2E i jeden niezależny whole-review przed commitem.
RzeczywisteLLM/pozycjeparagonu/nowekategorie/historybatch nie należą do tego etapu.

## Wynik builder check i decyzje wykonawcze

Read-only check `ses_e5c9b005effeJ1ZKa1OTo63A7v` nie znalazł pytań blokujących po stronie
użytkownika. Przyjęto: odrębną tabelę metadanych, istniejące FinanceCommandReceipt,
ochronę Actual/loan/FX, niezmienny accountposting i odrębny wąski serwis zamiast
luzowania guardu dokumentów. Tylko podgląd końcowy może obejmować wybrane części:
dlatego plan rozdziela kontekst, niemutujący preview i apply z zatwierdzeniem.

Nie przyjęto ograniczenia „tylko pierwsza zmiana kategorii na zawsze” ani zakazu użycia
kategorii zaimportowanej zActual. Takie ograniczenia blokowałyby uzgodnioną ręczną
korektę i wybór istniejących kategorii. Dopuszczone usunięcia dotyczą wyłącznie zbędnych
postings kategorii we własnej ręcznie zatwierdzonej operacji; audyt zachowuje stan przed.
Przed zmianą serwis odmawia, jeśli jakakolwiek alokacja wskazuje stronę kategorii.

Builder wskazał wspólny `category-tree` lock. Sprawdzenie kodu ujawniło, że
`delete_category` go jeszcze nie bierze, a FKpostings.category_id ma ONDELETESETNULL.
Plan obejmuje synchronizację kasowania kategorii z zatwierdzeniem i regresję tego
wyścigu. Nie zmienia semantyki innych mutacji ani nie usuwa żadnej istniejącej kategorii.
