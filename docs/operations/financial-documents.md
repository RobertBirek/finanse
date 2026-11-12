# Rozliczanie faktur i paragonów

W **Finanse → Faktury i paragony** otwórz szczegóły zatwierdzonego, aktywnego dokumentu.

- **Powiąż płatność → Powiąż istniejącą** łączy dokument z wydatkiem już zapisanym
  w księdze. Nie tworzy kolejnej transakcji. Obecnie dotyczy PLN.
- **Zarejestruj płatność** tworzy nowy wydatek w księdze. Używaj wyłącznie, gdy nie
  został wcześniej zapisany. Nie zleca przelewu bankowego.
- **Oznacz jako opłaconą bez transakcji** deklaruje opłacenie całej pozostałej kwoty.
  W potwierdzeniu sprawdź kwotę i zaznacz zgodę. Nie powstaje transakcja, wydatek ani
  alokacja. Salda kont się nie zmieniają. Dokument znika z pozycji do zapłaty i prognozy,
  ale pozostaje w rejestrze wraz z oryginałami.

Status **Opłacona deklaracyjnie — bez powiązania z księgą** nie jest potwierdzeniem
bankowym. „Do zapłaty” wynosi zero; „Pozostało do powiązania z księgą” nadal pokazuje
rzeczywistą niepowiązaną kwotę. Późniejsze powiązanie istniejącej płatności PLN nie
sumuje deklaracji jako drugiej wpłaty. Pełne powiązanie daje status **Rozliczona z księgą**.

**Cofnij oznaczenie opłacenia → Przywróć do zapłaty** przywraca tylko pozostałą kwotę,
nie cofa przelewów ani istniejących alokacji. Kwota wraca do prognozy, jeśli spełnia
pozostałe warunki. Zastąpienie pozycji cyklicznej pozostaje bez zmian. Aby zmienić kwotę
lub walutę deklaracyjnie opłaconego dokumentu, najpierw cofnij oznaczenie.

Deklaracje działają dla PLN, EUR i USD bez wyliczania FX. Nie obsługują częściowych
kwot deklaracji. Rozliczanie z księgą w EUR/USD nie zostało dodane.

Po konflikcie wersji odśwież dokument, sprawdź nową kwotę i podejmij nową decyzję.
Po błędzie sieci ponów tę samą decyzję w otwartym oknie — klucz idempotencji nie zmieni się.
Zmiany deklaracji i ich cofnięcia są zapisywane w audycie.
