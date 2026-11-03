# Bezpieczna archiwizacja dokumentów — zakres zatwierdzony lokalnie

## Cel i decyzja proponowana przez asystenta

Użytkownik poprosił o plan naprawy usuwania, następnie „zaproponuj bezpieczny wariant”.
Następnie zatwierdził pełny zakres lokalnej implementacji z testami i niezależnym
przeglądem („tak”). Produkcyjna migracja ani wdrożenie nie są zatwierdzone.
Rekomendacja: zamiast nieodwracalnego harddelete oferować **Archiwizuj / Przywróć**.
Pozostać w obecnej architekturze FastAPI/PostgreSQL/React; nie dodawać zależności.
Podstawa: `docs/audits/2026-11-03-document-delete-diagnosis.md`.

## Kontrakt użytkowy

- Archiwizacja ukrywa dokument na zwykłej liście, nie usuwa rekordu, pliku, tekstu,
  rewizji/jobów AI/OCR, usage ani audytu. Osobny widok „Archiwum” umożliwia przywrócenie.
- Można archiwizować źródło powiązane z zatwierdzonym dokumentem finansowym, ponieważ
  nie niszczy to źródła. Powiązanie, dostęp do oryginału w finansach, dane rachunku,
  płatności i księga pozostają bez zmian. To nie anulowanie dokumentu finansowego.
- Aktywna praca blokuje archiwizację: komunikat „Dokument jest przetwarzany. Poczekaj
  na zakończenie odczytu AI/OCR.”. Nie anulujemy pracy ani nie obchodzimy blokady.
- Potwierdzenie: „Przenieść dokument do archiwum? Plik, historia odczytu i powiązania
  finansowe pozostaną zachowane.”. Po sukcesie „Dokument przeniesiony do archiwum.”.
- Przywrócenie zmienia wyłącznie widoczność, bez ponownego AI/OCR lub naliczenia usage.
- Ponowny upload tego samego zarchiwizowanego pliku zwraca istniejący dokument:
  „Ten plik jest już w archiwum. Możesz go przywrócić.”. Nie odtwarza go automatycznie,
  nie tworzy duplikatu/nowego odczytu. Zachowane pliki nadal zajmują limit storage.
- Archiwum jest stanem dokumentu (`archived_at` w PostgreSQL), nie filtrem tylko w UI.
  Odczyt oryginału i historii po UUID pozostaje prywatny/owner-scoped także w archiwum.

## Bezpieczeństwo i cykl życia

- Brak harddelete/CASCADE/garbage collection/zmian historycznych finansów w tym zakresie.
- Archiwizacja i utworzenie pracy synchronizują się blokadą tego samego rekordu
  Document. Rozpoczęta wcześniej praca powoduje409; wygrana archiwizacja uniemożliwia
  utworzenie nowej pracy. Dotyczy durablevision/OCR, legacyOCR i tekstowego review.
- Niedokończone durablejoby oraz rzeczywiste pending/processing review blokują; stare
  rewizje z terminalnym failed/paused/superseded/succeeded jobem nie udają aktywnej pracy.
  Zwykłe paused/failed/superseded joby nie są wznawiane przez archive/restore.
- Archiwalne dokumenty nie trafiają do aktywnego discovery ani dispatcherów. Nowy
  prepare/retry z nową intencją zwraca409 `document_archived`. Replay już zapisanej,
  identycznej intencji może zwrócić istniejący wynik, ale nigdy nie kolejkuje pracy.
- Operacje są owner-scoped, zabezpieczone istniejącym auth/CSRF, idempotentne i audytowane
  w tej samej transakcji. Obcy UUID zwraca404, bez ujawniania istnienia dokumentu.
- Stary DELETE staje się kompatybilną archiwizacją (200, bez harddelete), a nowy UI
  nazywa czynność wprost. Nie pozostawiamy publicznej ścieżki nieodwracalnego kasowania.
- UI czyści tylko właściwe sesji watch/toast/cache po archiwizacji; spóźniona odpowiedź
  po logout lub zmianie właściciela nie może zmodyfikować nowej sesji.

## Zakres i odbiór

Zmiana wymaga jednej addytywnej migracji nullable archived_at i spójnego API/UI.
Wszystkie istniejące dokumenty zachowują archived_at=NULL; bez backfillu klasyfikacji,
AI/OCR, automatycznej archiwizacji lub utraty źródeł. Testy na syntetykach i izolowanej
bazie, TDD, niezależny review, pełny gate i mocked E2E375/1440. Produkcyjna migracja
i wdrożenie wymagają osobnej zgody, świeżego backupu/restore oraz kompatybilnego rollbacku.

Poza zakresem: fizyczne kasowanie/retencja plików, anulowanie zatwierdzonych finansów,
masowe akcje, zmiany ekstrakcji, automatyczne naprawianie/replay historycznych jobów.
