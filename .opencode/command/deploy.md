---
description: Przygotuj wersjonowany release i wdróż wyłącznie po zgodzie użytkownika
---

Produkcja: `https://finanse.birek.online`, VPS Docker Compose. Nie migruj do Cloudflare.

1. Przed wdrożeniem przeczytaj `docs/operations/backup-restore.md`, sekcję
   „Versioned Application Releases And Rollback”, oraz prywatne metadane
   `/opt/finanse/webapp/releases/active-release.json`. Ustal aktywny override,
   rewizje poszczególnych usług i istniejący rollback. Nie wypisuj sekretów.
2. Wymagaj zatwierdzenia dokładnej rewizji i zakresu wdrożenia. Przejście testów
   lub scalenie PR samo w sobie nie upoważnia do wdrożenia.
3. Uruchom testy, lint, typy i build. Przygotuj wersjonowany pakiet przez
   `ops/prepare_release.py` i skontroluj wynikowy Compose. Zmiana
   `backend/requirements.txt` wymaga nowego, zweryfikowanego runtime; nie obchodź
   zabezpieczenia przez podanie fałszywej rewizji starego obrazu.
4. Wykonaj i zweryfikuj kopię bezpieczeństwa według procedury. Zachowaj obrazy
   rollbacku oraz identyfikatory usług danych. Nie uruchamiaj importów, migracji
   ani napraw historycznych transakcji jako niejawnego kroku deployu.
5. Stosuj pełną listę Compose: bazowy `/docker/finanse/compose.yaml`,
   `/docker/finanse/compose.prod.yaml` oraz zatwierdzony `compose.release.yaml`,
   z istniejącym plikiem środowiska. Używaj `up -d --no-deps --no-build` tylko
   dla zatwierdzonych usług. Sam frontend można wymienić wyłącznie wtedy, gdy
   nie wymaga nowego API; nowe endpointy wymagają spójnego backendu i frontendu.
6. Sprawdź rewizje/obrazy, brak host mountu `/app`, niezmienione usługi danych,
   HTTPS, pliki statyczne, API health, odrzucenie anonimowych odczytów oraz logi.
   Nie wykonuj mutacji danych użytkownika w ramach smoke testu.
7. Przy awarii przywróć zapisany, zgodny pakiet rollbacku, używając tej samej
   pełnej listy bazowych plików Compose. Dopiero po udanej weryfikacji zaktualizuj
   prywatne metadane aktywnego release'u i zapisz wynik w PR.

Nie używaj samodzielnego bazowego Compose, `make up` ani `make restart`:
może to odtworzyć stare mounty kodu i ominąć wersjonowany release. Nie usuwaj
obrazów lub kopii rollbacku bez osobnej zgody.
