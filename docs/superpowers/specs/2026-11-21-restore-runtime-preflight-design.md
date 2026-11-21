# Kontrola zgodności narzędzia odtwarzania przed wydaniem

W wydaniach `8121512` i `db062d2` próba odtworzenia doszła do Alembic ze
starszym drzewem migracji, które nie znało schematu kopii. Kontrola ma wykryć
ten przypadek przed odtwarzaniem i przed decyzją o przełączeniu usług.

## Pierwszy zakres

Osobne narzędzie odczytowe dla operatora, nie nowy tryb checkera wydania.
Operator ustala, który zainstalowany skrypt faktycznie wywoła ścieżka
systemd → Make → restore oraz jaki przypięty runtime będzie używany po
wydaniu. Nie bierz tych informacji z ruchomego `main`, tagu obrazu lub z
domyślnej ścieżki. Dla każdej roli jest osobny wynik:

- `rehearsal`: runtime wybrany do próby i zatwierdzony docelowy head tej próby;
- `after_rollout`: runtime zaplanowany dla cyklicznego restore i oczekiwany
  head zgodny ze schematem po wydaniu.

Obie kontrole wykonuje się przed przełączeniem, dla dokładnego kandydata,
pełnego 64-znakowego ID kopii oraz przypiętych bajtów jej `manifest.json`.
Operator potwierdza pochodzenie manifestu z dokładnej kopii poza narzędziem.
Przy `app_only` oba heady mogą się pokrywać. Zmiana kopii, runtime'u, drzewa
migracji, kandydata lub oczekiwanego headu wymaga świeżego wyniku. Po późniejszej
aktywacji instalacji trzeba niezależnie sprawdzić, że rzeczywista ścieżka
systemd/Make używa zatwierdzonego runtime'u.

## Granica zaufania

Launcher kontroli i jego moduł polityki pochodzą z osobno zatwierdzonego
checkoutu narzędziowego, nigdy z kandydata lub sprawdzanego runtime'u. Operator
podaje niezależnie zatwierdzone SHA-256 obu manifestów. Manifest runtime'u
wiąże pełny SHA źródeł, absolutny katalog instalacji i dokładne bajty skryptu
restore, entrypointu Alembic, konfiguracji, `env.py` i całego drzewa wersji.
W tym samym zatwierdzonym manifeście operator przypina fazę, SHA kandydata,
head oraz pełny ID i hash manifestu kopii; same argumenty nie dowodzą zgody.
Manifest nie potwierdza samodzielnie pochodzenia całego Pythona lub jego
zależności; przypięcie i instalacja runtime'u pozostają osobną bramką.

Źródła migracji analizuje istniejący parser AST dla liniowego grafu. Nie
importujemy ani nie wykonujemy migracji i nie wywołujemy Alembic. Dopuszczamy
wyłącznie standardowy układ `backend/migrations/versions` bez dodatkowych
lokalizacji i rekurencyjnego discovery; inny układ to STOP, nie próba
odgadnięcia ścieżki. Schemat z manifestu musi leżeć na liniowym grafie
kończącym się dokładnie na oczekiwanym headzie, także gdy schemat kopii jest
już tym headem. Stare drzewo, błędny head, nieznana rewizja, drift, niepełne
wejścia lub nieobsługiwany graf powodują odmowę.

Wynik mówi wyłącznie o zgodności grafu i przypiętych plików. Nie daje zgody na
operację, nie dowodzi odtwarzalności kopii, pochodzenia obrazu ani zgodności
danych. Nadal trzeba odtworzyć tę samą kopię na izolowanym celu i odnotować
wynik. Kontrola niczego nie pobiera ani nie zmienia: bez Restic, DB, Dockera,
sieci, wykonania skryptów runtime'u i automatycznego zmieniania pinu.
Wymaganie publikacji `verified-live` i instalacja na serwerze są oddzielnymi
etapami, poza tym zakresem.
