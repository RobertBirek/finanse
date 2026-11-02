# iPhone JPEG z mapą HDR — poprawka obsługi, 2026-11-02

## Zgoda i zakres

Po potwierdzeniu odrzucenia JPEG/MPO użytkownik zatwierdził poprawkę, testy,
niezależny przegląd i przygotowanie wdrożenia. Zakres: rozpoznany wariant Apple,
zachowanie oryginału i użycie głównego obrazu w pochodnych. Nie dowolne MPO.

## Odtworzenie

- Udostępniony JPEG3809248B, sygnatura i końcoweEOI poprawne, PillowMPO/2obrazy.
  Główny4032×3024 i pomocniczy2016×1512. Rola pomocniczego została następnie
  potwierdzona strukturalnie: Apple pixeldatainfo AuxiliaryImageType=HDRgainmap
  i HDRGainMapVersion65536. Nie odczytywano treści faktury/OCR ani EXIF/GPS.
- Dokładny obecny obraz9369b5d z produkcyjnymi limitami odrzuca plik: mime=null.
  Powód: jawna bramka formatu i n_frames!=1 w validation_process.py.
- Badanie i weryfikacja poprawki: odizolowany kontener networknone/read-only/UID10001,
  parser i normalizer z rzeczywistymi limitami produkcji; bez DB/AI/uploadu aplikacyjnego.
  Oryginał niezmieniony, prywatne piksele nie trafiły do repo lub obrazów wydania.

## Rozwiązanie

- Minimalny przyrost wyłącznie w samodzielnym validation_process.py; MIME=image/jpeg.
- Dwa indeksowane JPEG: MP0100, główny Baseline MP Primary Image, pomocniczyUndefined;
  bez zależności lub zarezerwowanych flag. Ciągłe, dokładne zakresy pliku, poprawne
  indeksy oraz rzeczywisty końcowy EOI każdej części, nie tylko ostatnie dwa bajty.
- Pełne dekodowanie obu obrazów; pomocniczy nie większy od głównego; dotychczasowe
  limity pikseli/rozmiaru/czasu/CPU/pamięci bez zmian.
- Wymagane poprawne XMP UTF-8 z pojedynczą rolą AppleHDRgainmap i wersją65536.
  DTD, deklaracje encji, referencje znakowe/encje i nieznane profile odrzucane.
- Istniejący normalizer wybiera główny obraz, stosuje orientację i tworzy pojedynczy
  JPEG bez metadanych. Test syntetyczny różnymi kolorami obu obrazów przypina wybór
  głównego, orientację i brak XMP/EXIF/GPS. Serwis zachowuje oryginał bajtowo.
- Bez zmian frontendu, zależności, schematu, konfiguracji AI, polityki vision, auth,
  księgi lub niejawnego przetwarzania starych dokumentów.

## Weryfikacja i przegląd

- Pierwsze RED: akceptacja i bounded MIME; po poprawieniu testowej rejestracji modeli
  również RED przechowania oryginału. Pierwszy focused88PASS, Ruff/mypy PASS.
- Niezależny przegląd wskazał2Important: dane za rzeczywistym EOI wewnątrz zakresuMP
  i referencje znakowe XML. Jedna poprawka:3regresjeRED→GREEN, focused91PASS,
  Ruff/mypyPASS. SkanerJPEG pomija segmenty długościowe i stuffing danych entropy.
- Minor odroczony: dodatkowe bezpośrednie przypadki brakujących/powtórzonych pólMPF;
  błędne zakresy/typy/dependencies, dodatkoweobrazy, ucięcia i trailing są testowane.
- Lokalna weryfikacja udostępnionego JPEG na kodzie kandydata: boundedparserJPEG PASS,
  boundednormalizer pojedynczyJPEG3024×4032 bezEXIF/XMP PASS, oryginał niezmieniony.
- Świeży build i93E2E+1celowy skip PASS; źródła/dist związane manifestem, dist bez
  zmian między build i E2E. Szesnaście offline testów procedury wydania PASS.
