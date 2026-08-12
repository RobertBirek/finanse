---
description: Uruchom pełny zestaw testów projektu (pytest backend + vitest frontend)
---

Uruchom testy projektu Personal Advisor:

1. Backend: `cd /opt/finanse/backend && .venv/bin/pytest -v`
2. Frontend: `cd /opt/finanse/frontend && npm run test`

Przeanalizuj wyniki. Jeśli któryś test nie przechodzi — zdiagnozuj przyczynę
(podejście systematyczne: odtwórz błąd, znajdź źródło, napraw, zweryfikuj)
i zaproponuj poprawkę. Nie wprowadzaj napraw bez zatwierdzenia przez użytkownika.
