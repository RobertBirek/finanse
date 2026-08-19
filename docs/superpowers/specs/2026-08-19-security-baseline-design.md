# Security Baseline — Design

## Cel

Zamknąć najpilniejsze ryzyka audytu bez zmiany modelu domenowego: chronić
sekrety, dane finansowe i dokumenty przez odtwarzalne backupy, fail-fast
konfiguracji, sesje unieważnialne, CSRF, rate limiting oraz audyt operacji
bezpieczeństwa.

## Zakres

1. Produkcja bez poprawnego `SECRET_KEY` nie startuje; publiczna rejestracja
   jest wyłączona wyłącznie w produkcji.
2. Sesja jest losowym tokenem 256-bit przechowywanym tylko jako hash SHA-256 w
   PostgreSQL. Cookie `advisor_session` pozostaje HttpOnly, Secure w produkcji
   i SameSite=Strict. Login nie zwraca tokenu w JSON ani nie obsługuje Bearer
   JWT.
3. Każda mutacja oparta o cookie wymaga tokenu CSRF powiązanego z sesją oraz
   dozwolonego `Origin`.
4. Redis obsługuje limity loginu, Advisora i uploadu. Błąd Redis blokuje tylko
   auth i endpointy kosztowe, nie zwykłe odczyty aplikacji.
5. Każdy backup zawiera PostgreSQL, uploady i manifest; jest szyfrowany przez
   Restic i wysyłany do skonfigurowanego repozytorium offsite. Restore drill
   działa na izolowanym PostgreSQL i kontroluje księgę.
6. Login, logout, odrzucenie CSRF i rate-limit są audytowane bez sekretów,
   tokenów, haseł i surowych emaili.

## Model sesji

`sessions` otrzymuje unikalne `token_hash`, `csrf_token_hash`, `revoked_at` i
`last_seen_at`. Surowy token sesji i token CSRF powstają przez
`secrets.token_urlsafe(32)`. Tylko hash SHA-256 trafia do bazy. Backend
porównuje hashe przez `hmac.compare_digest`.

`POST /login` tworzy rekord `Session`, ustawia dwa cookie i zwraca `204`.
`POST /logout` oznacza bieżącą sesję jako unieważnioną oraz usuwa oba cookie.
`get_current_user` pobiera wyłącznie aktywną, nieprzeterminowaną i
nieunieważnioną sesję. Dotychczasowe JWT przestają być akceptowane.

## CSRF i Origin

Cookie `advisor_csrf` jest dostępne dla JavaScript, ma SameSite=Strict i tę
samą żywotność co sesja. Axios przesyła jego wartość w `X-CSRF-Token` przy
metodach mutujących. Middleware wymaga dla takich metod zgodności tokenu z
hashm sesji oraz originu z `CORS_ORIGINS`; `/auth/login` i `/auth/register`
wymagają tylko dozwolonego originu, ponieważ nie mają jeszcze sesji.

## Rate limiting

Limity są konfigurowane w środowisku. Klucze Redis nie przechowują surowego
emaila ani IP: identyfikator loginu używa hasha emaila, a klucz klienta używa
hasha IP. Skrypt Lua atomowo inkrementuje licznik i ustawia TTL. Odpowiedź
odrzucona ma `429` oraz `Retry-After`.

## Backup i restore

Skrypt backupu tworzy custom-format `pg_dump`, archiwum uploadów i manifest
z commit SHA/revision Alembic/checksumami, po czym wykonuje `restic backup` i
`restic forget --prune --keep-daily 7 --keep-weekly 4 --keep-monthly 6`.
Sekrety Restic pozostają poza repozytorium. Skrypt restore odtwarza snapshot
do izolowanej bazy, uruchamia migracje i sprawdza liczby rekordów, sumę ledgeru
oraz checksumy uploadów.

## Wdrożenie

Najpierw backup i restore drill. Migracja sesji jest additive. Następnie
deploy aplikacji, smoke test nowej sesji i CSRF, a na końcu rotacja sekretów.
Brak skonfigurowanego repozytorium Restic blokuje deploy, ale nie blokuje
przygotowania kodu i testów lokalnych.
