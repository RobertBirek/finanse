# Dokumenty → automatyczne szkice w finansach

Uzgodnione w rozmowie: dwa niezależne znaczniki w /documents, automatyczny
odczyt nowych plików i szkic w /finances/documents, sugestia jednej istniejącej
kategorii z możliwością ręcznej zmiany. Użytkownik zatwierdza dane sam.

## Granice

- Nie tworzyć transakcji, postings, deklaracji zapłaty ani zadań Inbox/Today.
- Nie zmieniać zaakceptowanych dokumentów finansowych i ręcznych wyborów.
- Nie uruchamiać ponownego OCR/AI lub masowego importu istniejących plików.
- LLM tylko sugeruje. Nie zna UUID kategorii, nie tworzy kategorii, nie oblicza sald.
- Dokumenty inne niż pojedyncza faktura/paragon nie trafiają automatycznie do rejestru.
- Stare dokumenty dostają znaczniki wyliczone z rzeczywistych powiązań w PostgreSQL.
- Zgoda obejmuje lokalną implementację/testy; bez push, deploy, migracji produkcji,
  zmiany polityk AI lub wysyłania rzeczywistych dokumentów do dostawcy.

## Architektura i decyzje wykonawcze

1. Wykorzystać obecne OCR/Vision i serwis prepare_bill. Nie tworzyć drugiego
   pipeline ekstrakcji ani nowej domeny.
2. Nowy owner-scoped trwały intent `DocumentFinanceDraftIntent`, jeden na dokument,
   tworzony atomowo z nowym uploadem. Duplikat uploadu nie tworzy nowego intentu.
   Redis dostarcza ID; dispatcher odzyskuje pracę z PostgreSQL.
3. Rejestracja szkicu to krótka transakcja DB, bez HTTP. Blokada dokument→intent,
   prepare_bill i audit/receipt chronią przed powtórzeniem. Brak trwałego stanu
   processing: awaria transakcji pozostawia intent pending. Błąd domenowy ma
   bezpieczny kod i wymaga świadomego ponowienia; nie powtarzać OCR dla błędu zapisu.
4. Przypiąć intent do użytej rewizji; obsłużyć niekompletny/nieobsługiwany odczyt,
   archiwum, podmianę właściciela i istniejące powiązanie. Nigdy nie nadpisywać
   istniejącego draft/approved/rejected bill. Szkic zachowuje declaration=unknown
   oraz kwotę/walutę NULL; rozpoznane wartości są propozycjami z przypiętej rewizji,
   widocznymi w formularzu, a nie zatwierdzonymi kwotami księgowymi.
5. Sugestię kategorii dodać do tego samego wywołania rozpoznania, gdy istnieje nowy
   intent i poprawny ograniczony katalog właściciela. Bez drugiego API call.
   Kategorie: aktywne expense, poprawna ścieżka rodziców, bez kategorii technicznych.
   Model widzi klucze c01… i nazwy/ścieżki; backend sprawdza klucz i ponownie
   właściciela/aktywność przed publikacją. Brak/nieznany klucz oznacza brak sugestii.
6. Nie zmieniać kwotowej/daty walidacji OCR. Obecny kontrakt Vision bez katalogu
   pozostaje obsługiwany. Rozszerzony kontrakt z katalogiem ma osobny strict payload.
   Fingerprint polityki Vision uwzględnia nowy zakres danych: realna aktywacja
   po wdrożeniu wymaga osobnej decyzji operatora, nie cichego obejścia polityki.
7. Źródłem sugestii jest nullable FK rewizji do kategorii. To nie jest category_id
   zatwierdzonej faktury. Brak lub wyłączona kategoria nie blokuje szkicu.
   Pola form dirty (także ręczne wyczyszczenie kategorii) mają pierwszeństwo
   przed pollingiem, retry i zastosowaniem kolejnych sugestii.

## API i UI

- DocumentResponse.finance: summary zawierające powiązany bill_id/review/lifecycle
  oraz stan intentu. Jedno owner-scoped batch zapytanie dla strony, bez N+1
  i bez ładowania treści/wywołań AI z GET.
- Odczyt i Finanse to dwie osobne informacje; nowy błąd odczytu nie ukrywa
  uprzednio zatwierdzonego powiązania. Samo ready nie oznacza poprawności danych.
- Lista: „Nie wczytano”, „Przygotowywanie szkicu”, „Do sprawdzenia”,
  „Szkic w finansach”, „Zatwierdzony w finansach”, „Archiwalny/Anulowany”.
  Link do konkretnego bill; szkic ma akcję otwierającą przegląd źródła.
- Rejestr finansowy wyraźnie pokazuje draft/approved/rejected. Nowy szkic nie
  powinien wyglądać jak zatwierdzona faktura bez kwoty.
- Umożliwić jawne przygotowanie szkicu dla jednego starszego dokumentu bez
  ponownego odczytu; GET nie robi zapisu. Nie wykonywać tej akcji na danych użytkownika.
- Polling aktywnego intentu aktualizuje listę i powiązania; frontend ignoruje
  spóźnione odpowiedzi po zmianie konta. Używać istniejącego actor/generation guard.

## Weryfikacja

TDD czystych kontraktów, zapytań, walidacji payloadów, retry/replay oraz UI.
Testy integracyjne jako część istniejącego CI na jego nowych bazach; lokalnie
bez fixture DB, issuera permitów, Docker/PG lub sieci dostawcy. Addytywną migrację
sprawdzić statycznie/offline, nie udawać realnego upgrade/retencji.
Kanoniczne /lint /typecheck /test (backend: kolekcja) i dodatkowe konkretne
offline unit; pełny Vitest. Jeden świeży review całości.
