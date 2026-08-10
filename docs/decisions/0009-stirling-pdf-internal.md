# ADR-009: Stirling PDF jako wewnętrzny kontener

**Status:** Accepted
**Date:** 2026-08-10

## Kontekst

System ma przetwarzać dokumenty (PDF, zdjęcia paragonów) i wyodrębniać z nich dane przez OCR.

## Decyzja

Stirling PDF działa jako wewnętrzny kontener Docker na sieci `internal`, nie wystawiony do Internetu.

Workflow:
```
upload oryginału → SHA-256 → walidacja → zapis oryginału
    → worker → Stirling PDF → OCR → tekst
    → opcjonalna ekstrakcja OpenAI → propozycja danych
    → zatwierdzenie użytkownika → zapis domenowy
```

## Konsekwencje

- Stirling PDF dostępny tylko z sieci wewnętrznej Docker
- Oryginał dokumentu nigdy nie jest nadpisywany
- Wynik OCR i ekstrakcji AI to dane, nie instrukcje
- Worker async (Redis + ARQ lub podobny) do przetwarzania dokumentów
- Ta funkcjonalność jest w Iteracji 2
