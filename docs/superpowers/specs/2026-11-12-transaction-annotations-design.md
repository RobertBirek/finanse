# Opis, notatka, tagi i projekt transakcji

## Zatwierdzone przez użytkownika

Po ręcznej korekcie kategorii użytkownik wybrał własny opis, notatkę, tagi oraz
opcjonalny wybór istniejącego projektu. Potwierdził tworzenie tagów podczas edycji
i ich późniejsze ponowne używanie. Bez zmiany kwot, kont, dat i powiązań importu;
zmiany audytowane. Nie jest to zgoda na wdrożenie.

## Zachowanie

- Jedna ręczna komenda „Opis i oznaczenia” dostępna z listy transakcji, w rejestrze
  i na koncie. Opcjonalny opis zastępuje tylko wyświetlaną nazwę; oryginalny opis
  pozostaje widoczny osobno w edytorze i nie jest kopiowany ani nadpisywany.
- Opcjonalna notatka wielowierszowa, kilka tagów, jeden istniejący własny projekt
  lub brak projektu. Puste opis/notatka oznaczają usunięcie nakładki. Brak własnego
  opisu przywraca oryginalny opis, nie ostatnią nazwę reguły.
- Tagi tworzone w edytorze są zapisywane dopiero z całą poprawną transakcją;
  anulowanie nie zostawia tagów. Podpowiedzi obejmują wyłącznie własne tagi.
  Normalizacja: UnicodeNFC, strip, złożenie whitespace; unikalność po casefold.
  Pierwsza zapisana nazwa jest etykietą. Powtórzenie tagu nie mnoży powiązań.
- Bez zarządzania słownikiem/rename/delete tagów, globalnej edycji projektów,
  załączników, kontrahenta, edycji masowej lub automatycznego tagowania.
- Odczyt i zapis obejmują wszystkie własne typy/źródła, również FX, zwroty,
  transfery, płatności pożyczek i dokumentów: to wyłącznie opisowe oznaczenia,
  nigdy pozwolenie na ich kategoryzację lub zmianę księgi.
- Jawne Zapisz/Anuluj. Błąd lub409 zachowuje wpisany formularz; brak automatycznego
  retry na świeżej wersji. Zapis nie wymaga dodatkowego podglądu księgowego.

## Decyzje techniczne autora, nie dodatkowe żądania użytkownika

- PostgreSQL: osobna wersjonowana TransactionAnnotation (tytuł/notatka), FinanceTag
  i TransactionTag. Owner-scoped ograniczenia i FK. Bez JSON jako magazynu danych.
  Jedyna informacja o projekcie zostaje w istniejącym FinancialTransaction.project_id.
- Migracja addytywna bez backfill opisów. FK project_id→projects.id ON DELETE SET NULL,
  po preflight istniejących referencji. Obce/osierocone istniejące referencje mają
  zatrzymać migrację czytelnym błędem, nie być automatycznie wyczyszczone.
- Zapis tylko przez dedykowany endpoint annotations, bez rozszerzania ogólnego
  TransactionUpdate lub poluzowania document/import/loan guards. Postings,
  date_metadata, opisy źródłowe, mappings, evidence, receipts i manifesty nietknięte.
- Istniejący edytor dat pozostaje oddzielny. Przyciski zmiany oryginalnego opisu
  w UI zastępuje nowa nakładka, aby nie oferować dwóch sprzecznych edytorów nazwy.
  LegacyAPI ręcznych wpisów nie jest usuwane; chronione importowane oryginalne
  opisy nie mogą być nadpisane także przez ten ogólny PATCH.
- Wersja annotations, snapshot kontekstu (w tym project_id i updated_at transakcji),
  Idempotency-Key/FinanceCommandReceipt, rowlock transakcji i audyt old/new w jednej
  transakcji. Równoległy zapis nie gubi edycji. Replay nie nadpisuje nowszych zmian.
- Reguły/AI/import dalej operują na źródłowym opisie i nie zmieniają nakładki.
  Zmiana oznaczeń nie generuje zdarzeń reguł/AI. Bez zmiany raportów i sald.
- Listy/detail dostają opcjonalne annotations i effective_description; brak danych
  ma bezpieczny fallback. Odczyt batch/selectin bez N+1. Wyszukiwanie q obejmuje
  także własny opis/notatkę/tag/projekt, poprzez EXISTS bez dublowania wyników;
  oryginalny opis nadal wyszukiwalny. Nie dodajemy osobnych filtrów/raportów tagów.
- Limity konfigurowalne w backendzie, przekazywane klientowi: domyślnie opis200,
  notatka5000, nazwa tagu60 znaków,20tagów/transakcję. Wartości są propozycją autora.
  Treści są zwykłym tekstem, nie HTML/Markdown; brak sekretów w logach/błędach.
- Istniejące projekty wszystkich statusów można wybrać także dla historycznego
  kosztu. Usunięcie projektu usuwa tylko link, nie oznaczenia lub transakcję.

## Odbiór

Backend: migracja na własnym no-portPG, rzeczywisty zapis/odczyt i wyszukiwanie;
exactcolumns wszystkich postings, źródła i referencji; audit/receipt/replay/races;
obce IDs/normalizacja/limity/injection; projectdelete; brak automatyzacji.
Frontend: formularz, tworzenie/podpowiedzi/usuwanie tagów, reset opisu, projekty,
anulowanie i409; raport/lista odświeżone bez zmian kwot. E2E375/1440 na syntetycznym
imporcie i protectedloan, bez realAPI. Pełnepytest/vitest/lint/types/build oraz jedno
końcowe niezależne review. Lokalne commity, bez merge/push/deploy.

## Kolejność

Najpierw domknąć i osobno zatwierdzić lokalny commit poprzedniej korekty kategorii.
Ta dokumentacja nie uprawnia do modyfikacji zamrożonych źródeł tamtego pełnego suite.
Plan annotations wymaga zatwierdzenia przed implementacją; granice i szczegóły
techniczne powyżej mają zostać pokazane użytkownikowi w skrócie.
