# Velo — konfiguracja istniejącego profilu

Data:2026-11-08. Status: **zapisane i zweryfikowane na produkcji**.

## Zgoda i wybór konta

Użytkownik: „masz dane skonfiguruj od razu”. Parametry wskazane przed operacją:
limit33 600PLN, APR14,50%, cykl18–17, domyślna spłata12, maksymalnie57dni
bezodsetkowych. Bez zmian salda, transakcji lub odtwarzania zamkniętych planów.

Read-only discovery znalazł dwa konta o dokładnie tej samej nazwie „VELOBANK - karta”
u różnych właścicieli. Zabezpieczenie przerwało pierwszy odczyt wyboru bez zapisu.
Użytkownik jawnie wskazał **Robert**; konto drugiego właściciela pozostawiono bez zmian.
Identyfikatory właściciela/konta przypięto w prywatnych dowodach, nie zapisano w repo.

## Zapis

Właściwy rachunek miał już typ `credit_card` i profil wersji1. Limit3360000groszy,
APR14.5000 i zamknięcie cyklu17 były prawidłowe. Faktyczna zmiana:

- `due_day`:17→12;
- `grace_days`:56→57;
- wersja profilu:1→2.

Przed operacją świeży backup szyfrowany przez istniejący serwis: Resultsuccess,
ExecMainStatus0. Operacja przez istniejący serwis `credit_cards.configure`, nie surowy
UPDATE profilu: walidacja PLN/aktywności/właściciela/wersji/loanlink, mutex mutacji
i wyłączna blokada konta. Jedna transakcja REPEATABLE READ; przed zapisem dokładna
zgodność odczytanego profilu z zatwierdzonym stanem.

Powstał standardowy audit konfiguracji i dodatkowy `operator_configuration`
z `performed_by=agent`, parametrami i treścią zakresu zgody. Nie utworzono sesji,
nie logowano się jako użytkownik, nie ujawniano sekretów.

## Weryfikacja

- SHA-256 serializacji JSON wszystkich tabel poza docelowym profilem i nowymi auditami
  zgodne przed/po operacji; inne profile również identyczne. Konta, postings,
  transakcje, wyciągi, raty, użytkownicy i sesje zachowane.
- Bieżące zadłużenie, dostępny limit, rezerwacje, nadpłata i przekroczenie bez zmian.
- Istniejące plany/wyciągi/koszty/alokacje bez zmian; bez nowych planów lub transakcji.
- Oddzielny readonly odczyt po commit: limit3360000/APR14.5000/close17/due12/grace57/
  version2; pozycja identyczna, karta widoczna w owner-scoped zbiorczym przeglądzie.
- Bez zmian kodu, migracji, deploymentu, obrazów lub restartów. Operacja korzysta
  z odebranego i wdrożonego7801ba5, schema739144d5eaef.

Nie wykonano nowego uzgodnienia zadłużenia z najnowszym wyciągiem. Rzeczywisty termin
bankowy wygrywa z nominalnym12; maksymalnie57dni zależy od warunków banku.

Dowody prywatne: `/tmp/opencode/velo-card-config-20261108/`, w tym
`authorization.json`, `configuration-proof.json`, `backup-status.log`.
