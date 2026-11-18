# Publikacja preflight V2 — rollout wstrzymany przez CI

## Zgoda i publikacja

Użytkownik polecił „wypchnij do main i wdróż”. Wypchnięto bez force
`0e9e73c55b88f9bc2bf760d9836b28044b993931` na main (fast-forward z5c37246),
potwierdzono osobnym ls-remote. Pozostałe worktree i stary hostcheckoutmain
pozostawiono bez zmian. Drzewa aplikacji/migracji/frontendu były identyczne
z wcześniej sprawdzonym39aceec; nie zastępuje to CI nowego SHA.

## Artefakty i zgoda administratora

Pierwsze pakowanie prawidłowo odmówiło systemstdlib zawierającego3symlinki.
Przygotowano prywatny runtime z tego samego Pythona3.12.3 i root-controlled
stdlib: regularne kopie, bez site/dist-packages i bez zmiany plików systemowych.
Nie instalowano pakietów ani nie osłabiano warunku no-symlinks.

Osobny reviewer ses_e129444fcffeIDZpwfjkwwMZ0S zweryfikował runtime,28members,
Git/code/pins oraz273pełne pary źródeł, w tym30exacttoolingpairs: bez uwag.
Administrator następnie wybrał **„Akceptuję hashe i preflight”** dla:

| Artefakt | SHA256 |
|---|---|
| Bundle | `1ffe108a622e005c9068346c1aa460f216c89426f838de57204f7bd33f6d1036` |
| Toolchain | `07605c56f282002fd1b28d7b14730caede6ffddf2a4a578219b516d0dbcbffd2` |
| Review scope | `a1d657115dcd3f85cfe617aea6fb10663e94758933b0eb8a972607a514202c91` |

Zgoda na readonly acceptance była **warunkowa: po zielonym CI**.
Receipt zapisano dopiero po tej odpowiedzi. Warunek nie został spełniony.
Pakiet/sourceproof dotyczy exact0e9e73c; zmiana candidate wymaga nowego proof
i akceptacji jego hasha, nie reinterpretacji starej zgody.

## CI44253508543 — FAILURE

https://github.com/RobertBirek/finanse/actions/runs/44253508543

- Backend static/inventory i7grup testowych SUCCESS.
- `ordinary-3`:1FAIL,
  `tests.test_ops.test_release_preflight_launcher.test_valid_bundle_verification_never_imports_checker`.
  Powód `bootstrap_parent_untrusted`: fixture używa rzeczywistego Pythona
  GitHubtoolcache, którego ancestors mogą być writable dla runnera/grupy.
  Guard produkcyjny odmówił prawidłowo; to błędne założenie fixture.
- Frontend zatrzymał się na `npm audit --audit-level=low`:10high raportów
  w łańcuchu picomatch. Lint/types/unit/build/browser w tym jobie nie ruszyły.
- Agregator prawidłowo odrzucił niepełny odbiór. Nie zwiększano timeoutów,
  nie wyłączano testów lub audytu i nie ponawiano CI bez poprawki.

Advisory GHSA-fc5q-39xc-vjpf (CVE-2026-112366), aktualizacja17XI2026,
podaje affected `<=4.0.7`, patched **None**. Registry18XI zwrócił latest4.0.7,
4.0.8E404. Lock ma nested4.0.5 i dwa4.0.7. Sugestia auditfix--force nie
jest dowodem bezpiecznej remediacji. Lokalna dodatkowa próba auditJSON
przekroczyła30s; nie uznano jej za PASS ani za pełny nowy raport.

## Wąska naprawa po zgodzie użytkownika

Użytkownik wybrał „Napraw fixture i przygotuj plan”. Nie zatwierdził zmiany
zależności. Regresja odtwarza writablehostedtoolcache i pozostawia guardowi
obowiązek odrzucenia pierwotnej ścieżki. RED: bootstrap_parent_untrusted.
Fixture przechowuje prywatną regularną kopię pliku Pythona wyłącznie do hashowania,
nigdy jej nie uruchamia. GREEN:24launcher testyPASS1.96s. Kod `ops` bez zmian.
Focused reviewer ses_e12716443ffe2R91cJBn6Uf87f:0Critical/0Important/0Minor;
potwierdził guard-preservation i wykonalność planu decyzyjnego, bez pytań blokujących.
Pełny lokalny odbiór poprawki:231offlinePASS138.42s,719Vitest, kanoniczne lint/
types/kolekcja backendu oraz Ruff/mypy8opsPASS. Produkcyjny kod i dependencylock
pozostają bez zmian. Nie deklarujemy naprawy frontendnpm audit lub zielonego CI.

Proponowany plan decyzji:
`docs/superpowers/plans/2026-11-18-picomatch-remediation-decision.md`.
Wprost pozwala zakończyć BLOCKED przy braku prawdziwej poprawki; nie wymyśla
wersji/forka i nie zmienia dependencylocka. Właściwy plan implementacji zależności
powstanie dopiero po wyborze i akceptacji konkretnego źródła remediacji.

## Stan produkcji i dowody

Nie wykonano targetpreflightu, build/deploy, nowego backup/restore, migracji,
policytransition ani wywołań AI. Readonly discovery obejmowało wyłącznie
zatwierdzone inventory, whitelist metadanych, PGinspect i fixedfiledockerCP.
Nie było query/exec/authchange ani nowego inventory z obserwacji.

Dowody root-only:
- `/tmp/opencode/preflight-publish-0e9e73c.9qfZE5y5/`: CIlogs/JUnit, RED/GREEN.
- `/tmp/opencode/preflight-artifacts-0e9e73c.sOpN8zYw/`: piny, runtime, raport,
  scope, receipt i progress. Nie publikować env lub pełnych konfiguracji.

Produkcja nadal na dotychczasowej wersji. Zielone testy lokalne nie zastępują
brakującego zielonego CI, akceptacji nowego scope ani dalszych bramek release.
