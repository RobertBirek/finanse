# Rozliczenie dokumentu bez transakcji

## Zatwierdzony zakres

Użytkownik zatwierdził opcję „Oznacz jako opłaconą bez transakcji”: cała pozostała
kwota faktury, bez częściowych deklaracji; znika z pozycji do zapłaty i prognozy,
nie tworzy wydatku ani nie zmienia sald; jawny status deklaracyjny, audit, możliwość
cofnięcia i późniejszego powiązania rzeczywistej płatności bez podwójnego rozliczenia.

## Decyzje implementacyjne proponowane przez agenta

Wykorzystać istniejące `FinancialDocument.declaration="declared_paid"`. Bez nowej
tabeli, kwoty deklaracji, migracji, typu transakcji lub sztucznej alokacji.
`paid_minor`, `remaining_minor`, `allocations`, `reconciliation` nadal opisują
wyłącznie powiązania z księgą. Nie ustawiać `reconciliation="full"` dla deklaracji.

„Do zapłaty” w UI to0 dla deklaracji i rzeczywista pozostała kwota w innym przypadku.
„Pozostało do powiązania z księgą” zawsze pokazuje `remaining_minor`. Rejestr nie
oznacza deklaracyjnie opłaconego dokumentu jako zaległego. Oryginał i historia alokacji
pozostają dostępne. Status dokładny: „Opłacona deklaracyjnie — bez powiązania z księgą”.
Przy częściowej rzeczywistej alokacji status: „Opłacona deklaracyjnie — częściowo
powiązana z księgą”. Gdy alokacje pokrywają całość, pierwszeństwo ma „Rozliczona
z księgą”; wcześniejsza deklaracja pozostaje faktem historycznym, nie drugą wpłatą.

Przyszłe alokacje konsumują rzeczywistą pozostałą kwotę, nie sumują deklaracji jako
wpłaty. Częściowe powiązanie jest nadal dozwolone; deklaracja obejmuje wtedy całą
pozostałą niepowiązaną resztę. Nie ma edycji częściowej kwoty deklaracji.
Późniejsze powiązania zachowują obecny zakres: tylkoPLN. Deklarację bez księgowania
można nadać równieżEUR/USD, ale ta funkcja nie dodaje ich rozliczania z transakcjami
ani przeliczeńFX. UI nie obiecuje nieobsługiwanego powiązania walutowego.

Cofnięcie oznacza świadome „Przywróć do zapłaty” (`declaration="payable"`), nie
cofnięcie przelewu, usunięcie alokacji lub odtwarzanie nieznanego poprzedniego statusu.
Potwierdzenie wyjaśnia, że pozostała kwota może wrócić do prognozy, jeśli spełnia
pozostałe istniejące warunki. Już powiązane kwoty nie stają się ponownie należne.

## Kontrolowana komenda

`POST /api/finance/bills/{bill_id}/payment-declaration`, `Idempotency-Key`.
Request: `expected_version: StrictInt>=1`, `declaration: Literal["declared_paid",
"payable"]`, `confirm_forecast_effect: Literal[True]`; zabronione dodatkowe pola.
Response: istniejący `BillResponse`, bez zmiany publicznego znaczenia jego kwot.

Serwis `set_bill_payment_declaration` w osobnym `bill_declarations.py` korzysta
z `_run_bill_command`, owner-scoped `_bill`, mutationlock i rowlock. Tylko aktywny,
zatwierdzony dokument z dodatnią kwotą pozostałą i walutąPLN/EUR/USD. Konto płatnicze,
kategoria lub natywny odczytOCR nie są konieczne do samej deklaracji. BrakFX.
Stary version→409, inny owner/nieistniejący dokument→404, niedozwolony stan→422.
Ogólny `PATCH` nie może zmienić deklaracji zatwierdzonego dokumentu z pominięciem
tej komendy/potwierdzenia/audytu; zwraca422 ze wskazaniem właściwej akcji. Początkowy
wybór deklaracji podczas zatwierdzania szkicu pozostaje bez zmian.
Idempotentny retry zwraca oryginalną odpowiedź bez kolejnego auditu i zmiany version.
Nowy zamiar z tą samą deklaracją jest noop po walidacji version, bez dodatkowego auditu.
Rollback obejmuje dokument/audit/receipt; brak zapisów do ledgeru, kont i alokacji.

Audit ma poprzednią/nową deklarację, version, pozostałą kwotę/walutę, aktora i jawny
brak transakcji. Poza tym standardowa autoryzacja i zabezpieczeniaAPI, bez obejść.
Zmiana total/currency już deklaracyjnie opłaconego dokumentu wymaga najpierw
cofnięcia deklaracji; nie przenosić deklaracji po cichu na inną kwotę lub walutę.

## Prognoza i widoki

`project_bill_cashflows` pomija `declared_paid` jako brak przyszłego odpływu:
bez wpisu do zapłaty, zmiany sald dziennych i fałszywego ostrzeżenia o brakujących
danych tej pozycji. Nie rusza `RecurringOccurrenceCoverage`: zastąpiona pozycja
cykliczna nie odżywa po deklaracji, nie powstaje drugi koszt. Cofnięcie przywraca
normalną ocenę kwalifikacji. Pozostałe wykluczenia dokumentów nieopłaconych bez zmian.

UI korzysta z istniejącego stylu, bez redesignu. Osobne akcje w szczegółach:
„Oznacz jako opłaconą bez transakcji” i „Cofnij oznaczenie opłacenia”, z potwierdzeniem.
Rejestr pozostaje dostępny dla opłaconych dokumentów; nie usuwać ich z historii.
Busy/error/version-conflict: brak podwójnego submitu, zachowanie intencji przy retry,
po409 wymagane odświeżenie i świadoma nowa decyzja. Cache faktur/prognozy odświeżony;
bez zbędnej invalidacji transakcji/raportów, których kwoty nie zmieniły się.

## Granice i odbiór

Nie oznaczać automatycznie istniejącej faktury użytkownika, nie dodawać przelewów,
kwot częściowych, daty płatności, notatek, zmianyOCR lub automatycznego rozliczenia.
Wyłącznie implementacja i testy na syntetycznych danych. Deploy, migracje produkcji,
merge/push i finansowe mutacje nie należą do tej zgody.
Odbiór: testy backendu/API/prognozy/idempotencji i UI, przepływ deklaracja→częściowe
powiązanie→pełne powiązanie, undo po częściowym powiązaniu, zero zmian ledgeru.

## Builder-check i rozstrzygnięcia

Sesja `ses_e30b3af48ffeMPNj9L6630F8Z9`: modelbezmigracji i semantykaalokacji
potwierdzone. Uwaga o obejściu przez genericPATCH uwzględniona guardem dlaapproved.
KwestięEUR/USD rozstrzygnięto jako zachowanie istniejącego ograniczeniaPLN dla
alokacji, nie rozszerzenie zakresu o nową funkcjęFX. Koszt: dlaEUR/USD nadal możliwa
tylko deklaracja, bez linku do księgi; nie jest to regresja obecnego zachowania.
