# Automatyczny odczyt zdjęć dokumentów przez model wizyjny

Status: implementacja i review ukończone; po osobnej zgodzie wdrożone na produkcję
2026-11-02 w84c9c27 z OpenAI/Terra i aktywną polityką. Raport lokalnej akceptacji:
`docs/audits/2026-10-31-document-vision-verification.md`; odbiór produkcji:
`docs/audits/2026-11-02-openai-production-release.md`. Preview bez zmian.

Checklist projektu:
- [x] Uwzględnić diagnozę dwóch zdjęć oraz obecne modele/API/formularz.
- [x] Ustalić z użytkownikiem tryb automatyczny nowych uploadów.
- [x] Opisać zakres, prywatność, walidację, odzyskiwanie, limity i granice aktywacji.
- [x] Niezależny builder check i rozstrzygnięcie pytań o równoległe OCR/fallback.
- [x] Zatwierdzenie pełnego projektu przez użytkownika.
- [x] Szczegółowy plan implementacji po zatwierdzeniu:
  `docs/superpowers/plans/2026-10-31-automatic-document-vision.md`.

## 1. Cel i decyzje użytkownika

Po dodaniu zdjęcia paragonu albo faktury aplikacja ma automatycznie odczytać obraz
i zaproponować pola do ręcznego zatwierdzenia. Lokalny OCR nie może być koniecznym
ani jedynym wejściem modelu dla zdjęć. Nie budujemy autonomicznego agenta finansowego.

Użytkownik zatwierdził przygotowanie planu i wybrał **automatyczne** wysyłanie nowych
zdjęć do zewnętrznego AI, bez dodatkowego przycisku zgody dla każdego uploadu.
Dotychczasowa jednorazowa analiza dwóch zdjęć nie jest sama w sobie aktywacją tej
funkcji w działającym podglądzie. Zatwierdzenie odczytanych danych i rozliczenie
płatności nadal są osobnymi działaniami człowieka.

## 2. Dlaczego zmiana jest potrzebna

Diagnoza dwóch rzeczywistych uploadów telefonu ujawniła zniekształcony tekst OCR
mimo documents.status=done. Normalizacja EXIF poprawiła tekst i odzyskała sumy,
ale nadal występowały błędy cyfr, dat i pozycji. Bezpośredni odczyt obrazów przez
asystenta był lepszy dla tych dwóch przykładów; nie jest to benchmark API ani
gwarancja jakości przyszłego modelu. Preview ma celowo wyłączony LLM. Obecny
extractor wysyła do LLM tylko tekst, więc samo dodanie klucza nie daje mu obrazu.

## 3. Zakres pierwszej iteracji

- Nowe obrazy JPEG, PNG i HEIC/HEIF, zarówno z aparatu, jak i galerii/pliku.
- Odczyt rodzaju dokumentu, sprzedawcy, numeru, dat, opisu, kwoty i waluty oraz
  NIP/rachunku, tylko gdy są czytelne. Bazą jest istniejący ReviewSuggestion.
- Automatyczna propozycja po uploadzie; istniejący formularz review i usługi bills
  pozostają jedyną ścieżką zatwierdzania dokumentu.
- Poprawne przygotowanie orientacji JPEG/PNG/HEIF dla AI i dla lokalnego OCR obrazów.
- Osobne znaczenie zakończenia technicznego przetwarzania i gotowości danych review.
- Ograniczone koszty/retry, obsługa braku klucza, awarii, odmowy i nieczytelnego obrazu.

Poza zakresem: automatyczne płatności/postings, agentowe narzędzia/SQL, integracje
bankowe, import historii, masowe ponowienie starych dokumentów, pozycje paragonu
jako nowy rejestr kosztów, wielostronicowy vision-PDF i przebudowa UI finansów.

