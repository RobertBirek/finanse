# Pełny strumień obrazu przed AI — 2026-11-02

## Zgoda i zakres

Użytkownik zatwierdził naprawę potwierdzonego ucinania pochodnej oraz dostępność
PonówAI przy nieczytelnym wyniku. Bez obniżania2048px/quality90 lub limitów, bez
automatycznego AI/OCR/reuploadu i bez usuwania dokumentów/historii. Usuwanie po
ForeignKeyViolation500 jest odrębnym otwartym zadaniem, nie obejściem odczytu.

## Dowód przyczyny

Lokalny image_process z dokładnego runtime5d5b82f wytwarza644947B/1536×2048,
poprawny JPEG z głównego obrazu i właściwą orientacją, bezEXIF/XMP.
Publiczne async images.normalize_image zwracało65536B — dokładny prefix tegoJPEG,
bezEOI; Image.load zgłaszaOSError. Porównania skrótów wyłącznie w pamięci potwierdziły
zgodność źródła i uciętej pochodnej z ostatnią ukończoną rewizjąAI. Nie wypisano
hashów, wartości faktury, nazw/ID lub pikseli i nie wywołanoAI/OCR.

Przyczyna: StreamReader.read(n) może zwrócić tylko dostępny fragment, nie EOF.
Po pojedynczym odczycie kod czekał na zakończenie procesu i zwracał niepełne dane.
Wcześniejszy smoke konwertera używał subprocess.run/capture_output — pełnego bufora,
nie aplikacyjnego asyncAPI. Małe syntetyczne JPEG nie ujawniały tej granicy.

## Poprawka

- images.normalize_image czyta kawałkami doEOF, z natychmiastowym odrzuceniem limit+1.
  Zapis stdin współbieżny z odczytem stdout; całość pod dotychczasowym timeoutem.
- Wymagane sukces procesu oraz JPEG SOI/EOI. Nie włączono dekodowania uciętych obrazów.
  Na każdym wyjściu cancelwriter, killjeślitrzeba, drainpozostałości i reapdziecka,
  zwolnienie semafora. Bez nieograniczonego zbierania stdout/stderr.
- UI rozpoznaje incomplete/image z unreadable lub missing_required_fields bez
  errorcode: wyjaśnia brak odczytu i oferuje jawnePonówAI, pozostawiając edycję ręczną.
  Brak wywołania na mount/poll; nowy intent wyłącznie po kliknięciu, backend nadal
  egzekwuje policy/quota/idempotency. Nie zmieniono starego modelu ani rewizji danych.

## Weryfikacja

- RED3backend: dużyJPEG różny od pełnegokonwertera, odroczonechunkstdout ucięte,
  truncatedSOI przyjęty;2UIRED dla nieczytelnych/brakującychpól. Pozostałe bazowe
  przypadki starego zachowania zachowane.
- FocusedGREEN61backend/1deselected,33frontend; Ruff/mypy/ESLint/tscPASS.
  PrawdziweOSprocess/pipe: dużyJPEG, dzielonystdout, współbieżnestdin/stdout,
  exactlimit/limit+1 przedEOF, exiterror/brakEOI, timeout/cancelPIDreaped i slotreusable.
- Prawdziwe asyncAPI z kandydatem mountedreadonly na dokładnymruntime i prywatnym
  źródle: **644947B, zgodne bajtowo z pełnym childoutput, decode1536×2048 PASS**.
  Oryginał niezmieniony, pochodna tylko w pamięci, bezAI/OCR/DB/network.
- Świeży backup **8f621fb2** i zainstalowany restore tego samego snapshotu success/0,
  bez resetu limitów systemd.16offlineguardów procedury wydania i syntaxPASS.
- Niezależny source/security review: brakCritical,1ImportantUI (retry dla nieobsługiwanych
  typów), poprawione w jednej rundzie4RED→GREEN; dodatkowynegative textreviewPASS,
 38focusedfrontend/lint/typesPASS. Minor odroczony: wzmocnić test overlap o wymuszenie
  zapełnienia większej niż typowa pojemność pipe; test używa mniejszego bufora asyncio,
  a pozostałe regresje dużegoJPEG/partialreads potwierdzają naprawę właściwego błędu.
- Operacyjny reviewer wymagał porównania z rzeczywistym stdout child, nie funkcją
  inprocess. Smoke poprawiony na subprocess.run(python-I image_process.py)/fullstdout.
  Cały syntheticPROGRAM sprawdzony na readonlymount kandydata:610370B trueasync==child,
  split/overflow/timeout/truncation+reapPASS, noAI/DB. To jawnie NIEjest proof exactimage
  doapply; finalny pakiet musi przejść test ponownie bez mountu. Scopedreview warunkowoApproved.

## Stan

**Dokładny pakiet d9a5797 odebrany; oczekiwanie na zgodę exactSHA. Produkcja5d5b82f.**
Dokładny SHA `d9a5797a8de03f8868124e179d71a799c9c031ac` zawiera4pliki kodu/testów.
Końcowy1080backend/335frontend/Ruff/mypy/ESLint/tscPASS,8deselected/10znanychostrzeżeń.
Source manifest potwierdza niezmienione testowane bajty; build/93E2E+1skipPASS.
Gotowe spójne obrazy:201plikówbackendu każdy zgodneGit, całe config/hardening/
networks/volumes niezmienione poza appimages. DokładnyimageID/OCIrevisiond9a5797:
trueasyncsyntheticstream610370B==pełnychild/decode/chunks/overflow/timeout/reapPASS,
8syntheticdatecases i4HTTP400regressionPASS. Wszystko networknone/noAI/DB.
Osobny exactworkerimageprobe udostępnionegoJPEG: trueasync644947B==fullchild,
decode1536×2048/metadatastripped/originalunchangedPASS, bezAI/OCR/DB.
Pytanie o zgodę exactd9a5797 zadane, brakodpowiedzi; powiadomienie o prepare niezgoda.
Faktyczne bloby źródeł frontendu i aktualny dist zgodne z dowodem build/E2E;
dist niezmieniony między build i E2E, nie powtarzać tej bramki.
Plan: docs/superpowers/plans/2026-11-02-complete-image-stream.md.
Prywatne dowody: /tmp/opencode/image-stream-fix-20261102/; oryginał poza tym katalogiem
i poza repo. Pakiet i smoke PRAWDZIWEGO asyncAPI w gotowymobrazie zakończonePASS;
pozostaje zgodaexactSHA przed jakimkolwiekapply.
Bez migracji, konfiguracjiAI/policychange, ponownej wysyłki faktury lub kasowania danych.

## Decyzja wykonawcza

Kontynuacja inline zatwierdzonej małej poprawki z niezależnymreview zamiast kolejnego
pytania o metodę; koszt nietrafienia preferencji: użytkownik mógłby woleć osobnych
wykonawców per task. Wszystkie bramki bezpieczeństwa/wydania pozostają wymagane.
