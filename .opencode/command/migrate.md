---
description: Wykonaj migracje bazy danych (alembic upgrade head)
---

Wykonaj migracje Alembic na bazie PostgreSQL:

`cd /opt/finanse/backend && .venv/bin/alembic upgrade head`

Zweryfikuj wynik:
- Jeśli były nowe migracje — potwierdź, że przeszły bez błędów.
- Jeśli nie było nowych migracji (brak zmian) — poinformuj o tym.

Nie wykonuj downgrade ani ręcznych zmian w bazie bez wyraźnej zgody.
