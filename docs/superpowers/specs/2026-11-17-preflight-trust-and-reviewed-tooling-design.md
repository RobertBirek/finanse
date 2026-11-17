# Preflight: granica zaufania i jawnie zatwierdzone zmiany narzędzi

Status: **projekt do zatwierdzenia; bez implementacji i bez wdrożenia**.
Data: 2026-11-17.

Kontrola wykonalności: zakończona. Builder check wskazał dwa pytania o źródło
zgody i kontekst uwierzytelniania PG; doprecyzowano je w sekcjach3a i5.
Ponowna kontrola wyłącznie tych odpowiedzi: questions answered. Nie jest to
review implementacji, akceptacja artefaktów tooling ani odbiór produkcyjny.

## 1. Cel i podstawa

Użytkownik chce dokończyć bezpieczne wdrożenie szkiców dokumentów i polecił
przygotować osobny plan po review preflightu. Review oraz trzy syntetyczne próby
wykazały niedostateczne wiązanie narzędzi, plików konfiguracji i endpointu PG.
Ponadto V1 prawidłowo odrzuca zmiany własnych narzędzi jako unknown_change_scope.

Nie rozwiązujemy tego przez wyłączenie blokady. Projekt proponuje bezpieczniejszy
checker oraz jawny, osobno zatwierdzony dowód przeglądu konkretnych zmian tooling.
Implementacja będzie wymagać planu, testów i odbioru przed użyciem produkcyjnym.

Uzgodnione przez użytkownika: naprawić wskazane problemy, zachować kontrole,
nie zmieniać danych finansowych i nie przetwarzać masowo dokumentów. Rozwiązania
techniczne poniżej są propozycją autora, a nie już udzieloną zgodą operatora.

## 2. Zakres i niezmienne ograniczenia

- Python3.12+, istniejące repo i procedury release; bez zmiany stosu aplikacji.
- Zachować źródła z dokładnych obiektów Git, porównanie per-service, pełną
  kontrolę inventory→metadane→kontenery/obrazy, liniowy graf migracji,
  kontrole Compose, anonimizację błędów i limity czasu.
- Brak dowodu, niezgodność, nieobsługiwany format lub zakres nadal daje blocked/exit2.
- Nie tworzyć inventory z odczytów. Nie adoptować stanu, zmieniać historycznych
  rewizji/metadanych ani filtrować diffu, by uzyskać zielony wynik.
- Wyjście pozostaje authorized=false, production_ready=false oraz
  content_provenance_verified=false i external_configuration_reviewed=false.
- Brak apply/migrate/repair, buildów, restartów, operacji finansowych i wywołań AI.
- Nie dodawać kodu do siedmiu domen aplikacji ani zależności backendu/frontendu
  wyłącznie na potrzeby checkera.

Model zagrożeń nadal zakłada zaufanego administratora/roota i lokalny daemon.
Nie obiecujemy ochrony przed złośliwym rootem wymieniającym kernel, narzędzia
i jednocześnie zatwierdzone dowody. Chronimy przed odziedziczonym środowiskiem,
niezatwierdzonymi wejściami, pomyłkami i zmianami podczas zwykłej pracy operatora.
V1 jawnie nie gwarantował atomowości całego środowiska; nowe wiązanie plików
nie jest dowodem, że taka zmiana wystąpiła na produkcji.

## 3. Zaufany checker i narzędzia

Checker używany do rzeczywistego odczytu musi być osobnym, przypiętym pakietem
narzędziowym, z zatwierdzonym SHA256 całego zestawu wykonywanego kodu i runtime.
Nie uruchamiać niezatwierdzonego checkera z dirty worktree ani automatycznie
uznawać kodu kandydata za zaufany, ponieważ sam siebie sklasyfikował.

Operator osobno akceptuje pakiet checkera i manifest toolchain:

- pełne, bezwzględne ścieżki i SHA256 wykonywalnych Git, Docker i Compose;
- rzeczywiste pliki po rozwiązaniu systemowych symlinków, regularne, root-owned,
  bez zapisu dla grupy/innych; analogiczne kontrole katalogów;
- dokładny runtime Pythona oraz wszystkie importowane moduły spoza stdlib;
- dane potrzebne do bezpiecznego uruchomienia psql opisane w sekcji5.

Uruchomienia używają zatwierdzonych ścieżek, nie wyszukiwania w odziedziczonym PATH.
Środowisko jest jawnie zbudowane; nie dziedziczy konfiguracji Git, Dockera,
pluginów Compose ani lokalizacji z HOME użytkownika. Używany jest wyłącznie
zatwierdzony lokalny socket. Compose również musi pochodzić z przypiętego pliku:
nie wystarczy przypiąć docker i pozostawić niezaufane wyszukiwanie pluginu.

