# Uporządkowanie drzewa kategorii — projekt do zatwierdzenia

## Status i zakres obecnej zgody

Użytkownik zaakceptował przygotowanie pełnego drzewa i mapowania obecnych kategorii
do zatwierdzenia. **To nie zgoda na wykonanie zmian, przepisanie historii, utworzenie
kont, włączenie zgód/reguł ani wdrożenie.** Następnym krokiem po akceptacji projektu
jest odrębny plan operacyjny z bramką zgody przed produkcyjnym APPLY.

## Cel

Czytelne grupy bieżących kosztów, zachowanie przydatnego podziału dostawców i pojazdów,
oddzielenie własnych projektów od opłat zawieszonej firmy oraz proste kategorie rodzinne.
Nie wymuszać nowej interpretacji historycznych, niejasnych zapisów tylko po ich nazwie.

## Prywatność i kompletność materiału

Prywatna taksonomia, imiona i pełne mapowanie ID nie trafiają do Git. Pełen projekt,
źródłowy snapshot, mapowanie i manifest mają pozostać w katalogu operatora:

`/opt/finanse/webapp/category-designs/2026-11-06/` (root-only, poza śledzonym kodem).

Robocza kopia: `/tmp/opencode/category-tree-20261106/`. Dokumentem do zatwierdzenia
jest `proposal-private.md`, a nie sam niniejszy zanonimizowany opis. Szczegółowa tabela
`mapping-private.json` jest artefaktem projektu, nie źródłem prawdy aplikacji.

Snapshot właścicielski READ ONLY/REPEATABLE READ, z statement_timeout i rollback:
65 kategorii (59 expense, 6 income), bez zmian drzewa względem poprzedniego odczytu.
SHA256 źródła: `e813a3e41211ecbdf9782c9804a46c784db6a23692690ea1b79e1190cb51eda2`.
Bez cudzych kont, odczytu sesji, opisów/kwot transakcji lub wywołań modeli.

## Ustalenia użytkownika

- Narzędzia AI i hosting są do własnych projektów; nie traktować ich automatycznie
  jako działalności gospodarczej lub kosztów podatkowych.
- Ogólna kategoria AI obejmuje pozostałe narzędzia, odrębne od nazwanych dostawców.
- Historyczna kategoria przewalutowania oznacza obejście ograniczeń poprzedniego
  programu przy wymianie PLN na EUR/USD, nie faktyczną prowizję.
- Opłata zawieszonej firmy dotyczy obecnie wyłącznie utrzymania konta bankowego.
- Kategoria Apple obejmuje subskrypcje Apple, bez potrzeby dalszego podziału.
- Rodzina: wspólna kategoria i pięć wskazanych osób; brak kolejnych podkategorii osób.
  Pożyczki i ich spłaty użytkownik będzie rozliczać na osobnych kontach, które utworzy sam.

Pozostałe nazwy i rozmieszczenie są propozycjami autora, nie osobno zatwierdzonymi
wymaganiami. W szczególności przesunięcie alkoholu poza Zdrowie wymaga akceptacji całości.

## Proponowany kształt

Wydatki: dom, żywność, zakupy codzienne, zdrowie, dwa istniejące pojazdy, telekomunikacja,
abonamenty/multimedia, narzędzia AI z zachowaniem dostawców, infrastruktura/oprogramowanie,
czas wolny, jedna osobna kategoria opłat firmy, rodzina oraz jeden techniczny koszyk
przyszłych nowych wydatków. Dokładne nazwy: wyłącznie w prywatnym projekcie.

Maksymalnie dwa poziomy, nie dodawać spekulatywnych pustych liści. Przychody pozostają
w ostrożnym wariancie, bez automatycznej reinterpretacji lokat lub bilansu otwarcia.

## Pełne mapowanie i granica operacji

Każda ze wszystkich 65 kategorii, wliczając rodziców, ma dokładnie jeden wpis:
- KEEP: 16 — bez zmian;
- EDIT: 38 — docelowa nazwa/ścieżka przy zachowaniu ID;
- HOLD: 11 — bez zmian, osobny audyt potrzebny do rozstrzygnięcia znaczenia lub referencji.

EDIT opisuje różnicę ścieżki, niekoniecznie osobną mutację wiersza: zmiana nazwy rodzica
może zmienić ścieżkę dziecka przy identycznych własnych name/parent_id. Późniejszy plan
ma aktualizować wyłącznie potrzebne pola, nie generować sztucznych operacji dla dzieci.

W tym wariancie **żadnych scaleń, usunięć, dezaktywacji ani zmian typu**. 14 nowych
węzłów expense (w tym rodzice, rodzina i kategoria techniczna), łącznie 79 węzłów:
73 expense, 6 income. Zachowane wszystkie oryginalne 65 ID.

