# Dokumenty → szkice finansowe: odbiór lokalny

Data: 2026-11-17. Zakres: lokalny worktree; **nie jest to odbiór produkcyjny**.
Plan/spec: `docs/superpowers/{plans,specs}/2026-11-17-document-auto-finance-drafts*`.
Kod: `b33b99c` (modele/status), `4848a84` (orkiestracja),
`3c5ea2d` (UI oraz poprawka parsera hintów tekstowych).

## Zachowanie

- Nowy upload atomowo tworzy jeden intent. Duplikat nie adoptuje starego dokumentu.
- Kompletny odczyt pojedynczej faktury/paragonu → draft przez prepare_bill.
  Źródło istniejącej faktury ma pierwszeństwo, bez nadpisywania ręcznych danych.
- Odrębny dispatcher PostgreSQL→Redis. Blokada dokument→intent, skip_locked,
  receipt ze stałym kluczem; rollback nie wymaga ponawiania płatnego odczytu.
- Kwota/waluta NULL, declaration unknown. Brak zatwierdzania, transakcji,
  postings, płatności, Inbox/Today lub historycznego reprocessingu.
- Katalog wyłącznie aktywnych expense ownera; aliasy i ścieżki z limitami.
  Sugestia w tym samym wywołaniu rozpoznania; ponowna walidacja po sieci.
  Nieznany alias/zmieniony katalog → brak kategorii, nie nowa kategoria.
- Odczyt i Finanse są niezależne. Link pochodzi z faktycznego powiązania,
  szkic otwiera przegląd źródła/przypiętej rewizji. Ręczny wybór/clear
  kategorii ma pierwszeństwo przed późnymi wynikami.
- Starszy dokument można jawnie sprawdzić i przygotować przez istniejącą akcję
  formularza; samo GET nie zapisuje danych ani nie uruchamia AI.

## Weryfikacja

- TDD: domena23, adapter4, pipeline3, przypięcie rewizji2, UI5, notice1,
  actor cache1 i tekstowe hinty2 obserwowane RED→GREEN.
- `run-unit.sh tests/test_documents -m 'not integration'`: **424 passed,
  137 deselected**. Namespace bez sieci, syntetyczne sekret/DB URL i dane;
  fixtures rzeczywistego PostgreSQL nie uruchamiane.
- Kanoniczne `/lint`, `/typecheck`, `/test` z bieżącego worktree przez ich
  bloki `.opencode/command`: Ruff/ESLint PASS; mypy220/tsc PASS; backend
  collection PASS; **719 Vitest / 115 plików PASS**.
- Dodatkowe focused UI/API:76PASS; frontend `npm run build` PASS.
- Nowe integracyjne scenariusze dla CI: replay/concurrent delivery, draft bez
  ledger writes, niekompletny→nowa rewizja, owner-scoped projekcja. Nie udajemy,
  że kolekcja testów jest ich wykonaniem.
- Świeży readonly review całego zakresu b5fbc5e..3c5ea2d: **0 Critical,
  0 Important**. Zgłoszona nieaktualna dokumentacja etapu1 uzupełniona
  zgodnie z istniejącym Task4, nie odłożona jako niezrealizowany zakres.
- Naprawiono testowy teardown TransactionCategorization: najpierw unmount,
  potem reset klienta/mocków/auth; poprzednio4AggregateError na rzeczywistych
  żądaniach jsdom, po naprawie9PASS bez tych diagnostyk.
- Ostrzeżenia: zastana deprecjacja passlib/crypt; build chunk >500kB.
- Końcowy powtórny odbiór po naprawie teardownu:719Vitest/115plików w57.50s
  bez AggregateError;424offline w35.40s; build7.15s, diff--check PASS.
  Brak odłożonych uwag kodowych Minor.

## Rozstrzygnięcia wykonawcze

1. Katalog w istniejącym wywołaniu rozpoznania, nie drugi model/job.
   Koszt: więcej tokenów wejścia i konieczność nowej aktywacji polityki Vision.
2. Nie uruchamiać produkcyjnego `/migration` w lokalnym odbiorze.
   Addytywna migracja `a6e52f41c9d0` po `efaf78432563` bez backfillu została
   sprawdzona statycznie/offline. Koszt: realny upgrade/retencja nadal do odbioru.
3. Rozszerzyć klucze cache bills/categories o owner/session, bo RED potwierdził
   widoczność danych poprzedniego właściciela. Koszt: dodatkowe pobranie po logowaniu.
4. Zakresy, których reviewer nie oceniał (PG/retencja, realny provider,
   Docker/runtime), pozostają niezweryfikowane zgodnie z zatwierdzonym spec.
   Koszt: blokują twierdzenie o gotowości wdrożenia, nie lokalną implementację.

## Przed wdrożeniem

Osobna zgoda na integrację/push i CI, rzeczywiste testy PostgreSQL oraz próbę
upgrade/retencji, potem migracja i runtime odbiór. Nie zmieniono produkcyjnych
polityk. Fingerprint Vision obejmuje nowy zakres danych: nie omijać wymaganej
reaktywacji. Nie przetwarzać masowo istniejących dokumentów.
