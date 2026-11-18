# Picomatch — granica remediacji przed wdrożeniem

Status: **propozycja do akceptacji; brak zgody na zmianę zależności**.

## Cel i zgoda

Użytkownik wybrał „Napraw fixture i przygotuj plan”: wąska naprawa testu
backendu RED→GREEN oraz osobny plan remediacji zależności przed ich zmianą.
Nie jest to zgoda na nowy toolchain, fork, wyłączenie audytu lub podatności.

## Fakty z 2026-11-18

- Main `0e9e73c`, CI44253508543FAIL. Frontend zatrzymał się przed testami/buildem
  na npm audit:10high w łańcuchu zależności picomatch (nie10niezależnych CVE).
- GHSA-fc5q-39xc-vjpf / CVE-2026-112366: affected `<=4.0.7`, patched versions
  **None**; advisory zaktualizowane17XI. `npm view picomatch version` zwróciło
  `4.0.7`, a `npm view picomatch@4.0.8 version` E404.
- Lock zawiera picomatch4.0.5 pod tinyglobby0.2.17 oraz4.0.7 pod Vite/Vitest,
  także fdir6.5.0. Nie wystarczy wymienić jednego wystąpienia.
- Sugestia `npm audit fix --force` oznacza potencjalny breaking downgrade;
  nie jest dowodem usunięcia podatności.
- Lokalna dodatkowa próba `npm audit --json` zakończyła się timeout30s,
  nie jest nowym wynikiem PASS. Dowód audytu pochodzi z pełnego logu CI.

Źródła: https://github.com/advisories/GHSA-fc5q-39xc-vjpf oraz logi i artefakty
CI44253508543. Wyniki registry są obserwacją w czasie, nie stałą obietnicą.

## Niezmienne ograniczenia

- „Nie będę obniżał progu audytu, wyłączał bramek ani używał npm audit fix --force.”
- Nie instalować ani nie zmieniać zależności bez zatwierdzenia konkretnego rozwiązania.
- Nie zmieniać nazwy/wersji pakietu, metadanych advisory lub drzewa tylko po to,
  by skaner przestał widzieć podatny kod.
- Bez forków, nieprzejrzanych tarballi, Git HEAD lub nowego postinstall w ciemno.
- Brak poprawionej wersji nie jest zgodą na wdrożenie z czerwonym CI.
- Naprawa fixture nie może osłabić produkcyjnego sprawdzania ancestors/hash/owner/mode.
- Nowy kandydat wymaga pełnego CI i nowego exact scope proof do akceptacji.

## Proponowany kierunek autora

Preferowana jest utrzymywana poprawka upstream z konkretną wersją, integralnością,
źródłem i testem ReDoS. Dziś takiej wersji nie potwierdzono — bramka pozostaje
zamknięta. Alternatywą do osobnego projektu jest usunięcie wszystkich podatnych
łańcuchów przez kompatybilną wymianę narzędzi glob/toolchain; nie wybieramy teraz
nieznanego pakietu ani nie obiecujemy kompatybilności.

Plan decyzji ma zakończyć się zaakceptowanym konkretnym źródłem naprawy lub
jednoznacznym BLOCKED. Dopiero potem można napisać i zatwierdzić właściwy plan
zmiany package.json/lock. Ten dokument nie upoważnia do automatycznego wykonania.