Sposób wywołania wspieranego binarium Compose wybiera wykonawca i utrwala
w planie; zgodność CLI/argv musi mieć testy, bez cichego fallbacku. Brak
obsługi zatwierdzonego sposobu oznacza blocked. Fake tools w testach są osobno
przypięte do syntetycznego manifestu; nie ma flagi produkcyjnej trust-PATH.

Zatwierdzenie nowego pakietu narzędziowego nie zmienia wersji działających
aplikacji, inventory ani aktywnych metadanych. Jego przygotowanie i publikacja
to osobna czynność operacyjna, wymagająca zgody, nie ukryty krok aplikacyjny.

### 3a. Kto zatwierdza i gdzie leży źródło zaufania

Propozycja autora po builder check, do akceptacji wraz z tym projektem:

- Zatwierdzającym pozostaje użytkownik, który wskazał siebie jako administratora.
  Osobny reviewer dostarcza dowód przeglądu; nie zastępuje zgody administratora.
- Zgoda administratora w uwierzytelnionej rozmowie wskazuje dokładne SHA256
  pakietu checkera, manifestu toolchain i dowodu review zakresu. Zatwierdzenie
  projektu lub „kontynuuj testy” nie jest akceptacją przyszłych, nieznanych hashy.
- Po takiej zgodzie można sporządzić prywatny receipt powtarzający tożsamości
  zaakceptowanych artefaktów i referencję do zgody. Nie tworzyć receiptu zgody
  na podstawie samego review, wyniku CI lub kodu kandydata.
- Proponowane miejsce pakietów to
  `/opt/finanse/webapp/tooling/preflight/<bundle-sha256>/`,
  a dowodów akceptacji `/opt/finanse/webapp/approvals/preflight/<approval-id>/`.
  Oba poza repo, w katalogach root-owned0700. Manifesty/receipty0600;
  zawartość pakietu nieedytowalna dla grupy/innych. To planowana lokalizacja,
  nie twierdzenie, że już istnieje lub jest zatwierdzona operacyjnie.
- Minimalny launcher również jest osobno przejrzany i przypięty jako część
  zatwierdzonego pakietu. Administrator uruchamia go z podanej, zatwierdzonej
  ścieżki i z osobno przekazanymi digestami. Nie jest pobierany z kandydata
  podczas uruchomienia i nie wybiera sam sobie nowej wersji.
- Launcher najpierw sprawdza receipty/manifesty względem tych zewnętrznych
  digestów, następnie runtime, kod checkera i binaria. Dopiero potem uruchamia
  checker. Kandydat Git jest wyłącznie badanym wejściem; nie dostarcza
  wykonywanego launchera, importów ani decyzji, czy sam jest zatwierdzony.

To operacyjne zatwierdzenie przez zaufanego administratora, nie nowa PKI
lub udawany podpis cyfrowy. Nie wprowadzać automatycznego podpisującego agenta
ani kluczy prywatnych. Hash jest identyfikatorem bajtów, nie samodzielnym
dowodem zgody. Koszt tej decyzji: dodatkowy odbiór dokładnych artefaktów tooling
przed pierwszym użyciem oraz ponowna akceptacja po zmianie któregokolwiek z nich.

## 4. Compose/env: używać sprawdzonych bajtów

Po walidacji digestów przechwycić zatwierdzone bajty wszystkich wejść konfiguracji.
Compose nie może później ponownie czytać oryginalnych, zmienialnych plików.
Używa wyłącznie prywatnej, utrwalonej kopii wejścia na czas kontroli.

Wspierany zestaw minimalny:

- pełna uporządkowana lista zatwierdzonych Compose oraz wskazany env-file;
- service.env_file może wskazywać ten sam zatwierdzony env-file;
- zachowana semantyka project directory, względnych ścieżek, interpolacji,
  nazw projektu i odwołań do obrazów;
- nieodczytywane przez Compose źródła bind mountów nie są kopiowane ani dotykane.

Odwołania wymagające odczytu innych plików, np. include/extends, dodatkowe env_file,
zewnętrzne configs/secrets lub niezidentyfikowane zależności, muszą zostać
wykryte i odrzucone przed konsumowaniem ich przez renderer. W tym slice nie
dodajemy automatycznego poszerzania listy ani zbierania kolejnych hashy do akceptacji.
Brak parsera gwarantującego tę kontrolę oznacza blocked, nie tekstowy grep
uznany za parser YAML.

Wykonawca dobiera algorytm przechwycenia, walidacji zależności i zachowania ścieżek
w planie. Jeśli wymaga to nowej biblioteki parsera, musi być jawnie zaproponowana,
przypięta i objęta osobnym runtime narzędziowym, bez instalacji ad hoc.
Nie wolno uprościć tego do ponownego sha256sum po renderze: taki zabieg sam
nie dowodzi, jakie bajty Compose konsumował.