PDF pozostaje na dotychczasowej ścieżce PDF/OCR/tekstowego review. Nie zmieniamy
teraz jej zachowania ani nie wysyłamy automatycznie obrazów wszystkich stron PDF.
Nie uruchamiamy obowiązkowo drugiego odczytu OCR dla poprawnie obsłużonego vision.

Rozstrzygnięcie autora po builder check: **aktywne vision zastępuje automatyczny
OCR dla nowych obrazów**. Nie ma równoległego uruchomienia obu metod. Przy braku
klucza/limicie/odmowie/awarii vision pozostaje jawny stan do ręcznej obsługi;
nie ma automatycznego fallbacku do OCR ani innego dostawcy. Lokalny OCR jest osobną,
jawną alternatywą. Gdy funkcja vision nigdy nie była aktywowana, nowe uploady
zachowują dotychczasową ścieżkę legacy; nie są milcząco przenoszone na vision po
późniejszym włączeniu flagi. Oczekujące wcześniej wybrane vision po wyłączeniu
flagi zachowują zasady wstrzymania opisane w sekcji6.

## 4. Przepływ i prywatność

1. Obecne auth, CSRF, limity i walidacja typu/rozmiaru/pikseli przyjmują upload.
   Oryginał prywatny, jego SHA i deduplikacja pozostają niezmienione.
2. Dla nowego obrazu przy aktywnej polityce vision zapisujemy zamiar odczytu
   w PostgreSQL w transakcji uploadu. Po commicie kolejkujemy zadanie; Redis nie
   jest jedyną pamięcią tego zamiaru. Utrata kolejki jest odzyskiwalna.
3. Worker w ograniczonym procesie przygotowuje pochodną: EXIF transpose, RGB,
   zachowane proporcje, kontrolowany rozmiar i brak EXIF/GPS/innych metadanych.
   Ta pochodna nie nadpisuje oryginału. Limity nie mogą być tylko frontendowe.
4. Do skonfigurowanego dostawcy trafia pochodna JPEG oraz stała instrukcja ekstrakcji.
   Nie wysyłamy oryginalnej nazwy, GPS, danych konta użytkownika, jego księgi ani
   innych dokumentów. Dane widoczne na samym zdjęciu są jednak wysyłane — usunięcie
   EXIF nie anonimizuje faktury. Nie obiecujemy retencji dostawcy bez weryfikacji.
5. Wynik jest niezaufaną propozycją: walidacja schematu, formatów i kwot w backendzie,
   zapis nowej rewizji review i audyt metadanych wykonania, bez danych finansowych.
6. Użytkownik porównuje propozycję z obrazem, poprawia pola i zatwierdza przez
   istniejącą usługę bills. Nawet zatwierdzenie faktury nie tworzy płatności.

Treść obrazu to dane, nigdy instrukcje. Wywołanie nie ma tools/function calling,
SQL, dostępu do URL-i wskazanych w obrazie ani możliwości wykonywania działań.
Nie przenosimy dokumentów przez publiczne URL-e lub narzędzia wyszukiwania.
Logi i repo nie zawierają obrazu/base64, promptu z dokumentem, surowej odpowiedzi,
sekretów ani pełnych prywatnych pól. Dane do audytu przechowujemy wyłącznie
w kontrolowanych modelach aplikacji z dotychczasowym owner scoping.

## 5. Konfiguracja — propozycje autora, nie dotychczasowe decyzje użytkownika

- Osobna konfiguracja vision, niezależna od modelu Doradcy i tekstowego extractora.
  Nie zakładamy, że obecny LLM_MODEL potrafi przyjmować obrazy.
- Adapter multimodalnego API ze schematem odpowiedzi; konkretne provider/model/
  base URL/klucz są jawnie konfigurowane przed aktywacją, bez nazw modeli w kodzie.
  Pierwszy adapter może korzystać z istniejącego SDK OpenAI-compatible, pod warunkiem
  testu wsparcia obrazu i struktury przez wybrany endpoint. Brak zgodności blokuje
  aktywację, nie uruchamia cichego fallbacku do innego dostawcy.
