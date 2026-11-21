---
description: Przygotuj wersjonowany release i wdróż wyłącznie po zgodzie użytkownika
---

Produkcja: `https://finanse.birek.online`, VPS Docker Compose. Nie migruj do Cloudflare.

1. Przed wdrożeniem przeczytaj `docs/operations/backup-restore.md`, sekcję
   „Versioned Application Releases And Rollback”, oraz prywatne metadane
   `/opt/finanse/webapp/releases/active-release.json`. Ustal aktywny override,
   rewizje poszczególnych usług i istniejący rollback. Wznów od ostatniej
   ważnej bramki opisanej w „Przekazanie wydania między agentami”.
   Prowadź jeden prywatny zapis poza Git:

   ```text
   Kandydat / aktywna rewizja:
   Przypięte obrazy i wejścia / rollback:
   Ostatnia zaliczona bramka / ścieżka do dowodu:
   Następny krok / warunek STOP:
   Brakująca zgoda / zakres / liczba uruchomień:
   ```

   Nie wypisuj sekretów. Przed pierwszym odczytem produkcji sprawdź fazę Git
   na docelowym checkoutcie, pod docelowym UID i w czystym środowisku launchera.
   Nie zmieniaj właściciela ani `safe.directory`, żeby wymusić przejście.
2. Wymagaj zatwierdzenia dokładnej rewizji i zakresu wdrożenia. Przejście testów
   lub scalenie PR samo w sobie nie upoważnia do wdrożenia.
   Po osobnej zgodzie na odczyt rzeczywistego środowiska uruchom readonly
   przez osobno przejrzany i zaakceptowany launcher V2, zgodnie z sekcją
   „Read-only release preflight” w procedurze. Nie uruchamiaj checkera z kandydata.
   Najpierw wymagane są dokładne zewnętrzne piny pakietu/runtime, toolchainu,
   opcjonalnego scope proof i prywatny receipt rzeczywistej zgody administratora.
   Lokalny odbiór kodu nie jest zgodą na pakowanie/instalację ani odczyty produkcji.
   Podaj pełne SHA, pełną listę Compose/env/projekt/PG, prywatny scratch0700
   oraz niezależnie zatwierdzony inventory i jego SHA256. Nie wydawaj inventory
   z bieżących obserwacji ani nie zmieniaj aktywnych metadanych, aby kontrola przeszła.
   `blocked`/exit2 oznacza STOP; exit0 to klasyfikacja źródeł/schematu, nie zgoda
   lub production-ready. Oceń zewnętrzny env/mounty/ingress osobno.
   Sprawdź również gotowość każdej zmienionej funkcji, nie tylko health API.
   Dla sekretu zapisz wyłącznie obecność, poprawność formatu i zgodność między
   wymaganymi usługami; brak odnotuj jawnie, nie zgłaszaj funkcji jako gotowej.
   Domyślne unknown scope nadal blokuje; jedynie exact review proof dla plików
   checkera/deploy może uznać konkretną zmianę tooling. Nie pozwala to instalować
   narzędzi, zmieniać etykiet aplikacji lub pomijać wcześniejszego blocked V1.
   `no_rollout` dla samych docs/testów/zatwierdzonego tooling oznacza brak nowych bajtów aplikacji:
   nie buduj i nie restartuj identycznych usług wyłącznie dla nowszej etykiety.
   `app_only` na już zmigrowanym schemacie nie upoważnia do ponownego backfillu;
   `migration_then_app` wymaga osobnej zgody na dokładną migrację.
   Po zmianie stanu raport jest nieaktualny; przed mutacją ponów sprawdzenie
   pod istniejącym deploylock. Bramka nie zastępuje żadnego z dalszych dowodów.
3. Uruchom testy, lint, typy i build. Przygotuj wersjonowany pakiet przez
   `ops/prepare_release.py` i skontroluj wynikowy Compose. Zmiana
   `backend/requirements.txt` wymaga nowego, zweryfikowanego runtime; nie obchodź
   zabezpieczenia przez podanie fałszywej rewizji starego obrazu.
   Po zbudowaniu backendu/workera obowiązkowo uruchom `ops/verify_release.py`
   dla gotowego pakietu i numerycznych non-root UID:GID obu usług z finalnego
   wyrenderowanego Compose (nie z domyślnego USER obrazu). Zachowaj JSON dowodu
   dla dokładnych image IDs. Błąd/timeout/import/read-access oznacza STOP przed
   `compose up`; nie obchodź go przez root lub podłączenie produkcyjnego env/DB.
   Jeśli obrazy przebudowano/przetagowano lub zmieniono docelowego użytkownika,
   bramkę uruchom ponownie i porównaj IDs dowodu z obrazami wdrożenia.
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
