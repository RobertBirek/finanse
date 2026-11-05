# 4B — jedna rzeczywista próba syntetyczna: PASS

## Zgoda i zakres

Po warunkowej zgodzie do2PLN preflight zatrzymał próbę przed requestem
(`2026-11-05-receipt-read-api-preflight.md`,0wysyłek). Następnie user polecił
**„ok, działaj dalej, bez względu na koszty”**. Zniesiono wyłącznie próg pieniężny dla
tej jednej próby. Nie rozszerzono zgody na kolejne requesty, prywatne paragony,
aktywację aplikacji, produkcję, merge lub push.

## Wynik rzeczywistego wywołania

- Zakończone2026-11-05T09:45:27Z. **Dokładnie1 transport invocation, HTTP200, PASS.**
- OpenAI `gpt-6.1-terra`, `https://api.openai.com/v1/responses`, reasoningnone,
  `store=false`, strictschema, bez tools, SDK/HTTP retry0, redirects/proxiesoff.
- Istniejący `extract_receipt_items`/normalizator/parser/proposal/kalkulator4A,
  bez zmian plików aplikacji. Konfiguracja tylko w izolowanym procesie operatorskim.
- Syntetyczny JPEG1080×1080, znormalizowany76763B,1frame/noEXIF, wyłącznie fikcyjny tekst.
  Limity2048edge/1MiB/inputpixelbound4194304/output2048/response262144B/60sHTTP+75soverall.

| Dowód z obrazu | Odpowiedź po walidacji |
| --- | --- |
| Mleko80,00PLN | nameMleko, amount80.00, basisbefore_separate_discount, unreadablefalse |
| Plyn20,00PLN | namePlyn, amount20.00, basisbefore_separate_discount, unreadablefalse |
| Osobny kupon10,00PLN | amount10.00, kindseparate |
| Wydrukowane udziały8,00/2,00PLN | line_index0→8.00; line_index1→2.00 |
| Suma90,00PLN | receipt/PLN, printed_total90.00 |

Ostrzeżenia modelu0; problemy proposal0 i kalkulatora0. Lokalny kalkulator4A,
z wyłącznie syntetycznymi UUID kategorii w pamięci, wyliczył **7200/1800 groszy,
razem9000, różnica0**. Kategorie/UUID nie zostały wysłane modelowi. Nie zatwierdzono
produktów ani podziału płatności w aplikacji, nie utworzono transakcji/alokacji.

## Użycie i koszt

Provider zwrócił input_tokens2075, output_tokens221, total_tokens2296;
inputdetails:cache_write_tokens2072/cached_tokens0; outputdetails:reasoning_tokens0.
Są to rzeczywiste metryki usage, nie domniemanie, że obraz lub cache są bezpłatne.

Oficjalne źródła potwierdzały stawki Standard1USD input/5USD output za1Mtokenów,
ale szczegóły taryfy cachewrites/retencji i faktyczne rozliczenie nie zostały sprawdzone
w panelu billing. **Nie potwierdzono kwoty naliczonej USD ani PLN.** Nie podajemy ceny0
ani fikcyjnej dokładnej kwoty na podstawie samych sum tokenów. Wcześniejsza blokada
wyceny nie została uznana za rozwiązanie problemu taryfy; użytkownik wyraźnie ją uchylił.

## Zabezpieczenia i dowody

- Harness i10offline testów wyłącznie w `/tmp/opencode/receipt-read-api-20261105/` (0700).
  Testy10RED→GREEN; sprawdzone odmowy innego endpointu/modelu/obrazu/tools/store/tokenlimit,
  marker przed timeout i odmowa drugiego wysłania także przez nową instancję transportu.
- Jeden wąski readonly review harnessu `ses_e54e8ed90ffeFtlvcK3ebZVh3c`:Approved/no blockers.
  Drobna uwaga odroczona: przerwanie operatora jest konserwatywnie klasyfikowane jako
  stopped/no-retry, z zachowanym `error_type`; nie dotyczy tej zakończonej próby.
- `attempt.json` utworzonyO_EXCL/fsync PRZED HTTP. Istnienie tego pliku blokuje ponowny
  live run. To prywatny artefakt operatorski, nie zastępcza baza/polityka aplikacji.
- Po jednym requestcie nie uruchamiano drugiej generacji, testu innego modelu ani fallbacku.
- Klucz pobrany wyłącznie z nazwanego `OPENAI_API_KEY` do pamięci procesu. Nie użyto
  klucza LLM dla innego providera; brak sekretów w wynikach/repo/czacie/logach.
- OryginałSHA256 `50c1fe5f245f05c9e2288d5e832d97525f4a34e77ddccc5b62fca4be53b3f100`.
- PochodnaSHA256 `0670b99927a2d49f31f1de76af4452f5db031f47c01b32f9cae3c9d40a3ea3ec`.
- HarnessSHA256 `6faddb852c7008dd057fe5c4bc280db3a31b191f4b2f0d76ecabc859f5e87b11`.
- Configfingerprint `46425052aa61d28afd5bc9bc42ac94f33ad4f51fb35020d0be8d5df204bfb1e5`.
- Lokalny `result.json` zawiera ograniczony zwalidowany syntetyczny payload i usage,
  nie Authorization/rawHTTP. `prepared.json`, `attempt.json`, log10testów i progress
  zachowane. **Nie powtarzać live run.**

## Co ten PASS oznacza

Rzeczywisty model przyjął dokładny kontrakt klienta4B i poprawnie przepisał jedną prostą
syntetyczną próbkę z jawnymi udziałami rabatu. To NIE dowód jakości trudnych/prywatnych
paragonów ani live end-to-end workera/UI/polityki. Rabaty już w cenie/nieczytelne/cropy
nie były sprawdzane dodatkowym requestem.

Receipt_items purpose aplikacji nadal **OFF**. Brak DB/Redis/uploadów/importów,
zmian ledgeru, prywatnych zdjęć, zmian produkcji, merge lub push. Źródła produktu
i retained proof1628backend/493frontend/static/build/141E2E+1expectedskip bez zmian.
Kolejna próba/prywatny paragon lub wdrożenie/aktywacja wymagają osobnej zgody.
