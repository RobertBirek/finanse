# Jawne uzgodnienie zachowanej historii Actual

## Cel i zgoda

Użytkownik zatwierdził uzgodnienie jako surowy eksport Actual plus dokładnie jedna
istniejąca lokalna operacja Actual, nieobecna w tym eksporcie, z kontrolą jej ID i hasha.
Następnie wyłącznie próba na izolowanej kopii PA. Import produkcyjny nie jest zatwierdzony.
Identyfikatory, kwoty i manifest rzeczywistych danych pozostają poza repozytorium.

## Wymagania

- Domyślny importer bez manifestu nadal wymaga dosłownej zgodności z Actual.
- Opcjonalny manifest zawiera wyłącznie wersję, hash ZIP, user_id oraz pin jednej
  transakcji: Actual ID, PA UUID, hash pełnej transakcji i postingów. Nie zawiera kwot.
- Walidacja przypina źródło, właściciela, provenance ActualImportMapping, source=actual,
  prefiks opisu i brak operacji w bieżącym eksporcie. Wszystkie warunki muszą być spełnione.
- Kwoty pochodzą z PostgreSQL, nie z manifestu ani z różnicy w raporcie. Kanoniczny
  fingerprint obejmuje ID/owner/source/datę/opis/typ/pending/projekt/created_by oraz
  pełne postingi, w tym ID, referencje, kwoty, waluty, kursy, kierunki i budget impact.
- Zmieniony ZIP, dowolna zmiana zapisu, brak/wadliwe mapowanie, inny użytkownik lub
  ponowne pojawienie się operacji w źródle blokują próbę; nigdy podwójnego uwzględnienia.
- ZIP jest odczytany raz do niezmiennego bytes. Hash i parsowanie dotyczą dokładnie
  tych samych bajtów (ZipFile(BytesIO)); nie otwierać ponownie ścieżki po weryfikacji.
  Tryb manifestu wyodrębnia wyłącznie jeden główny plik db.sqlite do prywatnego katalogu.
- Brak operacji sprawdzać w unii ID zwykłych operacji, transferów i splitów.
  Obejmuje to wszystkie nietombstonowane wiersze: obie strony transferu, rodzica
  i dzieci splitu, także wiersze nieprzekształcone w operację przez parser.
  Powtórzone ID źródłowe blokują próbę przed weryfikacją pinu i zapisami.
- Provenance wymaga dokładnie jednego mapowania tego użytkownika o
  entity_type=transaction i actual_id z manifestu, którego entity_id jest PA UUID
  z manifestu. Właściciel, source=actual i dokładny prefiks [actual:<actual_id>]
  muszą należeć do wskazanego, istniejącego zapisu.
- Blokada importera per użytkownik i blokady wskazanej transakcji/postingów chronią
  weryfikację przed równoległą zmianą w trakcie importu.
- Kolejność blokad przez całą transakcję: advisory user → mapowania użytkownika
  ORDER BY entity_type/actual_id → wskazany FinancialTransaction → jego Posting
  ORDER BY UUID → zmapowane własne Account ORDER BY UUID → zmapowane własne Category
  (w tym grupy) ORDER BY UUID. Weryfikacja odświeża dane po uzyskaniu blokad. Brak
  własności/referencji blokuje próbę; błąd blokady/deadlock oznacza rollback, nie obejście.
- Dopiero po zwykłej walidacji mapowań dodatki wyliczone z zapisanych postingów
  zwiększają oczekiwane salda kont w walutach źródłowych oraz kategorii/grup w PLN.
  Referencje muszą być jednoznacznie zmapowane i obecne w źródle; braków nie zgadujemy.
- Raport zachowuje surowe uzgodnienie z Actual i osobno jawny wynik z zachowaną
  historią, identyfikację pinów i wyliczony wkład. Nie nazywa surowych sald zgodnymi.
- Końcowe ensure_reconciled nadal obowiązuje; każdy inny błąd/różnica powoduje rollback.
- Opcja jest zgodna tylko z wykonaniem wymagającym uzgodnienia. Nie łączyć jej z
  replace-legacy ani parser-only dry-run, który nie może sprawdzić bieżącego zapisu w PA.

## Poza zakresem

- Nie usuwać ani nie nadpisywać istniejących transakcji/postingów/opisów.
- Nie tworzyć operacji wyrównawczej, tolerancji kwotowej ani ogólnego ignorowania różnic.
- Nie zmieniać reguł księgi, API aplikacji, schematu bazy, walut ani kursów.
- Nie wdrażać, nie wykonywać migracji bazy i nie uruchamiać importu produkcyjnego.

## Wybory implementacyjne agenta

- Mały moduł wewnętrzny finance.actual_history; Pydantic z odrzucaniem nieznanych pól.
- SHA-256 kanonicznego JSON do fingerprintu; Decimal normalizowany do precyzji modelu.
- Fingerprint obejmuje wszystkie kolumny transakcji i postingów, w tym Base.id,
  created_at/updated_at i Posting.transaction_id; postingi sortowane po UUID.
  JSON: sort_keys=True, separators=(',', ':'), ensure_ascii=False, allow_nan=False,
  kodowanie UTF-8. UUID mały kanoniczny str, date ISO, datetime świadomy UTC z
  mikrosekundami, null/bool/int natywne JSON, tekst bez normalizacji Unicode.
  Numeric(12,6) jako string z dokładnie sześcioma miejscami, bez niejawnego zaokrąglania.
- Bez zmian ogólnego ReconciliationReport: importer buduje dwa zwykłe raporty, a jego
  writer dodaje jawne metadane i surowy raport tylko przy użyciu manifestu.
- JSON bez manifestu pozostaje identyczny. Z manifestem ma jawny envelope:
  schema_version=1, source_basis=actual_plus_pinned_preserved_history,
  raw_actual={zwykły raport}, augmented={zwykły raport},
  preserved_history={manifest: piny bez kwot, contributions: konta/kategorie/grupy}.
  ensure_reconciled używa wyłącznie obiektu augmented; tekst pokazuje osobno obie sekcje.
- Manifest jest jednorazowym wejściem autoryzacyjnym, nie finansowym źródłem prawdy.
  Dla rzeczywistej próby utworzyć go prywatnie po porównaniu ze wcześniej zamrożonym zapisem.

## Sukces

Regresje negatywne i pełny gate przechodzą. Na kopii jawne uzgodnienie jest zgodne
dla wszystkich kont/kategorii/grup, surowy raport zachowuje wyjaśnioną różnicę, a
wszystkie wcześniejsze transakcje/postingi pozostają identyczne. Ponowna próba nie
dubluje danych ani wkładu zachowanej operacji. Raport wraca do użytkownika przed produkcją.
