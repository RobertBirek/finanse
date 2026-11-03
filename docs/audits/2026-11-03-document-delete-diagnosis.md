# Diagnoza usuwania dokumentów — bez zmian produkcyjnych

## Zakres

Użytkownik: „Sprawdź usuwanie dokumentów”. Sprawdzenie kodu UI/API/modeli,
syntetyczna reprodukcja na identity-checked lokalnym `finanse_test`, produkcyjne
logi i ograniczony odczyt metadanych w transakcji READ ONLY. Nie wykonano DELETE,
AI/OCR, uploadu, zmiany schematu lub wdrożenia na produkcji. Nie eksportowano nazw,
treści, kwot, danych kontrahenta ani identyfikatora dokumentu.

## Ostatnia próba produkcyjna

- Bieżący kontener backendu: w ograniczonym wycinku logów24h/5000linii jeden
  DELETE /api/documents/... ze statusem409, bez IntegrityError. To nie dowód braku
  błędów w starszych kontenerach lub poza tym wycinkiem.
- Odczyt metadanych dokumentu wskazanego przez tę odpowiedź409: istnieje, done/vision,
  ma5rewizji, joby3failed+3succeeded, bez aktywnych pending/processing.
- Istnieje jedno powiązanie do dokumentu finansowego **approved/active**.
  Serwis prawidłowo blokuje usuwanie źródła finansowego. Ostatnia409 nie jest błędem
  FK z reprodukcji poniżej — kontrola powiązania zatrzymuje ją wcześniej.

## Reprodukcja lokalna

13syntetycznych przypadków potwierdziło aktualne zachowanie; kolejne2testy
bezpośrednio potwierdziły IntegrityError/SQLSTATE23503 i nazwy ograniczeń.
To PASS diagnozy, nie stwierdzenie, że usuwanie działa poprawnie.

| Przypadek | Obserwowany wynik |
|---|---|
| Niepowiązany dokument bez historii |200 |
| Niepowiązany dokument z tekstem OCR, bez jobu/review |200 |
| Gotowa rewizja review, bez powiązania finansowego |500 |
| Zakończony visionjob + rewizja |500 |
| LocalOCRjob succeeded / failed / paused |500każdy |
| Durablejob pending / processing |409, błędny detail o powiązaniu finansowym |
| Powiązanie do dokumentu finansowego |409 |
| LegacyOCR processing bez durablejob |200 (brak analogicznej blokady pracy) |
| Dokument innego właściciela / nieistniejący |404 |

W każdym przypadku syntetyczny plik oryginału pozostał na dysku. To obecna,
append-only semantyka bezpieczeństwa/backupów — usunięcie rekordu nie czyści storage.
Transakcje testowe cofnięte; produkcyjnych danych nie używano w testach.

## Przyczyny w kodzie

1. `backend/app/documents/service.py:271-300`: sprawdza powiązanie finansowe i aktywne
   durablejoby, następnie wykonuje `db.delete(doc)` bez obsługi istniejącej historii.
2. `DocumentExtractionRevision.document_id` i `DocumentProcessingJob.document_id`
   mają FK **RESTRICT** do documents. Zakończone rewizje/zadania nadal blokują harddelete.
   Potwierdzone23503: `document_extraction_revisions_document_id_fkey` i
   `document_processing_jobs_document_id_fkey`. Brak mapowania IntegrityError → błąd domenowy.
3. `backend/app/documents/router.py:302-305`: każdy ValueError, również
   `document_processing_active`, mapuje na identyczny409detail o dokumencie finansowym.
4. `frontend/src/components/DocumentList.tsx:145-170`: akcja zawsze dostępna poza
   trwającym DELETE, a każdy błąd pokazuje tylko „Nie udało się usunąć dokumentu.
   Spróbuj ponownie.”. Nie rozróżnia trwałej blokady, pracyAI/OCR i błędu serwera.
5. LegacyOCR/review tekstowy nie są objęte taką samą kontrolą aktywności jak durablejob.
   Obserwacja wymaga decyzji o cyklu życia/usuwaniu, nie niejawnego wyłączenia RESTRICT.

## Dalsza praca

Naprawa wymaga osobnego uzgodnienia: nie usuwać zatwierdzonych źródeł finansowych,
nie dodawać automatycznego CASCADE kasującego historię/usage/audyt i nie czyścić
oryginałów w ramach szybkiej poprawki. Najpierw ustalić kontrakt usuwania/archiwizacji
oraz komunikaty blokad. W tej sesji **nie zmieniono kodu aplikacji ani produkcji**.

Dowody prywatne: `/tmp/opencode/document-delete-check-20261103/`:
diagnostic-tests.log, case-*.json, foreignkey-*.json, production-log-summary.json,
latest-409-metadata-proof.json. Snapshotują wyłącznie syntetyki/statusy/klasy ograniczeń.
