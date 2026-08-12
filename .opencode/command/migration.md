---
description: Utwórz nową migrację Alembic (autogenerate). Użycie: /migration "opis zmiany"
---

Utwórz nową migrację Alembic na podstawie zmian w modelach SQLAlchemy:

`cd /opt/finanse/backend && .venv/bin/alembic revision --autogenerate -m "$1"`

Następnie:
1. Przejrzyj wygenerowany plik w `migrations/versions/` — zweryfikuj, że zawiera
   dokładnie zamierzone zmiany i nie ma niczego nieoczekiwanego
   (np. drop/rename tabel, zmiany typów bez potrzeby).
2. Wykonaj `alembic upgrade head`.
3. Pokaż użytkownikowi podsumowanie zmian w migracji.
