# Produkcyjna reorganizacja drzewa kategorii — wykonana

## Zgoda i zakres

Użytkownik odpowiedział „tak” na osobne pytanie o produkcyjny APPLY:
30 minimalnych aktualizacji i 14 nowych kategorii, wraz z krótkim maintenance
i końcowym backupem/restore. Dokładna tożsamość operacji, właściciel i prywatna
taksonomia pozostają poza Git. Zatwierdzony request SHA256:
`34e530680ff529126de628a5e4201cf4f10840576278db19651c8954136febaa`.

To operacja danych, nie wdrożenie aplikacji. Aktywne wydanie nadal `8121512`,
schemat `7b57f2f0bde6`; nie zmieniono metadanych active-release ani Compose.

## Przygotowanie i maintenance

- Ten sam przetestowany operator: digest
  `fad69aba5550c98c82bb57f2fc1f67deb85a9b7089f43b1e4e781c2b927e7326`.
  Zachowane gate 1722 backend / 493 frontend / lint / types oraz próba na realnej
  odtworzonej kopii i poprawka jednego Important z review (7 RED→GREEN).
- Potwierdzono zgodność runtime, obrazów, owner/op/input/target i wszystkich
  fingerprintów referencji z zaakceptowanym preflight. Zapisano oryginalny nginx,
  konfiguracje i ID kontenerów aplikacji, usług danych oraz aktywne metadane.
- Blokada 503 przeszła test syntax/HTTP w izolowanym kontenerze tego samego obrazu
  frontendu. Produkcyjny frontend zwracał503, bez dodatkowego bypassu lub portów.
  Backend wyłącznie na sieci wewnętrznej, Caddy bez dostępu do sieci backendu.
- Brak przyjętych żądań/aktywnych transakcji i zadań dokumentów/receipt/suggestions/
  rules; Redis queue/in-progress0. Same finished-cron dedup pozostawiono nietknięte.
  Backend i worker zatrzymano łagodnie pełną listą base+prod+aktywny versioned Compose;
  ponowna kontrola po zatrzymaniu potwierdziła brak pracy. Drain nie był potrzebny.

## Backup i wykonanie

- Pod fence wykonano świeży zaszyfrowany backup **`0c121fec`**. Guarded restore
  do własnej nowej loopback bazy `category_tree_prod_20261106_restore` potwierdził
  checksumy dump/uploadów, schemat/head i invariant księgi. Produkcji nie odtwarzano,
  nie wykonywano na niej migracji, DROP, DELETE lub zmiany oryginalnych dokumentów.
- Zapisano końcowe owner/global/foreign-owner fingerprinty finansów i polityk,
  bez czytania haseł lub tokenów sesji. Hashe uploadów również zachowano.
- Oddzielna zgoda `category_tree_apply_v1` wiązała aktualny preflight, request,
  owner/op/input/operator/runtime/schema/target oraz świeże backup/restore/fence
  i poświadczenie zgodności wcześniejszej rzeczywistej próby. Nie zastępowała jej
  dawna zgoda projektu lub planu.
- **Dokładnie jeden produkcyjny APPLY**, SERIALIZABLE, lock Actual→tree,
  istniejące serwisy domenowe, jeden COMMIT. CLIexit0, READ ONLY verify=`applied`.
  Nie wykonywano replayAPPLY na produkcji ani ponowienia/nowego UUID.

## Wynik DB — PASS

| Kontrola | Wynik |
|---|---:|
| Wszystkie kategorie | 79 |
| Expense / income | 73 / 6 |
| Zachowane oryginalne ID | 65 |
| Oryginalne wiersze bez mutacji | 35 |
| Zaktualizowane / nowe wiersze | 30 / 14 |
| Audyty create / update / batch | 14 / 30 / 1 |
| Trwały receipt tej operacji | 1 |

Dokładne ścieżki i maksymalnie dwa poziomy zgodne z zatwierdzonym pakietem.
Wszystkie HOLD/KEEP zachowane. Osiem dziedziczonych zmian ścieżek nie wywołało
sztucznych aktualizacji dzieci. Nie zmieniono typu, sourceActual lub aktywności.

Kwoty, waluty, kursy, daty, postings, salda, konta, budżety, harmonogramy,
dokumenty/alokacje, mapowania Actual i pozostałe referencje pozostały identyczne.
Kontrole owner i global/foreign-owner oraz polityk AI/hashów oryginalnych plików PASS.
Invariant księgi bez naruszeń. Nie utworzono markerów, reguł, zgód AI lub kont pożyczek;
nie uruchomiono historii, importu lub modelu.

Zmiana grup/nazw wpływa na prezentację dawnych raportów i skład grup — nie oznacza
identycznych sum per grupa. Import Actual pozostaje zakończony; guard i mapowania
niezmienione. Dawny reimport może bezpiecznie odmówić konfliktu.

## Przywrócenie dostępności — PASS

- Uruchomiono te same kontenery backendu/workera, bez odtwarzania frontendu.
  ID/obrazy/config/mounts aplikacji i usług danych bez zmian; health wewnętrzny200,
  anonimowy endpoint401 i receipt READ ONLY `applied` przed otwarciem.
- Przywrócono zapisany nginx bajtowo, `nginx -t` i reload. Pierwszy natychmiastowy
  publiczny probe po reload trafił jeszcze na503; log potwierdził przejście503→200.
  Świeża kontrola bez dodatkowego restartu, zmiany config lub APPLY potwierdziła
  HTTPS200 / health200 / anonymous401. Wynik początkowej próby nie został ukryty.
- Końcowy READ ONLY receipt nadal `applied`, durablejobs0/Redisqueue0/in-progress0,
  brak błędów w logach backend/worker/frontend, aktywne metadane bajtowo niezmienione.
- Nie podszywano się pod sesję użytkownika. Zalogowany odbiór UI pozostaje do
  wykonania prawdziwą sesją/manualnie; nie jest zastąpiony publicznym smoke.

Prywatne dowody i receipt/verify/backup/restore/public outcome:
`/opt/finanse/webapp/category-operations/2026-11-06/production-execution/`.
Pierwotne request/acceptance z `production_apply_approved=false` są historyczne;
nie nadpisywano ich. Aktualny wynik jest w DBreceipt i `production-outcome.json`.
Bez merge/push/deploy, napraw HOLD lub automatycznego cofania danych.
