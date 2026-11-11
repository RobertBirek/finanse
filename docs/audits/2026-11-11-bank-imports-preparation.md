# Importery A+B — faza przygotowania P, NO-GO

Data: 2026-11-11. Plan: `docs/superpowers/plans/2026-11-11-bank-imports-release.md`.
Użytkownik zatwierdził P („tak”), nie wdrożenie D ani rzeczywisty import.

## Wynik

**Nie wydawać `c3069487fd8e7c23b8a0423883516768b98005d4`.** Izolowany Nginx
odrzuca nowy upload 2 MiB kodem **413**, zamiast przekazać go do upstream204.
Dotyczy `/api/finance/imports/{batch_id}/sources`, z i bez końcowego slash.

Przyczyna: `frontend/nginx.conf` ma wyjątek `client_max_body_size 21m` wyłącznie
dla `/api/documents/upload/?$`. Nowa ścieżka trafia do ogólnego `/api/`, bez
tego wyjątku. Nie jest to błąd parsera ani dowód odrzucenia przez FastAPI:
w probe API zastąpiono lokalnym stubem204, nie uruchamiano aplikacji/DB/workera.

## Co wykonano

| Bramka | Wynik |
|---|---|
| Zgoda P i wymagane hostdocs | Potwierdzone; bez zgody D |
| Fetch i FF-compatibility | origin/main nadal `e3c906f`; przodek kandydata |
| Freeze kodu/dist | 747 hashów źródeł +15 plików dist zgodnych z odbiorem B6 |
| Guardy operatora | RED: brak modułu → GREEN:9 testów PASS; uszkodzony SHA odrzucony |
| Pakiet dokładnego c306948 | Przygotowany istniejącym `ops/prepare_release.py`;445 plików źródeł zgodnych z Git |
| Backend/worker/frontend build | Wszystkie3 PASS, `--network=none --pull=false`, stare runtime7801 |
| Pełny Compose | Base+prod+active7801+candidate różni się tylko image/build; users10001:10001 |
| Ingress |3 metody testowe:2PASS/1FAIL,2 nieudane subtesty;10 żądań HTTP |
| Offline import verifier | **Nie uruchomiono**, brak proof i brak akceptacji obrazów |
| Backup/restore/klony/migracje | **Nie rozpoczęto** — STOP po ingress |
| Merge/push/maintenance/deploy/import | **Nie wykonano** |

### Dokładny kontrakt ingress

| Ścieżka, oba warianty slash |2 MiB |21 MiB+1 bajt |
|---|---|---|
| Dotychczasowy upload dokumentów |204 PASS |413 PASS |
| Nowy upload importera |**413 FAIL** |413 PASS |
| Zwykłe `/api/health`, `/api/finance/accounts` |413 PASS |Nie wymagano |

Użyto exact candidate frontend image oraz backend image jako syntetycznego klienta
HTTP. Jedyna adaptacja konfiguracji to zamiana upstream na loopback i lokalny
stub204. Wyjątki body-size pozostały bez zmian. Nginx działał z `--network none`,
klient wyłącznie w jego namespace, bez publikowanych portów i połączenia do produkcji.
Nie używano prywatnych plików, danych logowania ani oryginalnych uploads.

### Zbudowane obrazy — niezatwierdzone do wdrożenia

- Backend: `sha256:1ac810d2f2aa4272c89f2794cf735c0489c37262952bdd05a4648c1a2862151d`.
- Worker: `sha256:e423792ad68de77ef95d9aca2578fd23bbad14294a766b593078d7c8cce5a628`.
- Frontend: `sha256:715a6d3bf1a8d9a1af70a5491717336c3dbb22a2815df94b509eb3acbe3ce16f`.

## Dodatkowy konflikt procedury — nadal do rozstrzygnięcia

Istniejący `ops/verify_release.py` w `finally` wywołuje `docker rm -f` nawet po
sukcesie, co koliduje z zatwierdzonym zakazem force. Nie uruchomiono go i nie
zastąpiono nieudokumentowanym verifierem. Niezależny ingressprobe przesunięto przed
ten krok; jego failure zakończył P. Przed przyszłym wznowieniem potrzebna będzie
jawna decyzja o bezpiecznej obsłudze cleanup verifiera albo dokładnym wyjątku.

## Stan końcowy i dowody

- Produkcja nadal7801ba5/schema739144d5eaef/62tabele. Końcowy read-only check
  porównał ID, obrazy, Config, HostConfig, starttime i restarty wszystkich6usług,
  aktywne metadata, pliki Compose i hash env z inventory: bez zmian.
- Oba własne kontenery probe usunięte po kontroli exactID/label/network/noports
  i zatrzymaniu; bez force/prune. Nie utworzono PG, wolumenów lub bazy restore.
- Pakiet `/opt/finanse/webapp/releases/bank-imports-c306948-O0UIJYQN/` oraz lokalne
  obrazy pozostają jako **NO-GO**, nie są aktywne. Stare obrazy/override nietknięte.
- Prywatne dowody: `/tmp/opencode/bank-imports-release-c306948-O0UIJYQN/` (0700).
  `final-proof.json`, `ingress-proof.json`, `ingress-cleanup-proof.json`, log RED,
  guardy/testy i manifesty. Surowe inventory/Compose/env nie trafiają do Git.
- Nie powtarzano pełnych2300backend/617frontend/183E2E; potwierdzono hashami
  zgodność wcześniejszego odbioru. Dzisiejszy wynik ingress jest RED, nie GREEN.

### Niezależny review zamknięcia NO-GO

Jeden reviewer read-only potwierdził test ingress, cleanup i uczciwe rozróżnienie
wykonanych/pominiętych bramek; ponownie uruchomił9puretestsPASS. Brak Critical/Minor.
**Important przed przyszłym wznowieniem:** `select_rollback` sam sprawdza wyłącznie
format oldimageIDs; kontrakt wymaga oddzielnego `check_freeze`. Przyszły workflow
musi jawnie udowodnić powiązanie ID z zaufanym inventory, nie używać samego
`select_rollback` jako upoważnienia. To nie jest zgoda na obecny rollback i nie
zmienia NO-GO. Uwagi nie uznano za naprawione; pozostaje blokadą wznowienia.

Archiwum22sanityzowanych dowodów w katalogu `R/evidence/preparation-no-go.tar.gz`,
SHA-256 `2f2d58ddf787a63a71ece67003e81133f2f824c68b435e337f68cb17453caaf1`.
Lista allowlist/manifest sprawdzona, surowe privateinventory/Compose wykluczone;
skan rzeczywistych wartości sekretów PASS. Późniejszy review zapisano oddzielnie
w `R/evidence/review.json`, poza niezmienianym archiwum.

Decyzje proceduralne: użyto istniejącego worktree i ważnych hashów odbioru zamiast
powtarzania pełnej suite (drift unieważnia reuse); ujednolicono nagłówki Task 1
dla natywnego harnessu (bez zmiany zakresu); ingress przesunięto przed verifier
(offline imports pozostają nieudowodnione). Zatrzymanie P nie zamyka tych bramek.

## Następny krok

Osobna decyzja o wąskiej poprawce Nginx i trwałym teście proxy nowej ścieżki
(TDD), bez globalnego zwiększania limitu `/api/`. Nowe SHA wymaga nowego freeze,
buildów i odnowienia właściwych bramek P. Wdrożenie D i pilotaż prawdziwego pliku
nadal wymagają osobnych zgód. Nie wolno oznaczać P jako ukończonego.
