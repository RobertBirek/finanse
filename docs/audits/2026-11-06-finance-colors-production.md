# Kolory kont i kategorii — wydanie produkcyjne

## Zgoda i zakres

Użytkownik zatwierdził wdrożenie dodatku oraz ponownie dokładną rewizję `95f8380`
z migracją `7b57f2f0bde6 → f3a9d17c2e4b`, maintenance i zweryfikowanym backupem.
Zakres nie obejmował kolejnego APPLY drzewa kategorii, importów, zmian historii,
kwot, kont, polityk AI, zgód użytkownika lub wywołań dostawców modeli.

## Przygotowanie i ochrona danych

- Zachowano aktywny release `8121512`, obrazy i konfigurację rollbacku. Trzy nowe
  obrazy powstały offline z zaakceptowanego Git SHA, bez zmian zależności.
- Bajty aplikacji, migracji i dist zgodne z odebranym pakietem:
  1734 testy backendu, 507 frontendu, 145 E2E +1 oczekiwany skip, lint/typy/build PASS.
  Testowany kod nie został zmieniony przy wdrożeniu.
- Pełny inherited Compose zachowuje środowisko, zabezpieczenia, sieci, montowania
  i usługi danych. Zmiana dotyczy trzech wersjonowanych obrazów, nie host checkoutu.
- Świeży zaszyfrowany backup odtworzono na własnej bazie loopback; checksumy,
  schema i ledger zweryfikowane. Próba migracji zachowała wszystkie stare wiersze.
  Stary i nowy runtime poprawnie odczytały dane właścicieli z nowego schematu.
- Po publicznym HTTP503 sprawdzono DB/Redis: brak aktywnej pracy. Stary backend
  i worker zatrzymano łagodnie, ponownie sprawdzono stan, wykonano osobny świeży
  backup i odtworzenie. Odtworzona baza i uploads były identyczne z zamrożoną produkcją.

## Migracja i uruchomienie

Migrację produkcyjną wykonano **raz** w nowym runtime. Wszystkie projekcje wierszy
**56 dotychczasowych tabel identyczne**. Baza zawiera łącznie 34 konta i125 kategorii
wszystkich właścicieli; poprzednie79 dotyczyły zakresu operacji drzewa, nie całej bazy.
Nowe pola `color` pozostają NULL, oba CHECK obecne, zero naruszeń księgi. Oryginalne
uploads, polityki AI, zgody i audyt zachowane. Nie tworzono sesji lub wpisów użytkownika.

Backend, worker i frontend uruchomiono spójnie z rewizją `95f8380`. Nowy frontend
startuje z blokadą publicznych żądań; prywatny probe służy wyłącznie do odczytu
health/assets/401 przed otwarciem ruchu.

### Problemy wykryte przed otwarciem

- Konfiguracja klona bez ENVIRONMENT domyślnie włączała SQL echo i psuła parser
  JSON operatora; jawny tryb testowy naprawił wyłącznie klona, bez zmian produkcji.
- Weryfikator porównywał kolejność listy ENV, choć wartości były identyczne.
  Poprawiono porównanie map, zachowano testy odrzucania dodanych/usuniętych/zmienionych
  wartości. Nie zmieniono żadnego ustawienia aplikacji.
- Prywatne archiwum dowodów miało pliki600, a COPY zachowało ten tryb w obrazie
  frontendu. Prywatny probe wykrył403 i nginx permission denied. Test odczytu jako
  nginx najpierw RED, potem GREEN po ustawieniu publicznych plików obrazu na644,
  katalogów na755. **Bajty wszystkich zasobów nadal identyczne z testowanym dist**.
  Przebudowano offline i wymieniono tylko frontend za blokadą. Nie ponawiano migracji.
- Osobny read-only przegląd operatora wskazał dwa nieprzypięte skrypty starszych
  sesji. Przed maintenance zastąpiono je lokalnymi, samodzielnymi kopiami z kontrolą
  SHA. Testy naruszenia integralności i nieznanego artefaktu RED→GREEN. Bez ponownego
  przeglądu już odebranego kodu funkcji.
- Testy anonimowych401 prawidłowo dopisują systemowy audyt `session_rejected`.
  Weryfikator początkowo błędnie żądał braku jakichkolwiek nowych audytów. Nie wyłączono
  audytu: porównuje wszystkie wcześniejsze wiersze, a jedyny dopuszczony przyrost
  to nowe anonimowe systemowe odrzucenia sesji. Inne działania, aktorzy i domeny są
  odrzucane; testy walidatora RED→GREEN. Brak mutacji danych domenowych lub polityk.

Wszystkie pierwotne błędy i logi zachowano prywatnie; nie są deklarowane jako PASS.

## Odbiór

**Wdrożone: `95f8380`, schemat `f3a9d17c2e4b`, maintenance zdjęty.**

- Trzy usługi mają tę samą zaakceptowaną rewizję, prawidłowe obrazy i środowisko,
  zero restartów; backend/worker bez host mountu `/app`, zabezpieczenia zachowane.
- HTTPS strony i health200, pliki CSS/JS identyczne z przyjętym dist, anonimowe
  endpointy chronione401. Błędy logów nowych kontenerów0. Kontenery PostgreSQL,
  Redis, Stirling i ingress nie zostały wymienione.
- Produkcyjny smoke przeglądarkowy375/1440: przekierowania tras chronionych,
  poprawny layout/fonty, brak overflow i błędów JS, zero mutacji formularzy oraz
  żądań do innych originów. Obejrzano oba screenshoty logowania.
- Odczyty serwisów domenowych kont/kategorii i walidacja odpowiedzi PASS dla
  właścicieli. Nie podszywano się pod użytkownika ani nie testowano zapisu na jego
  danych. Funkcjonalne zapisy/dziedziczenie/reset pokrywa odebrany pakiet testów.
- Po smoke, jeszcze pod blokadą: wszystkie stare wiersze56 tabel zachowane,
  jedyny przyrost to oczekiwane systemowe odrzucenia anonimowych sesji w audycie.
  Po atomowym zapisaniu aktywnego release'u przywrócono normalny nginx i publiczny
  ruch; niezależna końcowa weryfikacja LIVE PASS.
- Dodatkowo5 testów operatora PASS. Błędy próbne (ENV, tryby plików, oczekiwany
  audyt) mają zachowane logi RED oraz osobne dowody poprawnego końcowego odbioru.

Dowody robocze: `/tmp/opencode/finance-colors-release-20261106/`; trwała kopia:
`/opt/finanse/webapp/releases/95f8380/evidence/`. To prywatne raporty operatora,
nie aplikacyjne źródło prawdy. Aktywną wersję określa `active-release.json`, nie
stary host checkout. Rollback zachowuje nowy schemat i zapisane kolory; bez
automatycznego downgrade/restore lub ponownej operacji drzewa. Zachowano branch,
worktree i niezwiązane Velo/Q7 dirty; bez merge/push lub zmian host checkoutu.