Wynik bezpiecznego renderowania można utrwalić w prywatnym, kanonicznym JSON
na czas kontroli i używać go dla następnych komend zamiast oryginałów. Te same
obserwacje obrazu/usługi co V1 muszą nadal być wykonane. Sposób zapisu nie może
zmieniać project directory lub kolejności scalania.

Ewentualny zapis wymaga wyraźnie wskazanego prywatnego scratch directory:
0700, pliki0600, własność operatora/root, bez symlinków. Jest to świadome,
ograniczone odstępstwo od dawnej obietnicy V1 „zero zapisów plikowych”,
nie mutacja serwisów. Snapshot może zawierać sekrety, więc nie trafia do Git,
stdout/stderr ani logów; cleanup dotyczy wyłącznie własnych plików. Błąd zapisu
lub cleanup daje niepowodzenie. Nie deklarować secure erase.

Zmiana oryginałów podczas kontroli unieważnia raport: sprawdzić ich tożsamość
i hashe ponownie przed zwróceniem sukcesu. W połączeniu ze snapshotem chroni to
przed użyciem innych bajtów, ale nie oznacza atomowej obserwacji całej produkcji.
Raport nadal trzeba powtórzyć pod istniejącym deploylock przed mutacją.

## 5. PostgreSQL: jednoznaczny lokalny endpoint

Najpierw zachować kontrole projektu, serwisu, ID/running, database i role.
Następnie uruchomić dokładnie jeden literalny SELECT version_num FROM alembic_version
w zatwierdzonym kontenerze, z czystym środowiskiem procesu psql.

Propozycja autora po builder check: docker exec działa jako numeryczny UID:GID
istniejącego systemowego użytkownika postgres w zatwierdzonym obrazie, nie jako
root ani z automatycznym domyślnym użytkownikiem obrazu. UID:GID jest częścią
zatwierdzonego manifestu toolchain PG, związanym z dokładnym image ID.
Role i database bierze się z zaakceptowanego inventory; nie zakładać, że
nazwa roli bazy to postgres lub że odpowiada nazwie użytkownika systemowego.

Jedyny wspierany kanał uwierzytelnienia to już istniejące bezhasłowe połączenie
lokalnym socketem, zgodne z zatwierdzonym oczekiwaniem operatora: peer z istniejącą
mapą albo już skonfigurowane trust. Nie włączać trust, nie zmieniać pg_hba,
nie tworzyć roli/mapowania i nie poprawiać uprawnień socketu w tym zadaniu.
Jeżeli obecna konfiguracja tego nie umożliwia, wynik to blocked z informacją,
że wymagany jest osobny projekt dostępu; nie dodawać kanału z hasłem.

- Nie dziedziczyć PGHOST, PGPORT, PGSERVICE, PGSERVICEFILE, PGOPTIONS,
  PGPASSFILE ani innych ustawień libpq wpływających na połączenie.
- Używać czystego środowiska, jawnego HOME bez plików konfiguracji i
  PGPASSFILE=/dev/null, żeby wyłączyć także domyślny odczyt .pgpass.
  /dev/null nie jest nowym magazynem poświadczeń.
- Jawnie wskazać lokalny socket Unix, port, bazę i rolę, z wyłączonymi rc/password
  promptami. Nie dopuszczać adresu TCP, URL lub dowolnego SQL z wejścia.
- Bezwzględna ścieżka psql, ścieżka socketu i port muszą wynikać z osobno
  zatwierdzonych danych toolchain dla dokładnego ID kontenera i obrazu PG.
  Brak, zmiana lub brak zgodności to blocked; nie zgadywać ścieżek.
- Socket musi należeć do lokalnego PG w tym kontenerze: odrzucić konfigurację,
  w której jego katalog pochodzi z obcego bind mountu lub współdzielonego
  z inną usługą endpointu. Nie zmieniać mountów lub parametrów serwera.
- Wymusić read-only, statement_timeout10000, ograniczony connect timeout
  i timeout subprocess10s. Brak połączenia jest błędem, nie powodem do fallbacku.

Test ma dopuszczać zarówno odrzucenie niezgodnego wejścia, jak i bezpieczne
wyzerowanie odziedziczonych ustawień przy jawnie przypiętym endpointcie.
Sam test „PGHOST istnieje” nie wystarcza jako dowód kierowania zapytania.
Nie twierdzić, że metoda pg_hba lub prawdziwe uwierzytelnienie zostały sprawdzone
przez syntetyczne testy. Osobny readonly odbiór rzeczywistego endpointu następuje
dopiero po zatwierdzeniu narzędzi i oczekiwań; ten projekt nie odczytuje go teraz.

## 6. Osobno zatwierdzony zakres tooling

