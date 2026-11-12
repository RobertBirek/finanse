# Velo: porównanie wyciągu i zatwierdzony przelew z karty

Data: 2026-11-12. **Przelew zapisany i niezależnie zweryfikowany na produkcji.**
Parametry umowy, identyfikatory właściciela, kont i operacji pozostają poza Git.

## Zgoda i zakres

Użytkownik polecił porównanie z księgą, dodanie kredytów/parametrów i zamknięcie
zadania przez scalenie, push main oraz wdrożenie. Po ustaleniu, że Q7 już istnieje,
a nowy plan karty nie ma potwierdzonego bankowego terminu pierwszej raty, wybrał
**„Przelew teraz, plan później”**: przelew z datą wykonania wskazaną w porozumieniu,
zachowanie parametrów i brak tworzenia rat do uzyskania bankowego terminu.

Nie uznano daty z porozumienia za niezależne potwierdzenie księgowania bankowego.
W audycie zapisano źródło daty oraz jawne zatwierdzenie użytkownika.

## Porównanie źródeł z księgą

- Odczyt owner-scoped, transakcja `REPEATABLE READ READ ONLY`.
- Październikowy Velo: 61 wierszy. 44 mają kandydatów o zgodnej dacie księgowania
  i kwocie, 3 dalsze według daty operacji i kwoty. Dla kolejnych 3 znaleziono
  pobliskie daty przy zgodnych kwotach/opisach, 11 nie ma kandydata.
- To kandydaci do uzgodnienia, **nie potwierdzenie 47 lub 50 duplikatów**. Nie
  utworzono linków ani nie poprawiano dat. 11 pozycji bez kandydata nie zaksięgowano.
- Przed zapisem nie znaleziono listopadowego kandydata odpowiadającego nowemu
  przelewowi. Guard sprawdzono ponownie pod blokadami kont przed utworzeniem.
- Q7: jedna istniejąca umowa, 59 rat, jedna powiązana spłata. Bez duplikowania.

## Wykonanie

Świeży szyfrowany backup **bez retencji**, lokalny odczyt backupu/checksum i restore
wyłącznie do własnego PostgreSQL na izolowanej sieci internal, bez host-portów.
Próba użyła dokładnego obrazu aktywnego backendu5dc84fe, z potwierdzonym imageID
i OCIrevision; aplikacja non-root, readonly, bez produkcyjnych credentiali/mountów.

Operator wywołuje istniejące `create_transaction` i `log_event` w pojedynczej
transakcji `SERIALIZABLE`, z owner-scoped lockami kont i mutationlock. Dokładny hash
zatwierdzonego requestu przypięto w operatorze przed importami bazy. Zmiana requestu,
obrazu, Q7 lub konfiguracji karty daje STOP. Ponowienie nigdy nie jest automatyczne.

Rezultat produkcyjny:

- Dokładnie **1 transfer, 2 postings, 1 wpis audytu**. Posting z karty zwiększa jej
  zadłużenie, posting rachunku bieżącego zwiększa dostępne na nim środki.
- Suma postings równa zero; brak kategorii i wpływu na przychody/wydatki/budżet.
- Parametry porozumienia zapisane atomowo w audycie operacji; opis przelewu wskazuje
  warunki i oczekiwanie na harmonogram. Bez szacowanego terminu lub rozbicia rat.
- **0 nowych kont, umów, planów i rat**, bez zmiany limitu lub konfiguracji karty.
- Retencja wcześniejszych rekordów **75 tabel** potwierdzona przed commitem i po nim.
  Globalny invariant zwraca jedynie liczbę i SHA-256 obliczone po stronie PostgreSQL;
  operator nie pobiera pełnych rekordów innych właścicieli. Dane domenowe owner-scoped.
- Dokładna zmiana salda wyłącznie dwóch kont przelewu; pozostałe salda bez zmian.
  Q7, 59 UUID rat i istniejąca spłata bez zmian. Bez korekt Actual lub historii.
