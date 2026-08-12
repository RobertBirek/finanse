---
description: Przebuduj i wdróż backend/frontend na produkcję (docker compose)
---

Wdróż zmiany na produkcję (finanse.birek.online):

1. `docker compose -f /docker/finanse/compose.yaml build backend frontend`
2. `docker compose -f /docker/finanse/compose.yaml up -d backend frontend`
3. Sprawdź status: `docker compose -f /docker/finanse/compose.yaml ps`
4. Health check: `curl -s https://finanse.birek.online/api/health`

Zasady:
- Przed deployem upewnij się, że testy przechodzą (`/test`).
- Jeśli po wdrożeniu coś nie działa — zdiagnozuj (logi kontenerów)
  i w razie potrzeby przywróć poprzednie obrazy.
- Nie wdrażaj bez potwierdzenia zmian przez użytkownika.
