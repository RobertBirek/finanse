# Isolated Document Preview Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Uruchomić zatwierdzony, izolowany podgląd PR5 pod `https://finanse-test.birek.online` do ręcznego testu telefonu.

**Architecture:** Własny projekt Compose, dwie nowe sieci, PostgreSQL/Redis/uploady/OCR i testowy użytkownik. Jedynie frontend jest osiągalny przez nowy host Caddy; backend i usługi danych nie mają portów hosta ani połączeń z sieciami produkcji. Caddy dostaje wyłącznie nowy host i połączenie z dedykowaną siecią ingress, przez graceful reload.

**Tech Stack:** Aktualny commit PR5, Docker Compose, PostgreSQL16, Redis7, Stirling PDF, Caddy2.

**Spec:** Zatwierdzony w rozmowie30.10 plan: osobne kontenery/baza/pliki, dane fikcyjne, prawdziwy upload i lokalny OCR, bez LLM, jeden nowy host HTTPS; bez zmian istniejących tras, merge/pushmain/deploy produkcji.

## Global Constraints

- Nie kopiować DB, uploadów, .env ani sekretów produkcji. Nie uruchamiać operatorów importu/korekkt.
- Brak wspólnych mountów danych i sieci z aplikacjami produkcji; Caddy jest jedynym wspólnym ingress.
- Własny losowy SECRET_KEY i hasło użytkownika; ENVIRONMENT=production dla Secure cookies, host-only cookie, registration disabled, trusted origin tylko preview.
- Backend/worker bez kluczy LLM i bez egressu; OCR wyłącznie własny Stirling.
- Pliki infra/secrets poza repo: `/docker/finanse-preview/`; kod z git archive wskazanego SHA, nie dirtyworktree.
- Zmiana Caddy wyłącznie append hosta, hash guard/backup/validate/graceful reload/rollback; zachować wszystkie stare bloki bajtowo.
- Nie publikować haseł/tokenów w repo/raportach; dane logowania tylko w prywatnym pliku i przekazane właścicielowi.
- Podgląd nie jest certyfikacją telefonu. Test użytkownika pozostaje wymagany.

## Review Focus

1. Preview cannot reach production DB/uploads: test memberships/mounts/routes and distinct credentials.
2. Camera needs secure origin: verify trusted HTTPS, cookies and CSP/frame preview behavior.
3. Missing LLM: manual review works, OCR local, no upstream external request.
4. Adding Caddy host cannot alter existing routes: compare original blocks and read-only HTTPS smoke.
5. Rollback removes only preview host/network/containers, never shared services or data.

### Task1: Prywatny bundle i izolacja

- [x] Zarejestrować SHA PR5, snapshot konfiguracji starych tras i identyfikatorów produkcyjnych kontenerów; bez DB odczytu.
- [x] Utworzyć prywatny bundle Compose/nginx/env/seed z osobnymi sieciami i zasobami; config validation/security review przed startem.
- [x] Archiwum źródeł z Git i lokalne obrazy własnych tagów; bez zmiany obrazów produkcyjnych.

### Task2: Własny stack i syntetyczne dane

- [x] Uruchomić tylko nowy projekt; zastosować migracje tylko jego DB.
- [x] Utworzyć testowe konto, syntetyczne konta/kategorie i przykłady, bez prawdziwych danych.
- [x] Sprawdzić health, login, CSRF, registration denied, upload/PDF/HEIF/preview/OCR i manual review; brak LLM/egressu.

### Task3: Osobny HTTPS i odbiór

- [x] Przygotować append-only candidate Caddy, validate i porównać stare hosty.
- [x] Dołączyć Caddy do wyłącznie nowego ingressu; graceful reload bez restartu produkcji.
- [x] HTTPS/browser375/1440/auth/headers smoke oraz niezmienność istniejących tras i containerIDs; niezależny review.
- [x] Zaktualizować CHANGELOG/TASKS/JOURNAL i raport bez sekretów; przekazać URL/testlogin/instrukcję telefonu.

## Stan

Podgląd uruchomiony i niezależnie odebrany: https://finanse-test.birek.online .
Źródła6385f39 z PR5, wyłącznie dane syntetyczne. Dane logowania przekazane właścicielowi poza repo.
Realdevicecertification pozostaje do wykonania przez użytkownika. Nie wykonano merge/deploy produkcji.
