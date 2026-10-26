# Makieta finansów — 2026-10-26

Samodzielny, tymczasowy prototyp pod `/makieta/`. Nie jest nowym interfejsem produkcyjnym.

- Wyłącznie fikcyjne dane w pamięci strony; bez API, fetch, cookies i localStorage.
- CSP `connect-src 'none'` i `form-action 'none'`. Brak bibliotek i zewnętrznych fontów.
- Widoki: przegląd, transakcje, budżet, nadchodzące, raporty, ustawienia.
- Kliki: filtry, szczegóły, transfer, zmiana kategorii, tworzenie i edycja kont,
  drzewo kategorii, dodawanie/przenoszenie podkategorii, limity, jasny/ciemny motyw.
- Prognoza jest stałym, jawnie oznaczonym scenariuszem. Zmiany znikają po przeładowaniu.
- Numery IBAN/BIC są celowo fikcyjne. Nie wprowadzać rzeczywistych danych.

Kierunek: canvas `#f5f6f8`, surface `#ffffff`, ink `#15191e`, muted `#667085`,
blue `#245bea`, green `#13755b`. Source Sans 3 (istniejący lokalny font) dla UI,
systemowy Arial dla głównych kwot i nagłówka. Jedna spokojna nawigacja.
Wyróżnik: osobna granatowa karta przebiegu prognozy, wyraźnie odróżniona od salda.

Pliki w `public/` zostaną uwzględnione przy kolejnym standardowym buildzie Vite.
Pierwsza publikacja: dodanie tylko `index.html`, `style.css`, `progress.css`, `app.js` do nowego
katalogu `/usr/share/nginx/html/makieta` działającego frontendu, bez restartu.
Taki katalog przetrwa restart, ale nie odtworzenie starego kontenera/obrazu;
przed następnym deployem należy uwzględnić te pliki w obrazie albo opublikować ponownie.
Nie zmieniać metadanych rewizji aplikacji: to nakładka statyczna, nie nowe wydanie.

## Publikacja i weryfikacja

- Użytkownik zatwierdził klikalny prototyp i publikację pod
  `https://finanse.birek.online/makieta`. Nie zatwierdzał przebudowy właściwej aplikacji.
- Opublikowano 2026-10-26: statyczny nowy katalog, uprzednio nieistniejący,
  przeniesiony atomowo po sprawdzeniu hashów czterech plików.
- HTTPS `/makieta`, `/makieta/` i cztery zasoby: 200, hashe zgodne z repo.
  Istniejące pliki webroot oraz konfiguracja Nginx mają te same hashe co przed operacją.
- IDs, obrazy i czasy startu sześciu kontenerów finansów niezmienione; health 200.
  Bez restartu, migracji, odczytu/zapisu bazy, uploadu, importu ani modyfikacji Compose.
- Lokalnie i na docelowym HTTPS: 12 widoków × 5 szerokości
  (320/375/768/1024/1440), brak poziomego overflow dokumentu.
- Playwright: wyszukiwanie, filtry, szczegóły i Escape, ujawnienie fikcyjnego IBAN,
  nawigacja prognozy, rozwijanie drzewa, dodanie/przeniesienie podkategorii,
  wykluczenie potomków z wyboru rodzica, edycja/tworzenie kont, transfer zachowujący
  sumę sald wszystkich kont, dodanie wydatku i bezpieczny tekst HTML,
  motywy i nawigacja mobilna: PASS. W nowym kontekście przeglądarki brak błędów JS/CSP,
  żądań API, żądań mutujących, cookies i localStorage.
- Axe: 4 główne widoki × 2 szerokości, brak naruszeń badanych reguł
  WCAG 2 A/AA i 2.1 AA. Tylko kontekst audytu omija CSP, aby wstrzyknąć axe;
  osobny główny test respektuje CSP. Nie jest to pełna certyfikacja dostępności.
- Frontend: 194 Vitest PASS, ESLint/tsc/build PASS, `node --check` prototypu PASS.
  Testy backendu nieuruchamiane: bez zmian backendu i połączenia prototypu z API.
- Artefakty sprawdzeń i screenshoty: `/tmp/opencode/makieta-20261026/`.
  Skrypty lokalne: `/tmp/opencode/test_finance_mockup.py`,
  `/tmp/opencode/axe_finance_mockup.py`, `/tmp/opencode/publish_finance_mockup.py`.

## Ograniczenia i następny krok

To prototyp do oceny wizualnej, nie implementacja księgi. Nie korzysta z logowania
ani danych użytkownika. Formularze i limity zmieniają tylko fikcyjny stan strony.
Data jest przypięta do października 2026. Wybór okresu i moduły poza finansami
pokazują objaśnienie zakresu. Reguły/import to oznaczone koncepcje.
Waluta demonstracyjna to PLN; brak rzeczywistej walidacji IBAN i prognozy backendowej.
Przed wdrożeniem docelowego UI potrzebne są uwagi i zgoda na pełny projekt/plan,
testy kontraktów, migracje pól bankowych oraz zachowanie istniejącej księgi i mapowań.