HOLD obejmuje historyczne FX wraz z rodzicem, niejasne koszyki Inne i ich rodziców,
nieustalone odsetki, osobną kategorię podejrzaną o duplikat oraz kategorie lokat/BO.
Nie znikną z aplikacji: nadal będą widoczne pod istniejącymi nazwami. Pełne mapowanie
nie oznacza zgody na ich automatyczne naprawienie lub wymuszone przypisanie docelowe.

Dla dostawców AI proponowany jest nowy rodzic zamiast przemianowania starego: dzięki
temu zatrzymana historyczna gałąź FX zachowuje identyczną ścieżkę. Dla dwóch pozostałych
historycznych grup zachowujemy rodzica oraz nierozstrzygnięte dzieci.

## Nienaruszalne zasady finansowe

- Pożyczka nie jest zwykłym przychodem, spłata kapitału nie jest zwykłym wydatkiem.
  Kategorie rodzinne dotyczą faktycznych wydatków/bezzwrotnego wsparcia; salda pożyczek
  są na osobnych właściwie ujętych kontach. Nie powielamy tej samej kwoty w kategorii i koncie.
- FX zachowuje obie rzeczywiste kwoty i kurs; ewentualna faktyczna prowizja jest oddzielnym
  kosztem. Projekt nie przekształca danych zastanych ani nie zgaduje drugiej strony wymiany.
- Wydatek poniesiony na własny projekt nie staje się przez to kosztem podatkowym firmy.
- Nie tworzymy kont, sald otwarcia, projektów, kontaktów ani rozdzielania abonamentów.
- Kategoria techniczna jest nowa, bez przypisania historycznych Inne. Jej utworzenie nie
  oznacza wyboru jako marker, włączenia reguł, zgody na eksport AI lub uruchomienia historii.

## Wpływ na historię i bezpieczeństwo przyszłego planu

Zmiana nazw/rodziców wpłynie na prezentację wszystkich dawnych raportów. Sumy grup mogą
się zmienić, bo zmieni się ich skład; nie obiecujemy identycznych sum per grupa.
Kwoty, waluty, kursy, daty, salda, źródło Actual, IDs i powiązania ledgeru muszą pozostać
bez zmian. Żadnego przepisywania postings lub masowego przypisywania kategorii transakcjom.

Przed ewentualnym wykonaniem: świeży właścicielski snapshot, sprawdzenie zmian od projektu,
wszystkich referencji i importów Actual, budżetów, harmonogramów, dokumentów, reguł,
zatwierdzonych produktów i grantów. Zachowanie ID nie gwarantuje niezmienionych zachowań
importera lub fingerprintów reguł po zmianie ścieżki. Zero użyć w postings nie jest dowodem
braku referencji — podejrzanego duplikatu nie scalamy nawet przy zerowym liczniku.

Ewentualne zmiany przez kontrolowane serwisy domenowe, w autoryzowanym zakresie
właściciela, z audytem, blokadą hierarchii i backupem/planem odzyskiwania. Nie używać
operacji kategorii do obejścia ochrony historycznych importowanych transakcji. Jeśli
preflight wykryje niebezpieczną zależność, zatrzymać wykonanie i przedstawić ją użytkownikowi.

## Walidacja projektu i odbiór

Generator sprawdza pełne pokrycie 65 źródeł, unikalność ID i docelowych ścieżek per typ,
14 unikalnych nowych węzłów, brak cykli/sierot, zachowanie typu, niezmienione HOLD/KEEP
oraz najwyżej dwa poziomy. To walidacja dokumentu, nie dowód wykonania migracji.
Żadne narzędzie przygotowujące propozycję nie ma ścieżki APPLY.

Przed przekazaniem: niezależny builder-check prywatnego projektu i tej specyfikacji,
wyjaśnienie ważnych niejasności oraz sprawdzenie manifestu prywatnych artefaktów.
Status po przekazaniu pozostaje **DO ZATWIERDZENIA**. Nie tworzyć planu implementacji,
nowego kodu produktu ani nie wykonywać zmian na produkcji w ramach obecnej zgody.

## Pozostawione autorowi planu

Kolejność operacji w przyszłym zatwierdzonym planie, dokładny format audytu/preflightu,
transport autoryzowanych poleceń serwisowych oraz testy wpływu na zależne odczyty.
Nie pozostawiono swobody zmiany interpretacji HOLD, typu kategorii, liczby rodzinnych
osób, polityk AI lub rozliczeń pożyczek.

## Wynik builder-check

Niezależny reviewer przeczytał pełny prywatny projekt oraz tę specyfikację. Wynik:
**nothing important left**. Walidacja offline odtworzyła docelowe parent_id i nazwy
wszystkich 79 węzłów; HOLD/KEEP zachowują własne name i parent_id, nie tylko tekst ścieżki.
Projekt przekazany do zatwierdzenia; brak zgody na APPLY, plan operacyjny jeszcze nie powstał.
