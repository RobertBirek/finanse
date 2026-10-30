# Potwierdzona korekta źródłowej waluty i wyceny PLN

## Zgoda i zakres

Użytkownik potwierdził EUR dla wszystkich historycznych kwot wskazanego konta,
następnie jawnie zatwierdził korektę obu stron operacji i przeliczenie wyceny PLN
historycznymi kursami NBP, z backupem i audytem. To nie import ani przewalutowanie.
Identyfikatory/kwoty tylko w prywatnym `/tmp/opencode/revolut-eur-20261028/`.

## Ograniczenia

- Operator-only serwis finance, bez HTTP endpointu i bez osłabiania AccountUpdate.
- Własne jedno konto actual PLN, wyłącznie proste przychody/wydatki po dwa postingi
  PLN z kursem1 i równymi źródłowymi/bazowymi kwotami; nie transfer/exchange.
- Kwoty źródłowe, ID, daty, kierunki, kategorie, mapping Actual i budget-impact bez zmian.
- Konto i oba postingi otrzymują EUR; wycena PLN Decimal/half-even według istniejącego
  NbpRateProvider dla daty transakcji (fallback poprzedniego dnia dla weekendu).
  Brak kursu, zależności harmonogramów/umów/linków, inny owner lub drift = brak zapisu.
- Podgląd nie mutuje. Zapis wymaga dokładnego digestu zatwierdzonego planu,
  blokad konta i transakcji, ponownego odczytu oraz niezmienionego snapshotu.
- Jedna transakcja z audytem old/new. Nie tworzyć nowych transakcji ani postingów.
- Weryfikacja całej produkcji przed/po dopuszcza tylko wskazane pola konta i postingów
  oraz timestampy i nowy audit event. Pozostałe dane/original uploads bez zmian.
- Nie wymieniać kontenerów aplikacji: przetestowany serwis uruchomiony jednorazowo
  jako operator przez readonly moduł, z zapisanym hashem dokładnego kodu.

## Plan i postęp

- [ ] RED: preview bez zmian; apply w EUR i poprawny ledger/audit; błędny owner,
  drift, brak kursu, mieszana waluta/transfer/dependency, brak zatwierdzonego digestu.
- [x] GREEN: `backend/app/finance/currency_correction.py` i integration tests (14 PASS).
- [x] Prywatny podgląd rzeczywistych danych i oficjalnych kursów; brak zgadywania.
- [x] Pełny pytest + Ruff/mypy, niezależny review; świeży backup/restore.
- [x] Próba na izolowanej kopii, potem jednorazowy zapis po ponownym guardzie.
- [x] Świeży odczyt salda EUR/PLN, invariantów, audytu i niezmienności reszty mapped danych.
- [x] CHANGELOG/TASKS/JOURNAL z wynikiem, bez prywatnych danych w Git.

Targeted13/Ruff/mypy69 PASS; backup1732c2cc i restore success/0; identyczna korekta
na izolowanej świeżej kopii produkcji PASS. Pełny backend i świeży review w toku.
Produkcja bez zapisu do czasu tych gate'ów. Frontend niezmieniony,243/lint/types PASS.

Review zatrzymał pierwszy apply:4 uwagi poprawione (niezależny pin, live NBP przy
apply, wszystkie mapped tables +dokładny audit, kontrole explicit raise zamiast assert).
Podmieniony NBP rate/recomputed digest RED→GREEN. Regeneracja preview i próba na
kopii ponownie PASS; -O nie wyłącza guardów. Final full pytest i scoped re-review w toku.

Zamknięcie: backend858 PASS, review zamknął4 uwagi do kodu. Brakujący review-proof
z pinem został uzupełniony po teście; approval CLI literalnie z sealed pliku.
Apply produkcyjny i fresh READ ONLY PASS (6 transakcji/12 postingów,EUR,1 audit).
Nie powtarzać operacji. Kod lokalnie51bf351, bez nowego deployu/main/push.

## Spójność interfejsów

Preview produkuje snapshot digest i kursy → apply konsumuje dokładnie ten plan;
NBP dostarcza faktyczne dane, serwis nie ma domyślnego kursu. Operator dostarcza
potwierdzoną tożsamość owner/account → serwis ponownie weryfikuje ownership.
Nie ma nowej migracji ani powiązania z rolloutem aplikacji.
