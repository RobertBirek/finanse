# Audyt AI i ustawienia OpenAI

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

`/settings/ai` obsługuje pięć funkcji niezależnie. Klucz jest zapisywany jako
szyfrogram związany z właścicielem i funkcją oraz nie jest zwracany przez API. Zapis klucza
wymaga jawnej konfiguracji sekretu szyfrowania. Bez własnego klucza stosowany
jest domyślny model serwera lub model z listy dopuszczeń; awaria odczytu
własnego klucza nie oznacza cichego przełączenia na klucz serwera.

Test z zapisanym modelem używa fikcyjnej funkcji dla Doradcy, danych testowych
dla tekstu i kategorii oraz obrazu wygenerowanego w pamięci dla zdjęć i paragonów.
Nie pobiera historii ani dokumentów i może zużyć tokeny. Własne instrukcje są
wersjonowane oddzielnie od nieedytowalnych reguł i schematów odpowiedzi.

Statystyki obejmują liczbę wywołań, błędy, średni czas i znane tokeny
każdej funkcji oraz oddzielnie testów połączenia. Nie rekonstruujemy danych historycznych
ani nie szacujemy kosztu bez zaufanego cennika. Statystyki mają charakter
informacyjny, nie służą do egzekwowania limitów ani rozliczeń.

## Przygotowanie środowiska

- `c435e5526e23` tworzy trzy tabele, a `e5a46dc32772` izoluje ustawienia,
  wersje i użycie po funkcji. Zmiany weryfikować na izolowanym PostgreSQL.
  Rollback aplikacyjny na tym schemacie powinien wrócić do wersji sprzed obu
  przyrostów (nie do pośredniego commita `b590040`). Cofanie migracji nie
  usuwa zapisanych konfiguracji i danych pomiarowych bez oddzielnego planu.
- `ADVISOR_CREDENTIAL_ENCRYPTION_KEY`: 32 losowe bajty zakodowane Base64URL.
  Sekret należy przekazać wyłącznie backendowi poza repozytorium i backupami
  bazy. Utrata lub podmiana sekretu bez migracji szyfrogramów powoduje
  niedostępność istniejących własnych kluczy; odzyskać poprzedni sekret
  albo ręcznie zastąpić klucze. Automatyczna rotacja sekretu nie jest dostępna.
- `ADVISOR_ALLOWED_SERVER_MODELS`: opcjonalna lista JSON identyfikatorów
  dopuszczonych przy użyciu klucza serwera. Model z `LLM_MODEL` jest domyślny.
- Po wdrożeniu tester może zweryfikować połączenie z własnym kluczem przez UI;
  w tej pracy wszystkie odpowiedzi OpenAI są atrapami.

## Reguły funkcji

Panel nie nadaje zgody na wysyłkę ani nie włącza globalnie wyłączonej funkcji.
Kategoryzacja po zmianie ustawień wymaga ponownej zgody; odczyt pozycji
paragonu nadal wymaga podglądu i potwierdzenia konkretnego odczytu. Starszy
podgląd nie może autoryzować zaktualizowanego modelu. Opublikowanie wyniku
po zmianie konfiguracji podlega kontroli wersji; wywołania już dopuszczonego
do wysłania nie da się wycofać. OCR lokalny pozostaje lokalny.
