# Diagnostyka odrzucenia uploadu iPhone — zatwierdzona mała poprawka

Użytkownik zatwierdził wdrożenie propozycji: pokazać konkretny powód400 bez treści
faktury. Oryginał HEIF3675697B/3024x4032 przechodzi lokalny ograniczony parser,
takżeUID10001. Produkcyjny Safariupload otrzymuje400/67B. Rootcause transportu/MIME
nie jest jeszcze rozstrzygnięty, ta poprawka daje dowód, nie obiecuje naprawy uploadu.

## Zakres

- Stabilne kody odrzucenia w JSON400 oraz tłumaczone komunikaty w DocumentUpload.
- Serwerowe logi zawierają wyłącznie kod, normalizowane deklarowane/rozpoznane MIME
  z istniejącej allowlisty (nieznane jakoother/unknown) i liczbę bajtów. Bez filename,
  idużytkownika/dokumentu, hashów, EXIF, treści, wyjątku parsera lub modelresponse.
- Nie zmieniać warunków walidacji, dekoderów, limitów lub dopuszczanych MIME.
- Nie zapisywać prywatnego pliku w testach/repo, nie wywoływaćAI z diagnozy.
- Bez migracji/zmianyfinance/auth/policyvision i bez backfillu.

## Kontrakt

400: `{"detail": <dotychczasowy bezpieczny stały opis>, "code": <enum>}`.
Kody: `document_mime_unsupported`, `document_empty`, `document_validation_failed`,
`document_mime_mismatch`. Parserresult/timeout/invalidIPC pozostają failclosed i
mapują na validationfailed; mismatched MIME po udanym parserze mapuje na mismatched.
Wyjątek UnsupportedDocumentFormatError ma opcjonalny keyword `code` z domyślnym
validationfailed; stary konstruktor `UnsupportedDocumentFormatError("...")` działa.
Wyjątek może też przenieść `detected_mime: str | None` tylko z udanego parsera;
router normalizuje go allowlistą zanim użyje w logu. Do odpowiedzi nie trafia MIME
użytkownika ani surowy wyjątek. Nieznany code mapowany na validationfailed.
Log ma stały template `Document upload rejected code=%s declared_mime=%s detected_mime=%s bytes=%s`.
Kody i MIME w logu wybierane przez zamknięte mapowanie; nigdy repr wyjątku.

UI400 maps:
- mimeunsupported: „Nieobsługiwany typ pliku. Wybierz PDF, JPG, PNG, HEIC lub HEIF.”
- empty: „Wybrany plik jest pusty. Wybierz go ponownie.”
- validationfailed: „Nie udało się odczytać pliku. Spróbuj wybrać oryginał przez Pliki zamiast biblioteki Zdjęć.”
- mimemismatch: „Typ przesłanego pliku nie zgadza się z jego zawartością. Spróbuj wybrać oryginał przez Pliki zamiast biblioteki Zdjęć.”
Nieznany/brak kodu zachowuje obecny ogólny komunikat;413/503/507 bez zmian.
Nie wyświetlać dowolnego serverdetail (niezaufane inputy).

## Wykonanie

- [x] RED: prawdziwe parser/mismatch i endpoint400 + caplogbezsekretów, UIall4codes,
  unknownfallback i stare413/503/507. Syntetyczne dane tylko.
- [x] Implementacja: validation.py/router.py/DocumentUpload.tsx + testy, bez refactorów.
- [x] GREEN: /test /lint /typecheck equivalents na finanse_test55432, build/E2E,
  jeden suiteDBnaraz. Source/testcommit dopiero poPASS.
- [x] Niezależny review przyrostu i poprawki tylko jeśli wymagane.
- [x] Backup/restore; spójne obrazy backend/worker/frontend dokładnegoSHA z zgodnego
  obecnego runtime, pełny Compose base+prod+active+release. Bez migracji lub policychange.
- [x] HTTPS/assets/health/auth, safe log/responsecode smoke na syntetycznym odrzuconym
  uploadzie BEZ prawdziwej sesji lub zapisu; jeśli nie ma bezpiecznego konta smoke,
  localexactimageAPItest zamiast mutacji użytkownika. Obserwacja/rollback84obrazów,
  dane/originalniezmienione poza ownsecurityaudits, metadaneatomowe/dokumentacja.
- [ ] Poprosić użytkownika o jedną próbę; nie twierdzić, że naprawiono Safariupload
  zanim znany jest kod i wynik rzeczywistego żądania.
