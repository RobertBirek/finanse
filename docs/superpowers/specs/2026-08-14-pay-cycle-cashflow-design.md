# Cykl wynagrodzenia i prognoza płynności — specyfikacja

## Cel
Pokazać, czy środki na kontach budżetowych wystarczą od ostatniego wynagrodzenia do kolejnego oczekiwanego wpływu oraz prognozować saldo na 30 dni bez automatycznego księgowania.

## Ustawienia
Per użytkownik: oczekiwany dzień wynagrodzenia (domyślnie 10), domyślne konto wpływu, horyzont 30 dni i tolerancja opóźnienia 3 dni.

## Scheduler
`ScheduledFinanceItem` przechowuje typ przychód/wydatek, konto budżetowe, kategorię, walutę, cykl, termin, metodę kwoty (`fixed` lub `last_actual`), kwotę stałą, status i powiązaną rzeczywistą transakcję.

Po terminie powstaje sugestia transakcji z kontem i kategorią. Nie zmienia księgi przed potwierdzeniem. Po 3 dniach bez rzeczywistego wpisu ma status `overdue_uncertain` i nie wpływa na prognozę.

## Prognoza
Saldo kont budżetowych + oczekiwane przychody − aktywne planowane wydatki. Widok pokazuje bieżący cykl wypłaty, bezpieczny limit dzienny, najniższe prognozowane saldo i oś 30 dni. Konta pozabudżetowe są wykluczone.

## Integracja
Rzeczywista transakcja może zostać utworzona wyłącznie po zatwierdzeniu sugestii lub wykryta przez zgodność konta, kategorii, kwoty i terminu. Po powiązaniu prognoza nie dubluje rzeczywistego zapisu.

## Testy
Cykl wypłaty, kwota z ostatniej rzeczywistej transakcji, wykluczenie offbudget, sugestia bez księgowania, opóźnienie po 3 dniach, saldo graniczne i brak podwójnego liczenia.