- Flaga automatycznego vision jest domyślnie wyłączona dla aktualizacji starego
  środowiska. Włączenie odbywa się osobno po akceptacji konfiguracji/operatora.
  Po włączeniu nowe zdjęcia są przetwarzane automatycznie zgodnie z wyborem użytkownika.
- Konfigurowane limity: długość krawędzi/pochodnej, tokeny wyjścia, timeout,
  współbieżność, liczba prób/opóźnienia i dzienny limit wywołań na użytkownika.
  Nie wymagamy uniwersalnej kwoty PLN za wywołanie bez modelu i cennika.
  Rezerwacja limitu musi być atomowa i trwała; niedostępność licznika blokuje
  wywołanie. Nowa rewizja/retry zużywa limit, duplikat tego samego zamiaru nie.
- HTTP redirecty wyłączone; endpoint wyłącznie HTTPS z konfiguracji operatora,
  nie z uploadu/requestu/modelu. Tokeny nigdy nie trafiają do frontendu.
- Przed aparatem/uploadem stała informacja o automatycznym wysyłaniu obrazów do
  skonfigurowanego AI. To informacja o aktywnej polityce, nie ponowna zgoda per plik.

Dokładny dostawca, model, retencja i wartości limitów są warunkiem uruchomienia,
nie powodem kopiowania sekretów produkcji lub blokowania testów z atrapą dostawcy.
Dobór konfiguracji wymaga potwierdzenia przed realnym ruchem; niniejszy projekt
nie upoważnia do użycia dowolnej istniejącej subskrypcji/klucza.

## 6. Trwałość, idempotencja i kompatybilność

Nie reinterpretujemy starych dokumentów po zmianie flagi. Sposób przetwarzania
nowego uploadu utrwalamy w DB; istniejące dane pozostają na legacy OCR. Zmiana
polityki lub otwarcie listy nie może samo wysłać starych obrazów na zewnątrz.
Duplikat uploadu nie tworzy kolejnej odpłatnej analizy.

Projekt przewiduje addytywną migrację domeny documents: zapis metody wejściowej
nowych dokumentów/rewizji (obraz vs tekst), z bezpiecznym legacy default dla starych
rekordów, oraz metadane próby i odzyskiwania nowej ścieżki. Konkretny rozkład
kolumn i indeksów pozostawiamy autorowi planu; metoda nie może być wyłącznie
dynamiczną decyzją z bieżącej flagi lub niezweryfikowanym polem odpowiedzi modelu.

Odczyt vision nie zależy od istnienia DocumentText. Nie zapisujemy odpowiedzi modelu
jako tekstu rzekomo pochodzącego z lokalnego OCR. Istniejące teksty/review są zachowane.
Każda nowa rewizja ma kontrolowane metadane wejścia, SHA źródła/pochodnej, provider/
model z konfiguracji oraz wersję schematu/instrukcji; provenance pól ustala backend.

Claim zadania, wywołanie i publikacja wyniku są rozdzielone: krótki claim w DB,
sieć bez długiej transakcji/blokady, potem zapis przez token próby/lease i CAS.
Przerwane processing jest odzyskiwalne po konfigurowanym czasie. Spóźniony wynik
nie nadpisuje nowszej rewizji lub danych zatwierdzonych przez człowieka. Równoległy
dispatcher i kliknięcia nie uruchamiają świadomie tego samego aktywnego zadania.

Retry tylko dla awarii przejściowych, z limitem i backoff. Nieczytelność, odmowa,
niezgodny schemat, brak konfiguracji i zły klucz nie uruchamiają nieskończonej pętli.
Retry SDK i workera nie mnożą się niejawnie. Po utracie procesu w niepewnym momencie
może wystąpić ponowny koszt dostawcy; nie obiecujemy exactly-once billing, którego
API nie zapewnia. Limit prób i rezerwacje ograniczają ten przypadek.