- Niezależna nowa sesja readonly potwierdziła trwałość transferu/parametrów,
  brak nowego planu oraz **0 naruszeń ledgeru**.

## Testy, review i naprawa próby

- Guardy: RED14assertions → GREEN5testów. Jedno safetyreview wskazało 3 blokady:
  exactapprovalhash, liveimagepin, ograniczenie globalnego snapshotu do metadanych.
  Pokryto je RED3FAIL → GREEN8testów, bez ponownego review.
- Pierwsza próba klonu wykryła zły układ argumentów `string_agg ORDER BY` przy
  odczycie początkowego snapshotu, **przed jakimkolwiek zapisem**. Zachowano log;
  nowy test SQL RED1FAIL → GREEN9testów. Wznowiono tylko własny klon na odtworzonym
  backupie, bez powtórki backupu lub restore produkcji.
- Finalny exactimage test: commit+postcommit/75retention/balancePASS; ponowienie
  zablokowane przed zapisem, liczba transakcji bez zmian. Produkcyjny operator
  i request mają identyczne hashe jak ten zaakceptowany przebieg.
- Świeże testy: **9 operatora, 21 backendowych kart, 617 frontendowych PASS**;
  35 integracyjnych backendu celowo poza focusedselection, bez runtime-skips.
  Passlib zgłasza istniejący warning wycofywanego `crypt`.
- Backend Ruff0.17.4 i mypy191sourcesPASS; frontend ESLint/TypeScriptPASS.
  Hostowy starszy Ruff0.16.2 zgłosił 3DTZ007 w niezmienionych parserach; nie
  poprawiano kodu, użyto zgodnego z wymaganiami runnera0.17.4. Hostmypy nie uruchomił
  się po tym błędzie. Nie deklarujemy nowego pełnego backend2329 lub nowego builda.

## Runtime i integracja

Zmiany gałęzi względem main i wdrożonej aplikacji dotyczą wyłącznie dokumentacji.
**Nie uruchomiono ponownego deployu, migracji ani restartu**: aplikacja już działa
w tej wersji, a zapis danych jest od razu widoczny przez istniejące endpointy.

Świeża weryfikacja: 752 trackedbackend/frontend zgodne z runtimecommit, 446 źródeł
obecnych w pakiecie zgodnych bajtowo, wszystkie15dist zgodne przezHTTPS. Backend,
worker, frontend i3usługi danych zachowały IDs/images/starttime, restarty0.
Public health/login200, anonimowe finance401, ARQreadinessPASS; runtimeERROR0.
Metadata release'u pozostają `verified-live`5dc84fe/schema84, bez udawania nowego
builda dokumentacyjnej rewizji. FF/push main zatwierdzone; wynik integracji w Git.

Cleanup: po kontroli ownership/exactID/network/mount/idle usunięto2własne kontenery,
sieć i wolumen oraz lokalną plaintextkopię restore i credentiale klonu. Bezforce,
prune lub usuwania backupów. Oryginały źródeł i cudze zasoby zachowano.

## Dowody i następne kroki

- Szyfrowany backup: `e775c54b8c2911fdf5c984406f067b27e0402ca513440072fcc699c72265ee35`.
- Operator SHA-256: `a0b7a9d8b166bd254e53a21f15c77d285c8a32c68640d2a7d95229c8c220ac95`.
- Prywatne źródła/dowody zachowane w katalogach `drive-statements-review-20261112-Du0lKmnZ`
  i `finance-config-20261112-vBoVbkka` pod `/tmp/opencode/`; trwały pakiet operatora
  i receiptów pod `/opt/finanse/webapp/maintenance/card-transfer-20261112-vBoVbkka/`.
- Nadal potrzeba bankowego terminu pierwszej raty/harmonogramu karty. Plan/raty
  odroczone zgodnie z wyborem użytkownika. Rozstrzygnięcie różnic Velo i ich księgowanie
  wymagają osobnego zakresu. Read-only follow-up następnego dnia pozostaje otwarty.
