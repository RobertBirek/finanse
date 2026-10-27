# Waluta konta — pierwszy zatwierdzony slice

Użytkownik zaakceptował kolejność: waluty, następnie Q7 jako pierwszy przypadek
zobowiązań, później karta/Allegro Pay (również odsetki), pożyczki rodzinne,
Goodie i darowizny. Ta zmiana obejmuje wyłącznie pierwszy slice.

## Zachowanie

- Waluta PLN/EUR/USD widoczna w edycji każdego konta; osobne konta Revolut EUR/USD.
- Nowe, puste ręczne konto pozwala zmienić walutę. Nie przeliczamy ani nie
  przepisujemy istniejących transakcji, sald otwarcia i mapowań Actual.
- Konto z dowolnym postingiem (także pending i przy saldzie zero), harmonogramem
  (także nieaktywnym) lub powiązaniem importowym ma blokadę zmiany waluty.
  Źródło inne niż manual również blokuje, nawet przed pojawieniem się mapowania.
- Ponowne przesłanie aktualnej waluty jest idempotentne i dozwolone.
- Jawne null i waluta spoza PLN/EUR/USD są błędem walidacji; lowercase normalizujemy.
- PATCH odrzucający walutę nie może częściowo zmienić nazwy/innych pól. Inny owner
  dostaje 404. Konflikt z historią to 409, nie 500.
- Capability `can_change_currency` jest wyliczana z PostgreSQL w list/detail,
  bez N+1. Frontend przy braku capability zachowuje się fail-closed.
- UI wyświetla wyjaśnienie blokady i umożliwia edycję pozostałych pól.
  Walutę wysyła tylko gdy faktycznie zmieniona. Serwer ponownie sprawdza blokadę.
- Sprawdzenie i zapis chronią blokady kont przed równoczesną pierwszą transakcją
  lub utworzeniem/zmianą harmonogramu; odczyty waluty po czekaniu odświeżają ORM.

## Ograniczenia

Bez migracji schematu, deployu, importu, korekt księgi i zmian danych produkcji.
Obecny wygląd i mechanizm wyświetlania sald źródłowych/księgowych pozostają.
Nie budujemy teraz modułu zobowiązań ani nie importujemy harmonogramu Q7.

Decyzja implementacyjna: importowe powiązania i harmonogramy również blokują
zmianę pustego konta, żeby nie rozminąć się z ich walutą. To ostrożniejsze niż
sam warunek „saldo zero”; koszt: osobne uzgodnienie przy błędnym imporcie.