Zatrzymanie flagi blokuje nowe wywołania również dla oczekujących zadań. Zadania te
uzyskują jawny stan niedostępności/wstrzymania; ponowna aktywacja nie wysyła ich
automatycznie bez jawnego wznowienia. Działającego HTTP nie da się wiarygodnie cofnąć.

## 7. Walidacja i odpowiedzialność człowieka

Schemat odczytu rozszerzamy tylko o metodę i jawne ostrzeżenia, bez pełnej ewidencji
pozycji. Brakujące lub nieczytelne pola=null, nie dzisiejsza data/PLN/zgadnięta cyfra.
Typ dokumentu multiple/statement/loan_schedule/unsupported nie staje się pojedynczym
rachunkiem kosztowym. Spójność schematu nie dowodzi prawdziwości tekstu na obrazie.

Kwoty parsowane przez Decimal i zamieniane na grosze w kodzie, bez float; waluty,
daty, długości i zakresy ograniczone. Nie twierdzimy, że suma pozycji jest sprawdzona,
jeśli ta iteracja nie pobiera kompletu pozycji. Dane o podatku/rabacie/zapłacie nie
są automatycznie interpretowane jako suma do zapłaty. Brak IBAN-u/terminu nie musi
oznaczać błędu paragonu. Brak sprzedawcy/kwoty/waluty wymaga uzupełnienia, a nie
statusu „odczyt gotowy” tylko dlatego, że JSON jest syntaktycznie poprawny.

Wynik modelu nie jest źródłem prawdy i nigdy sam nie zatwierdza dokumentu. Obsługa
duplikatów, declared_paid vs reconciled, częściowych płatności, coverage i istniejących
postings pozostaje bez zmian. Wydruk „gotówka/karta” nie jest uzgodnieniem księgi.

## 8. Stany i obecny formularz — bez nowego projektu ekranów

API udostępnia lekki, owner-scoped status ostatniej rewizji w list/detail, aby nie
wykonywać po jednym GET na każdy wiersz. Statusy techniczne Document zachowujemy
dla kompatybilności; użytkownik widzi rozróżnienie:

- oczekiwanie/przetwarzanie odczytu,
- propozycja do sprawdzenia, nie „dane poprawne”,
- konieczne ręczne uzupełnienie/nieczytelne pola,
- AI niedostępne/limit/błąd, z bezpiecznym kodem bez sekretów.

Ogólne „Gotowe” nie wystarcza. Dla vision brak tekstu OCR nie oznacza awarii.
Oryginał, istniejący podgląd i ręczny formularz pozostają dostępne przy awarii AI.
Komunikaty/przyciski retry rozróżniają ponowny odczyt AI i lokalne OCR. Lokalne OCR
można uruchomić jawnie jako alternatywę, bez drugiego automatycznego kosztu AI.
W takim przypadku dla dokumentu vision powstaje wyłącznie tekst lokalnego OCR;
nie jest automatycznie wywoływany dotychczasowy tekstowy extractor LLM ani nowe
vision. Metoda dokumentu/istniejąca rewizja nie są przepisywane. Przełączenie na
kolejną propozycję AI wymaga osobnej jawnej akcji i własnej rewizji.

Wynik przychodzący podczas edycji nie może wyczyścić konta/kategorii ani nadpisać
zmienionych ręcznie pól. Automatyczne uzupełnienie tylko nietkniętych pól danej
rewizji; zastosowanie nowych sugestii do zmienionych pól jest jawną decyzją.
Nie zmieniamy layoutu/nawigacji — wyłącznie potrzebne stany i komunikaty w obecnych
komponentach. Makieta nowego ekranu nie jest częścią zakresu.

## 9. Stare zdjęcia i dwa przypadki diagnostyczne