- Świeży backup **b9b3a8d5** oraz zainstalowany restore tego snapshotu success/0,
  bez czyszczenia failedcounter lub zmiany jednostek systemd.
- Scoped operacyjny przegląd zamknął Important dotyczący pochodzenia smoke obrazu:
  probe wymaga przypiętego backendimageID/reference oraz zgodnego OCIrevision,
  apply sprawdza exact_image i imageID proofu. RegresjaRED→GREEN, warunkowy odbiór
  procedury. Wymagane dowody gotowego pakietu i zgoda exactSHA następnie uzyskane.

## Stan wydania

**Wydanie45c8c2d zakończone; oczekuje jedynie na rzeczywistą próbę użytkownika.**
Dokładny kandydat: `45c8c2d45311620320abd21a189706810c31069b`.
Wynik1057backendPASS/8deselected/10znanychostrzeżeń,316frontendPASS i lint/typesPASS.
Manifest potwierdza niezmienione bajty źródeł podczas całego gate i przed commitem.
Oba obrazy backendowe zawierają dokładnie200plików z archiwum Git; konfiguracja,
hardening, sieci i wolumeny identyczne z aktywnym runtime poza obrazami.
Gotowy przypięty obraz backendu z OCIrevision45c8c2d: prywatny JPEG boundedparser
image/jpeg i pojedyncza pochodna3024×4032/noEXIF/XMP PASS, zeroAI/DB i niezmieniony
oryginał. Oddzielny syntetyczny HTTPsmoke wszystkich4kodów400 PASS.
Na pytanie o wdrożenie dokładnej wersji45c8c2d użytkownik odpowiedział „scal na main
i wdróż”. Lokalny main FF8c2fa67 (kod45c8c2d+odebrana dokumentacja), bez push.
Cały manifest źródeł zgodny z pełnym gate; na main ponownie21testów poprawki,
Ruff/mypyPASS. Preapply: aktywna wersja, HMAC konfiguracji, dane/schema/policy,
oryginały i identyfikatory usług bez zmian, kolejki bez aktywnych dokumentów.
Testy działały tylko na izolowanym finanse_test55432, z wyłączonymi kluczami AI.
Manifest przypina faktycznie testowane niezmienione bajty.
ExactSHAapproval zapisane; zatwierdzone runtime apply zakończone, nie ponawiać go.
Apply zakończonePASS: działające spójne obrazy i HTTPS/assets/auth, dane/originals/
schema/policy/data-serviceIDs bez zmian poza dokładnie4własnymi audytami401.
Nie wykonano migracji ani operacji policy. Read-onlybrowser375/1440 i końcowa
obserwacja zostały zakończonePASS: oba viewporty bez błędów/mutacji/overflow,
10próbekPASS, atomic active-release2026-11-02T14:00:26Z. Świeże HTTPS200 oraz
działające imageIDs/OCIrevision zgodne z metadanymi PASS. Można poprosić o próbę.
Rollback pozostaje dokładną poprzednią wersją9369b5d, bez migracji lub operacji policy.

Prywatne dowody: `/tmp/opencode/iphone-jpeg-20261102/` (0700; plik wejściowy0600).

## Decyzja wykonawcza

Kontynuacja inline zatwierdzonej małej poprawki zamiast kolejnej rundy pytań o metodę.
Niezależny przegląd i pełne bramki wydania zachowane; koszt nietrafienia preferencji:
użytkownik mógłby woleć osobnych wykonawców per task. Nie obniża to bramek bezpieczeństwa.

Scalenie na main było fast-forward i zachowało cały manifest testowanych źródeł.
Nie powtarzano identycznego22-minutowego pełnego gate: na main ponownie21regresji,
Ruff/mypy i pełna zgodność bajtów źródeł z1057/316gate. Koszt tej decyzji: pełny zestaw
nie był ponownie uruchomiony w środowisku hostcheckout; regresje wyłącznie środowiskowe
mogłyby wymagać osobnego odtworzenia. Gotowe obrazy i produkcja miały własne smoke.
