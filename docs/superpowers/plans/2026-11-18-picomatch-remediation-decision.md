# Picomatch Remediation Decision Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Wybrać weryfikowalne, konkretne usunięcie podatności bez omijania audytu; przy braku rozwiązania zakończyć BLOCKED.

**Architecture:** To plan rozpoznania i decyzji, nie autoryzacja instalacji.
Oddziela naprawioną fixture od nierozwiązanej podatności. Nie rozpoczyna zmiany
zależności, dopóki administrator nie zatwierdzi dokładnego źródła remediacji.

**Tech Stack:** Istniejący npm/package-lock, GitHub advisory, Vite/Vitest/ESLint; dokumentacja, bez nowego runtime.

**Spec:** `docs/superpowers/specs/2026-11-18-picomatch-remediation-design.md` — propozycja do akceptacji.

## Global Constraints

- „Nie będę obniżał progu audytu, wyłączał bramek ani używał npm audit fix --force.”
- „Nie instalować ani nie zmieniać zależności bez zatwierdzenia konkretnego rozwiązania.”
- „Brak poprawionej wersji nie jest zgodą na wdrożenie z czerwonym CI.”
- „Naprawa fixture nie może osłabić produkcyjnego sprawdzania ancestors/hash/owner/mode.”
- „Nowy kandydat wymaga pełnego CI i nowego exact scope proof do akceptacji.”

## Review Focus

1. Transitive picomatch4.0.5 i4.0.7: żaden łańcuch nie może zostać pominięty — Task1, porównanie wszystkich lockpaths.
2. Advisory „None”/registry E404: brak wersji daje BLOCKED, nie automatyczny downgrade — Task2.
3. Timeout/niepełny auditJSON: brak raportu nie oznacza0vulns — Task1.
4. Fork/rename/metadane wersji: zielony skaner bez rzeczywistej naprawy jest odmową — Task2.
5. Dependency-only zmienia build/candidate mimo tego samego kodu aplikacji — Task3, CI/build/scope freshness.

---

## Mapa plików i granica wykonania

- Create `docs/audits/2026-11-18-picomatch-remediation-evidence.md`: datowane źródła, kompletny lockgraph, registry/advisory, wynik decyzji.
- Update spec powyżej dopiero po wybraniu konkretnego źródła naprawy.
- W tym planie **nie zmieniać** frontend/package.json, package-lock.json,
  node_modules, workflowów, buildów lub produkcji.
- Kolejny plan implementacji ma wskazać dokładne nowe wersje/integrity, pliki,
  regresję ReDoS oraz zgodność globów. Nie są znane dzisiaj; ich wymyślenie
  nie jest dopuszczalnym krokiem wykonawczym.

### Task 1: Utrwalić kompletną diagnozę

**Files:** Create audit evidence; read `frontend/package-lock.json`, CI44253508543.
**Interfaces:** Produces datowany raport każdego lockpath/version/advisory
i statusów poleceń (`success`, `failure`, `timeout`), bez modyfikacji locka.

- [ ] Utrwalić hash locka, pełny wynik CIfrontend oraz wszystkie wpisy picomatch/fdir/tinyglobby z locka.
  Asercje: obejmuje nested4.0.5 i dwa4.0.7; nie ogranicza się do dependencyroot.
- [ ] Ponownie odczytać advisory i `npm view picomatch version dist-tags --json`
  oraz kandydacką wersję tylko jeśli została rzeczywiście wskazana upstream.
  Expected dziś: latest4.0.7, patchedNone. E404/timeout zapisać jako brak dowodu.
- [ ] Jeśli ponawiany jest `npm audit --json`, użyć jawnego timeout60s i prywatnego
  outputu; rozróżnić exit1 z poprawnym raportem od timeout/błędu sieci.
  Nie wykonywać npm install/ci/auditfix.
- [ ] Sprawdzić spójność lockpaths i źródeł; commit dokumentacyjny po kanonicznych
  lint/typecheck/test i diffcheck. Dokumentacja nie ma sztucznego testu RED.

### Task 2: Bramka konkretnego źródła naprawy

**Files:** Modify audit evidence i proponowaną spec.
**Interfaces:** Consumes Task1; produces albo **BLOCKED_NO_REMEDIATION**, albo
propozycję dokładnego package/version/integrity/upstreamfix/testscope do akceptacji.

- [ ] Preferować utrzymywaną poprawkę upstream. Porównać konkretne źródła i advisory,
  nie wyłącznie numer wersji lub sugestię skanera.
- [ ] Jeżeli nadal brak poprawki: zapisać BLOCKED_NO_REMEDIATION i **zakończyć**.
  Nie wybierać starej wersji, rename/forka ani wyjątku audytu w zastępstwie.
- [ ] Jeśli istnieje konkretna naprawa: opisać jej źródło i integralność, wszystkie
  dotknięte łańcuchy, wymagane Node/Vite/Vitest/ESLint compatibility oraz zakres
  testu ReDoS w oddzielnym procesie z twardym timeoutem. Nie wykonywać payloadu
  ReDoS w głównym workerze/test runnerze.
- [ ] Uzyskać zgodę administratora na dokładną propozycję przed instalacją.
  Alternatywna wymiana całego glob/toolchain wymaga własnego projektu i akceptacji,
  nie jest domyślnym fallbackiem tego planu.

### Task 3: Handoff bez utraty bramek

**Files:** Dalszy, osobno zatwierdzany plan implementacji i status TASKS/JOURNAL.
**Interfaces:** Consumes wyłącznie zaakceptowane źródło Task2. Przy BLOCKED nie wykonuje się.

- [ ] Napisać osobny plan RED→GREEN: procesowa regresja ReDoS,
  kompatybilność globów ignorowanych testów/assets/dotfiles i wszystkich łańcuchów;
  istniejący auditthreshold ma zostać bez zmian. Plan podaje konkretne wersje,
  integrity i dokładne pliki dopiero po ich ustaleniu.
- [ ] W tym kolejnym planie wymagać clean npmci, audytu, lint/types, całego Vitest,
  Vitebuild, Playwright, backendregresji/kolekcji i świeżego review. Brak
  dowolnego wyniku oznacza brak odbioru.
- [ ] Wymagać CI dokładnego nowego SHA oraz nowego scopeproof dla candidate;
  zaakceptowane wcześniej0e9e73cproof nie przenosi się na innycommit.
- [ ] Dopiero osobne przyjęcie hashy pozwala wrócić do readonly preflightu,
  backup/restore, rollbacku, migracji i rollout. Ten plan nie wykonuje deployu.

## Self-review

Pokrycie spec: pełny graph/timeouty→Task1; brak wersji/rename/downgrade→Task2;
auditthreshold/RED/ReDoS/compat/newSHA→Task3. Interfejsy są dokumentacyjne,
bez nieznanych funkcji lub nieistniejącego numeru poprawki. Wszystkie5focus
mają jawne sprawdzenie. Na dziś plan może uczciwie zakończyć się BLOCKED;
nie jest deklaracją, że npm audit da się już naprawić zwykłą aktualizacją.