Brak backfillu. Istniejące dokumenty pozostają bez zmian. Nowy odczyt vision
istniejącego obrazu wymaga jawnej akcji z autoryzacją/CSRF, rate limit i kluczem
idempotencji; tworzy nową rewizję, zachowuje stary tekst i zatwierdzone dane.
Wcześniejsza zgoda na jednorazowe porównanie dwóch zdjęć nie oznacza zgody na
ponawianie dowolną liczbę razy podczas implementacji lub CI. Do testów używamy
syntetycznych fixtures bez osobistych danych. Jeden kontrolowany test tych zdjęć
w API po uruchomieniu wymaga osobnego potwierdzenia i skonfigurowanego dostawcy.

## 10. Testy i warunki odbioru

- TDD normalizacji EXIF1/3/6/8, JPEG/PNG/HEIF, braku GPS i integralności oryginałów;
  nadal ograniczone procesy/parsery i quota guards.
- Nowy obraz => trwały zamiar vision, job => obraz wysłany do atrapy dostawcy,
  schema-valid propozycja dostępna bez DocumentText i bez obowiązkowego OCR.
- Duplikat, utrata Redis, restart worker, recovery processing, konkurencja, timeout,
  spóźniony wynik, wstrzymanie polityki i brak konfiguracji: brak utraty zamiaru,
  niekontrolowanych kosztów, nadpisania nowszych danych i sekretów w logach.
- Idempotencja oraz dzienne limity atomowe także przy równoległych uploadach/retry.
- Odmowa, unreadable, niepoprawny JSON/daty/kwoty, prompt injection w obrazie,
  nietypowy rodzaj dokumentu => kontrolowany stan i ręczna ścieżka, zero działań AI.
- API owner scoping także dla starego obrazu/retry/oryginału/statusu; GET nic nie wysyła.
- Regresja PDF i legacy review, manual approve, receipt declaration, duplikaty,
  alokacje i prognoza; upload/vision/retry/approval nie zmienia ledger ani sald.
- Frontend: rzeczywiste API contract fixtures, wszystkie stany, brak utraty edycji,
  odświeżenie po uploadzie, dwa motywy i mobilny viewport/keyboard/a11y.
- Zestaw syntetycznych paragonów z ground truth i trudnymi orientacjami. Wynik live
  sprawdzamy dla konkretnego wybranego modelu; test z atrapą nie potwierdza jego jakości.
- Rzeczywisty Android/iPhone: aparat/galeria/HEIC, obrót i powolna sieć nadal wymagają
  testu urządzenia; nie zastępują ich dwa uploady ani test viewportu.
- Przed commitem pełny wymagany lint/typecheck/test gate; przed wydaniem oddzielny
  review, backup/restore i test addytywnej migracji, bez produkcyjnych danych w CI.

## 11. Aktywacja podglądu i granice zgody

Implementacja i migracja testowa nie oznaczają uruchomienia nowego modelu w preview.
Obecny stack jest bez egressu i kluczy; nie podłączamy go po prostu do sieci produkcji.
Po osobnym zatwierdzeniu aktywacji potrzebuje własnego klucza o ograniczonym zakresie,
wybranego modelu/retencji/limitów oraz wyjścia tylko do zatwierdzonego endpointu
(np. kontrolowany proxy egress), bez dostępu do baz/usług/sekretów produkcji.
Konkretny mechanizm egress i porty wymagają osobnego przeglądu infra przed zmianą.

Rollout: kod i testy z atrapą -> izolowany test migracji -> review -> osobna zgoda
na nowy preview z AI -> test API wybranego modelu na syntetykach -> test użytkownika
na telefonie. Dwa istniejące zdjęcia dopiero po jawnej akcji i potwierdzeniu powtórki.
Rollback wyłącza nowe wysyłki i zachowuje wszystkie oryginały/review/ledger. Nie
wykonuje masowego kasowania ani downgrade schematu.

Ten projekt nie obejmuje merge PR5, push main, wdrożenia produkcji ani importu danych.
Po zatwierdzeniu całego projektu powstaje szczegółowy plan implementacji.
