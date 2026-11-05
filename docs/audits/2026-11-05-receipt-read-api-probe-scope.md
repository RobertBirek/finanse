# 4B — proponowany zakres jednej syntetycznej próby API

## Status i zgoda

**Update:** po c6d687d user zatwierdził wykonanie jednej próby warunkowo≤2PLN. Preflight
zatrzymany przed requestem: potwierdzone stawki exactmodel1/5USD, niepotwierdzone
naliczanie obrazu dla6.1Terra.0requestów próby/0odczytówklucza; nie podnoszono limitu
ani nie zmieniano modelu. Szczegóły `2026-11-05-receipt-read-api-preflight.md`.
Poniższy opis granicy zgody na przygotowanie jest historyczny.

2026-11-05: user zatwierdził wyłącznie **przygotowanie zakresu i limitów**, odpowiadając
„tak” na pytanie „Przygotować zakres i limity tej pierwszej próby, jeszcze bez wywoływania API?”.
Nie jest to zgoda na request, użycie klucza, aktywację aplikacji lub produkcję.
Poniższe wartości są propozycją autora do osobnego zatwierdzenia.

## Cel i granica próby

Sprawdzić, czy rzeczywisty provider przyjmuje dokładny kontrakt istniejącego klienta4B
i poprawnie przepisuje prosty, syntetyczny paragon. To test klienta/kontraktu i jednej
próbki odczytu, **nie** dowód jakości wszystkich paragonów ani live test całego workera/UI.

- Kandydat: zaakceptowane źródła backendf9fe4c8/UI527e92a, docs68314a0; retained proof
  1628backend/493frontend/static/build/141E2E+1expectedskip. Bez zmian tych źródeł i bez
  powtarzania niezmienionego godzinnego gate/migracji.
- Izolowany proces operatorski poza usługami aplikacji, bez połączeń z PostgreSQL/Redis,
  bez uploadu/importu, zatwierdzeń, workerów, crona lub modyfikacji ledgeru.
- Użyć istniejących normalizacji, `extract_receipt_items`, parsera/proposal i kalkulatora4A;
  bez alternatywnego promptu, ręcznie naprawianej odpowiedzi lub innego modelu po błędzie.
- Konfiguracja tylko dla procesu próby; aplikacyjny receipt_items purpose pozostaje OFF.
  Klucz poza repo/czatem/logami, przekazany przez uprawniony kanał dopiero po zgodzie.

## Proponowany odbiorca i limity

| Parametr | Propozycja |
| --- | --- |
| Provider / model | OpenAI / `gpt-6.1-terra` — jak historycznie zaakceptowana ekstrakcja; nie dziedziczy to zgody na4B |
| Endpoint | `https://api.openai.com/v1/responses`, bez przekierowań/proxy/fallbacku |
| Płatne próby | **1 request łącznie**, równoległość1, SDK/transport retry0 |
| Obraz | 1 syntetyczny JPEG po istniejącej normalizacji, edge≤2048, pixel upper bound≤4194304, bytes≤1048576 |
| Output | max2048 tokenów; reasoning effort `none`; bounded response≤262144B |
| Deadline | timeout klienta60s; zewnętrzna granica procesu75s; przekroczenie nie daje prawa ponowienia |
| Payload | max10 produktów/5 rabatów/20 udziałów, nazwy≤200 znaków; wersje prompt/schema jawnie oznaczone dla tej próby |
| Prywatność | wyłącznie syntetyk, `store=false`, bez tools, historii, kategorii, kont, NIP/IBAN lub prywatnych dokumentów |

Publiczna nazwa modelu pochodzi z raportu `2026-11-02-openai-production-release.md`,
nie z dzisiejszego sprawdzenia dostępności. Nie wykonywano GET model ani generacji.

## Próg kosztu: propozycja 2 PLN, warunkowa

2PLN jest proponowanym **progiem zgody przed wysłaniem**, nie udawanym twardym limitem
naliczania API. Bieżący cennik tego konkretnego modelu i górna granica tokenów obrazu/
promptu/schema nie zostały tu potwierdzone. Nie podajemy wymyślonej ceny pojedynczego calla.

Przed pierwszym requestem należy potwierdzić oficjalną taryfę i sposób naliczania obrazu,
oszacować konserwatywnie całe wejście oraz pełny limit2048 wyjściowych tokenów, a także
udokumentować przeliczenie USD→PLN. Bez ceny/specyfikacji pozwalającej wiarygodnie
ograniczyć koszt, przy niejasnym rozliczeniu lub wyniku>2PLN — **STOP, bez requestu**,
powrót do użytkownika. Nie zakładać, że miesięczny budżet projektu jest hard capem.

Timeout, zerwana odpowiedź albo restart po rozpoczęciu wysyłki może być płatny. Konserwatywnie
traktujemy tę jedną próbę jako zużytą; nie ponawiamy jej samoczynnie ani ręcznie bez nowej zgody.

## Syntetyczna próbka i kryteria

Obraz zostanie przygotowany dopiero w zatwierdzonej próbie. Fikcyjny sklep, dwa wyraźne
wiersze: Mleko80,00PLN i Płyn20,00PLN; osobny kupon10,00PLN z **wydrukowanymi** udziałami
8,00PLN i2,00PLN; wydrukowana suma90,00PLN. Bez prawdziwych identyfikatorów, QR lub kont.

PASS wymaga zakończonej odpowiedzi zgodnej ze strictschema; receipt/PLN, dwóch zgodnych
produktów i kwot, jawnych poprawnych udziałów rabatu oraz printed_total90,00. Niejasności,
ucięcie/refusal/unsupported lub błędny payload są wynikiem negatywnym, nie „naprawionym PASS”.
Nazwy mogą różnić się wielkością liter/normalizacją, nie tożsamością produktu.

Kalkulator4A lokalnie, bez bazy, ma dać net7200/1800 i total9000 groszy. Model nie dostaje
kategorii ani prawa do wyliczenia/potwierdzenia księgi. Brak nowej płatności lub alokacji.
Jedna prosta próbka nie sprawdza zwrotów, cropów, rabatów już w cenie ani nieczytelnych zdjęć.

## Wynik i kolejne zgody

Raport ma podać exactsource/config bez sekretów, hash syntetyka/pochodnej, liczbę wysłań,
status, walidację, lokalny wynik kalkulatora, znane input/outputusage oraz oszacowanie kosztu
(albo jawnie unknown). Nie logować klucza, Authorization, pełnych nagłówków/tracebacków SDK.
Artefakty operatorskie nie są źródłem prawdy aplikacji ani nowym magazynem dokumentów.

Każda druga próba/zmiana modelu, prywatny paragon, aktywacja, wdrożenie, merge/push
wymagają kolejnej zgody. Dziś nie napisano harnessu, nie wygenerowano obrazu, nie pobrano
klucza i nie wywołano API; przygotowano wyłącznie ten zakres.