Domyślnie wszystkie nieznane ścieżki nadal blokują. Nie dodawać ogólnego
allowlist dla ops/** lub .opencode/** i nie usuwać ich z porównania Git.

Opcjonalny dowód review ma być osobnym prywatnym plikiem oraz osobno
zatwierdzonym SHA256, niezależnym od inventory i od wyniku checkera.
Jest ściśle związany z:

- pełnym SHA kandydata i mapą trzech rzeczywistych baseline SHA usług;
- identyfikatorem/SHA256 zatwierdzonego pakietu checkera;
- dokładną listą zmian operacyjnego checkera/komendy, bez globów;
- ścieżką, starym i nowym typem/mode i Git blob ID każdej zmiany
  (jawne null przy dodaniu/usunięciu), oraz SHA256 niepustej nowej treści;
- hashem raportu review i deklarowanym wynikiem odbioru bez nierozwiązanych
  Critical/Important. Samego braku usterek w JSON nie traktować jako review.

Dowód nie może zawierać powłoki, komend do wykonania, uprawnień do mutacji ani
klasyfikacji, którą checker przyjmuje bez weryfikacji. Wszystkie wymienione
tożsamości i kompletny zakres są porównywane z rzeczywistymi obiektami Git.
Extra/missing entries, podmieniony kandydat lub dowolny niezatwierdzony path blokuje.

W tym slice kwalifikują się wyłącznie pliki zatwierdzonego pakietu
release_preflight i `.opencode/command/deploy.md`. Inne operatory, CI/workflows,
Compose lub .dockerignore nie dostają nowego zwolnienia. Rozszerzenie tej
granicy wymaga osobnej zmiany projektu i testów.

Raport pokazuje osobno uznany zakres tooling i digest dowodu; nie przepisuje
tych ścieżek na docs/none. Nie zmienia to oceny runtime/migracji dla aplikacji.
Przy samych zatwierdzonych zmianach tooling no_rollout oznacza tylko brak
nowych bajtów aplikacji, nigdy automatyczną instalację narzędzi.
Brak prawidłowego dowodu zachowuje unknown_change_scope/exit2.

Pierwsze uruchomienie nowego checkera wymaga wcześniejszego niezależnego
przeglądu, pozytywnych testów i akceptacji dokładnego pakietu przez operatora.
V1 nie musi „zatwierdzić swojego następcy”; nie jest do tego uprawniony.
Obecny blocked pozostaje w historii, a nowy zaakceptowany checker wytwarza
osobny raport według jawnie zmienionej procedury. Nie wolno nazywać tego
ponownym sukcesem V1 ani zastąpić go ręcznie zmodyfikowanym raportem.

## 7. Odbiór i granice dalszych prac

W planie ująć RED→GREEN trzech braków review i regresje:

- podmieniony PATH, fałszywy plugin Compose, zły digest i tryb binarium;
- zmiana pliku po hashu, podmiana ścieżki, obce referencje i zachowanie ścieżek;
- obce ustawienia libpq, zły endpoint/container/image i odmowa dowolnego SQL;
- niepełne/fałszywe/stare review scope, zmiana kandydata lub baseline;
- nadal blocked dla każdego niezatwierdzonego ops/workflow i zmian migracji;
- sekrety w stdout/stderr/wyjątkach/snapshotach, cleanup, timeouty, Python -O;
- per-service revisions, już zmigrowany schema i brak ponownego backfillu;
- minimalny zewnętrzny launcher uruchamia wyłącznie zatwierdzony checker/toolchain.

Testy syntetyczne bez prawdziwego Docker/DB/AI, potem kanoniczne kontrole,
pełne CI dokładnego SHA i jeden świeży review całego slice. Same dotychczasowe
91PASS nie wystarczają. Nie ma automatycznego odstąpienia od nierozwiązanych uwag.

Dopiero po odbiorze i osobnej zgodzie: przygotowanie/akceptacja pakietu tooling,
readonly odbiór na rzeczywistym środowisku oraz odrębne dalsze bramki release.
Backup/restore, retencja, rollback, obrazy nonroot, dokładna migracja i runtime
nadal obowiązują. Projekt nie zmienia zgody na funkcję ani nie gwarantuje,
że obecna produkcyjna konfiguracja zmieści się we wspieranym podzbiorze.

## 8. Decyzje pozostawione wykonawcy planu

Podział modułów/testów, dokładny ścisły JSON schema dowodów, nazwy reason codes,
metoda przypinania runtime/binarnych plików i snapshotu, parser/ewentualny osobny
lock zależności narzędziowych, protokół launchera i pełne scenariusze testowe.
Każdy wybór ma spełniać powyższe invariants i być opisany w planie przed kodowaniem.
Nie są pozostawione do decyzji: pomijanie blokady, automatyczny issuer inventory,
uruchamianie niezatwierdzonego kodu kandydata lub mutacja produkcji w ramach testu.
