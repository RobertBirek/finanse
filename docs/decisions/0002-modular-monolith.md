# ADR-002: Modularny monolit

**Status:** Accepted
**Date:** 2026-08-10

## Kontekst

System musi obsłużyć wiele domen (finance, work, inbox, advisor, documents, audit) przy jednoosobowym zespole developerskim.

## Decyzja

Stosujemy architekturę modularnego monolitu:
- Jeden proces backendowy (FastAPI), jedna baza danych (PostgreSQL)
- Domeny jako oddzielne pakiety Pythona (`backend/app/<domain>/`)
- Każda domena ma własne: models.py, schemas.py, service.py, router.py
- Domeny mogą się odwoływać do siebie tylko przez serwisy (nie bezpośrednio przez modele)

## Alternatywy odrzucone

- **Mikroserwisy:** Zbyt duży narzut operacyjny dla jednoosobowego zespołu
- **Full monolith bez podziału domen:** Ryzyko spaghetti kodu, trudne testowanie
- **Supabase/backend-as-a-service:** Ogranicza kontrolę nad logiką domenową

## Konsekwencje

- Łatwa późniejsza ekstrakcja domeny do osobnej usługi jeśli zajdzie potrzeba
- Współdzielona sesja bazy danych
- Testy mogą testować domeny w izolacji lub integracyjnie
- Konieczność dyscypliny w nie-cyklicznych zależnościach między domenami
