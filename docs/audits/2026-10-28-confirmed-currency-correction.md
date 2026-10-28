# Potwierdzona korekta waluty źródłowej — 2026-10-28

## Zgoda i zakres

- Użytkownik potwierdził EUR dla wszystkich historycznych kwot wskazanego konta,
  potem osobno zatwierdził przeliczenie historycznej wyceny PLN według NBP.
- Właściciel i konto wskazane jednoznacznie z prywatnego, wcześniej uzgodnionego
  kontekstu. Inne konta o tej samej nazwie nie zostały zmienione.
- Korekta dotyczy jednego konta i sześciu prostych operacji przychód/wydatek,
  łącznie12 postingów. Kwoty źródłowe, ID, daty, kategorie, kierunki, mapping Actual
  i budget-impact zachowane. Zmieniono walutę EUR, kurs/proweniencję i wycenę PLN.

## Zabezpieczenia i testy

- Operator-only serwis `currency_correction.py`, lokalny commit51bf351. Bez nowego
  endpointu, force flag w UI, osłabienia AccountUpdate, migracji i wymiany obrazów.
- READ ONLY preview i niezależne ponowne pobranie oficjalnego NBP, sealed pin0400,
  jawny CLI digest, pin hashów kodu operatora/serwisu/guarda, świeży snapshot.
- Apply ponownie sprawdza oficjalny kurs, datę i źródło; blokuje konto/transakcje,
  odrzuca drift lub inne zależności, zapisuje w jednej transakcji z audytem.
- Wszystkie mapped tables fingerprintowane; dozwolone wyłącznie uzgodnione pola,
  timestampy i dokładnie jeden event o właściwym owner/entity/action/old/new.
  Kontrole pozostają aktywne przy Python -O; brak zatwierdzenia jest odrzucany.
- Targeted14 PASS, pełny backend **858 PASS** (8 proxy deselected,2 znane warningi),
  Ruff/mypy69 PASS; niezmieniony frontend243/lint/types PASS.
- Pierwszy review zatrzymał zapis i wymusił powyższe zabezpieczenia. Test podmiany
  kursu z przeliczonym digestem RED→GREEN. Scoped re-review potwierdził zamknięcie
  czterech uwag do kodu; uzupełniono brakujące poświadczenie i końcowy gate858.

## Backup, próba i wykonanie

- Świeży szyfrowany backup **1732c2cc**, izolowany restore success/0.
- Identyczna korekta na świeżej kopii produkcji (tmpfs, network-none) PASS.
  W kopii odtwarzano osobno potwierdzone oficjalne kursy; twardy guard DB/host/user
  uniemożliwia użycie trybu offline dla produkcji. Produkcja zawsze sprawdza NBP.
- Ostateczny READ ONLY preflight: stan i kursy nadal identyczne z zatwierdzonym planem.
- Jednorazowy operator wykonał zatwierdzony zapis. Guard wszystkich innych kolumn
  i tabel przeszedł przed commitem; nie utworzono nowych transakcji/postingów.
- Świeży odczyt po commicie: konto EUR,6 operacji/12 postingów EUR, poprawne kwoty
  PLN wg zatwierdzonych kursów, suma postings=0 i dokładnie1 event audytowy. Salda
  źródłowe i PLN zgodne z odpowiedzią operatora; HTTPS health200.
- Kontenery aplikacji nie były wymieniane; nie wykonywano importu ani korekt Velo.
- Prywatne dowody (bez danych w Git): `/tmp/opencode/revolut-eur-20261028/`.
  Końcowe porównanie oryginalnych plików z właściwym backupem1732 PASS;
  żadnego istniejącego oryginału nie nadpisano. Starszy baseline wydania9db
  nie był właściwą bazą porównania tej operacji.
- Trwałe, prywatne dowody z manifestem hashów:
  `/opt/finanse/webapp/maintenance/confirmed-eur-20261028-51bf351` (0700/0600).

## Stan kodu

Kod i dokumentacja pozostają w lokalnej gałęzi `fix/confirmed-eur-currency`.
Nie wypychano nowego kodu ani nie wdrażano nowej aplikacji: zadanie dotyczyło
zatwierdzonej korekty danych. Zwykła blokada edycji waluty przy historii nadal działa.
