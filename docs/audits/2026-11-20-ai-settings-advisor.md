# Audyt AI i pierwszy przyrost ustawień OpenAI

## Stan wykryty

| Funkcja | Konfiguracja | Użycie |
| --- | --- | --- |
| Doradca | Wspólne `OPENAI_API_KEY` i `LLM_MODEL`; instrukcje w kodzie | Brak agregacji tokenów i czasu |
| Ekstrakcja tekstu | Wspólny klucz, osobny model oraz limit wejścia | Bez wspólnego raportu |
| Vision dokumentów | Osobne poświadczenia, epoka, limity wywołań i ponowień | Limit utrzymywany przez worker |
| Pozycje paragonu | Oddzielna polityka i rezerwacja przed wysłaniem | Częściowe pomiary tokenów |
| Sugestie kategorii | Oddzielna polityka, bramka danych wysyłanych i rezerwacja | Częściowe pomiary tokenów |

Doradca korzystał z pełnej historii i dla błędów dostawcy potrafił zwracać
komunikat jako poprawną wiadomość. Dotychczasowe działanie mutujące wymagało
potwierdzenia według rejestru narzędzi, ale nie używało modułu polityki.

## Zakres tego przyrostu

`/settings/ai` obsługuje tylko Doradcę. Klucz jest zapisywany jako zaszyfrowany
blob przypisany do właściciela i nie jest zwracany przez API. Zapis klucza
wymaga jawnej konfiguracji sekretu szyfrowania. Bez własnego klucza stosowany
jest domyślny model serwera lub model z listy dopuszczeń; awaria odczytu
własnego klucza nie oznacza cichego przełączenia na klucz serwera.

Test syntetyczny wywołuje OpenAI z zapisanym modelem i wymusza wywołanie
fikcyjnej funkcji. Nie pobiera historii, nie wykonuje żadnego narzędzia
aplikacji i może zużyć tokeny. Własne instrukcje są wersjonowane oddzielnie
od nieedytowalnych reguł. Zmiana konfiguracji Doradcy nie zmienia reguł
przetwarzania w innych modułach.

Statystyki obejmują liczbę wywołań, błędy, średni czas i znane tokeny
Doradcy oraz testów połączenia. Nie rekonstruujemy danych historycznych
ani nie szacujemy kosztu bez zaufanego cennika. Statystyki mają charakter
informacyjny, nie służą do egzekwowania limitów ani rozliczeń.

## Przygotowanie środowiska

- Migracja `c435e5526e23` tworzy wyłącznie trzy nowe tabele. Należy przetestować
  ją na izolowanym PostgreSQL przed wdrożeniem. Zmiany aplikacji i migrację
  wdrażać w kontrolowanej kolejności po osobnej akceptacji.
- `ADVISOR_CREDENTIAL_ENCRYPTION_KEY`: 32 losowe bajty zakodowane Base64URL.
  Sekret należy przekazać wyłącznie backendowi poza repozytorium i backupami
  bazy. Utrata lub podmiana sekretu bez migracji szyfrogramów powoduje
  niedostępność istniejących własnych kluczy; odzyskać poprzedni sekret
  albo ręcznie zastąpić klucze. Automatyczna rotacja sekretu nie jest dostępna.
- `ADVISOR_ALLOWED_SERVER_MODELS`: opcjonalna lista JSON identyfikatorów
  dopuszczonych przy użyciu klucza serwera. Model z `LLM_MODEL` jest domyślny.
- Po wdrożeniu tester może zweryfikować połączenie z własnym kluczem przez UI;
  w tej pracy wszystkie odpowiedzi OpenAI są atrapami.

## Kolejne przyrosty

Ekstrakcja, vision, pozycje paragonu i kategoryzacja wymagają osobnych
adapterów konfiguracji, wersji instrukcji i statystyk. W kolejce należy
wiązać wywołanie z właścicielem, wersją konfiguracji i stanem istniejącej
polityki; nie wolno wyłączać limitów ani żądań zatwierdzenia, by umożliwić
ogólny panel ustawień. Dalsza implementacja nie jest częścią tego przyrostu.
