# Całe AI Personal Advisor na OpenAI

## Zatwierdzony zakres

Użytkownik polecił wdrożyć na produkcję bez pilotażu, następnie „przenieś cały AI
na modele od openAI”. Zatwierdził dobór: `gpt-6.1-sol` dla doradcy i jego narzędzi,
`gpt-6.1-terra` dla ekstrakcji tekstu i obrazu. Implementacja, testy, backup i wydanie
są częścią przyjętego planu. Bez ponownego uruchamiania zakończonego planu vision.

## Zachowanie i granice

- Wszystkie generatywne wywołania aplikacji korzystają z OpenAI; brak fallbacku
  do DeepSeek i brak odziedziczonego klucza DeepSeek. Nie dotyczy to innych aplikacji VPS.
- Modele, limity i klucze są ustawieniami środowiska, nie stałymi w serwisach.
- Doradca zachowuje historię PostgreSQL i obecne tool_calls/ToolExecution/API.
  Tylko zarejestrowane narzędzia, nie dowolny SQL; mutacje nadal pending_confirmation.
- Nowe modele wymagają Responses dla tool calling. `store=false`, stateless replay
  pełnej historii aplikacyjnej; żadnego hosted tool, agenta lub Conversations API.
- Ekstrakcja zachowuje obecne walidatory, strict vision schema i Decimal; odmowa,
  incomplete/failed lub obce output types nie mogą być zaakceptowane jako wynik.
- Ręczne OCR nadal pozostaje lokalne i nie łączy się z AI. Nie przetwarzamy wstecz
  starych dokumentów, duplikatów ani prywatnych zdjęć dostarczonych wcześniej.
- Oryginały prywatne i niezmienione; vision otrzymuje jedynie obecną pochodną JPEG.
- Nie zmieniać ledger, sald, płatności, automatyki zatwierdzania ani modelu danych.
- Osobne ustawienia vision i jawna polityka/epoka pozostają obowiązkowe; nie ma
  ukrytego fallbacku na klucz lub model doradcy.

## Klucz i dane

Projektowy klucz OpenAI jest w `/docker/finanse/.env` (potwierdzono jedynie obecność
po zatwierdzeniu modeli). Nigdy nie wypisywać kluczy, odpowiedzi zawierających dane
lub pełnego Compose/env. Nie używać poświadczeń OpenCode/innych aplikacji.
OpenAI API domyślnie nie trenuje na danych; abuse logs mogą być zachowane do30dni.
`store=false` nie obiecuje Zero Data Retention.

## Wybory implementacyjne koordynatora

- Wspólny niewielki klient Responses; oddzielne adaptery domenowe. Minimalna zmiana
  schematu wire, bez nowej warstwy agentowej i bez migracji DB dla tego przyrostu.
- SDK `openai==2.54.0`: najnowsza znaleziona stabilna linia2 zgodna z istniejącym
  httpx0.27; linia3 wymaga httpx2. Nowy runtime musi być rzeczywiście zbudowany
  i sprawdzony, nie wolno podszywać starego runtime pod nowy requirements revision.
- Sol reasoning low; Terra none. Budżety wyjścia i timeouty konfigurowalne;
  usuwamy niezgodne stare temperature/max_tokens z wywołań Responses.
- Krótki live smoke tylko na syntetycznym tekście/obrazie i fikcyjnym wyniku narzędzia;
  nie pobiera danych użytkownika ani nie księguje niczego na produkcji.

## Wydanie

Pełny gate i niezależny review przyrostu przed spójnym backend/worker/frontend.
Backup/restore i próba wymaganych migracji c2→7f8→92 na izolowanej kopii, rollback
do9db255b z zachowaniem addytywnego schematu. Po wydaniu HTTPS/assets/auth/health,
wersje obrazów, brak host mountu /app, niezmienne dane historyczne i oryginały,
bez restartów usług danych. Aktywacja vision przez istniejącą CLI z expected_epoch.
