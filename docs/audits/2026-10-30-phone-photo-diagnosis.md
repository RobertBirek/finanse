# Diagnoza dwóch zdjęć telefonu — 2026-10-30

## Zakres i zgoda

Użytkownik zgłosił problem po dodaniu dwóch zdjęć do izolowanego podglądu, następnie
jawnie zezwolił na porównanie z zewnętrznym modelem wizyjnym. Odczyt obrazu wykonano
przez asystenta w tej rozmowie (przed odczytem zapisanego tekstu OCR), nie przez
produkcyjny backend ani nową integrację API. Nie jest to benchmark konkretnego
dostawcy ani wdrożenie nowej ścieżki przetwarzania.

## Potwierdzone obserwacje

- Oba nowe pliki JPEG dotarły; status documents=done po jednej próbie, bez błędów
  technicznych. To nie dowodzi czytelności OCR.
- W obu zdjęciach tekst paragonu jest bokiem. Odczyt wizualny pozwala wskazać sumy,
  datę i pozycje; sumy widocznych pozycji zgadzają się z sumami paragonów.
- Zapisy Stirling mają762 i569 znaków, lecz są mocno zniekształcone, nie stanowią
  wiarygodnego odczytu dokumentów. „Niepusty tekst” był zbyt słabym kryterium
  wcześniejszego testu syntetycznych, prawidłowo zorientowanych obrazów.
- Obie rewizje review mają incomplete/llm_unavailable oraz puste fields. Podgląd
  celowo nie ma kluczy i egressu LLM. To odrębna przyczyna pustego formularza.
- Aktualny extractor.py przekazuje do LLM wyłącznie tekst OCR. Samo włączenie
  klucza nie daje modelowi dostępu do obrazu i nie naprawia utraconego tekstu.
- „Gotowe” w UI reprezentuje zakończenie zadania OCR, nie jakość tekstu ani gotowość
  propozycji review. Przepływ wymaga wyraźniejszego rozdzielenia tych stanów.

## Dowody i ograniczenia

Prywatne obserwacje obrazu i szczegóły dokumentów są wyłącznie w
`/docker/finanse-preview/evidence/phone-vision-observation.json`, poza repo.
Pomocniczy probe lokalnego OCR zmienia wyłącznie robocze bajty w pamięci;
nie uruchamia retry, prepare ani approve i używa transakcji READ ONLY dla odczytu
dwóch dokumentów. Oba oryginały mają EXIF orientation6 i rozmiar4032x3024.
Pierwszy wariant (EXIF transpose + dodatkowe90stopni + JPEG) odzyskał obie sumy
i znacznie więcej czytelnego tekstu, ale nadal ma błędy pozycji i identyfikatorów.
Nie jest to test samego EXIF: dodatkowy obrót zmienia więcej niż jedną rzecz.
Kontrolny wariant EXIF-only (transpose, RGB i JPEG92 bez dodatkowego obrotu)
także odzyskał obie sumy i czytelne nagłówki. Nadal błędnie rozpoznaje część cyfr
daty, identyfikatorów i pozycji, szczególnie w drugim paragonie. To wskazuje na
problem przygotowania orientacji JPEG przed OCR, nie na awarię uploadu. Worker
normalizuje obecnie tylko HEIF przed OCR; JPEG trafia bez tej normalizacji.
Rozpoznanie sumy po przygotowaniu obrazu nie dowodzi poprawności całego dokumentu.
Pełne teksty i hashe wyłącznie w prywatnych `evidence/orientation-probe.json` oraz
`evidence/exif-probe.json`; stany dokumentów/OCR/review i oryginały potwierdzono
identyczne przed/po obu probe. Kontrola sum pozycji odczytanych wizyjnie też PASS.

Nie zmieniono kodu aplikacji, konfiguracji LLM ani produkcji. Nie zapisano nowych
pól dokumentów lub płatności. Metoda płatności wydrukowana na paragonie nie jest
potwierdzeniem ani uzgodnieniem postingów. Wybór i implementacja docelowego odczytu
obrazów wymagają planu i zgody; odczyt dwóch zdjęć nie daje gwarancji dla ogółu dokumentów.
