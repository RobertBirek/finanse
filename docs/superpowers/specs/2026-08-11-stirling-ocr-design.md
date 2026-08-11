# Stirling PDF + OCR Pipeline — Design Spec

Data: 2026-08-11 | Status: approved

## Overview

Pipeline do przetwarzania dokumentów: upload PDF/zdjęć → OCR (Stirling PDF) → wyekstrahowany tekst → podgląd w UI. Uniwersalne OCR + full-text search, bez specjalizacji pod typ dokumentu na start. Architektura przygotowana pod przyszłą ekstrakcję danych przez OpenAI.

## Architecture

```
Frontend (React)                    Backend (FastAPI)              Infra
─────────────                       ─────────────────              ─────
  Documents Page                     POST /upload      ──→ disk (SHA-256)
  ┌────────────┐  multipart/form     GET /list          ──→ PostgreSQL
  │ drag&drop  │──────────────────→  GET /{id}
  │ aparat 📷  │←──────────────────  GET /{id}/text
  │ lista dok. │  JSON               ──→ ARQ enqueue
  │ podgląd    │
  └────────────┘               ┌─────────────────┐
                               │ ARQ Worker       │
                               │ process_document │──→ Stirling PDF
                               └─────────────────┘    POST /misc/ocr-pdf
```

## Document Flow

```
1. UPLOAD (POST /api/documents/upload)
   ├─ walidacja: PDF, JPG, PNG (max 20MB)
   ├─ SHA-256 hashowanie (deduplikacja)
   ├─ zapis: /app/uploads/{sha256[:2]}/{sha256}
   ├─ INSERT documents (status=pending)
   └─ ARQ enqueue: process_document(document_id)

2. WORKER (process_document, async, w tle)
   ├─ UPDATE status=processing
   ├─ jeśli obraz (JPG/PNG) → Stirling /convert/img/pdf → PDF tymczasowy
   ├─ Stirling /misc/ocr-pdf (languages: pol,eng, ocrType=skip-text)
   ├─ sidecar=true → tekst jako .txt
   ├─ INSERT document_texts (extracted_text, ocr_engine="stirling")
   └─ UPDATE status=done

3. ODCZYT
   GET /api/documents → lista z paginacją, filter po statusie
   GET /api/documents/{id} → metadane (nazwa, rozmiar, status, data)
   GET /api/documents/{id}/text → pełny tekst
```

**Statusy:** `pending` → `processing` → `done` | `error`

## ARQ Worker

- Biblioteka: `arq` (async, Redis-backed)
- Osobny proces worker (docker compose service `worker`)
- Redis database 1 (oddzielna od cache na db 0)
- Jedno zadanie: `process_document(document_id: str)`
- Worker ma własną sesję DB przez `async_session_factory` (współdzieloną z backendem)
- Konfiguracja w `backend/app/worker.py`

## API Endpoints

| Method | Path | Auth | Description |
|--------|------|------|-------------|
| POST | `/api/documents/upload` | required | Multipart upload (pole `file`) |
| GET | `/api/documents` | required | Lista (limit, offset, status filter) |
| GET | `/api/documents/{id}` | required | Metadane |
| GET | `/api/documents/{id}/text` | required | Wyekstrahowany tekst |
| DELETE | `/api/documents/{id}` | required | Usunięcie |

## Stirling PDF Setup

- Obraz: `frooodle/s-pdf:latest`
- Sieć: `internal` (dostępny tylko dla backendu i workera)
- Port: 8080 (expose, nie ports)
- Polski OCR: `pol.traineddata` w `/docker/finanse/data/stirling/trainingData/`
- Security: disabled (wewnętrzna sieć)
- Locale: pl-PL

## File Storage

- Katalog: `/app/uploads/` (volume mount → `./data/uploads`)
- Struktura: `{sha256[:2]}/{sha256}` (dwa pierwsze znaki hasha jako podkatalog)
- Oryginalna nazwa zachowana w DB (`original_name`)

## Frontend

- Strona: `frontend/src/pages/Documents.tsx`
- Upload: strefa drag & drop + przycisk aparatu (mobile: `capture="environment"`)
- Lista: tabela/karty z nazwą, datą, rozmiarem, statusem (kolorowy badge)
- Podgląd: modal z pełnym tekstem
- Auto-refresh: polling co 3s dla dokumentów w statusie `processing`
- API hooki: `frontend/src/api/documents.ts` (TanStack Query)

## Files

| File | Action |
|------|--------|
| `backend/app/documents/service.py` | Create — upload, list, get, delete, text extraction |
| `backend/app/documents/schemas.py` | Create — Pydantic schemas |
| `backend/app/documents/router.py` | Modify — full endpoints |
| `backend/app/worker.py` | Create — ARQ worker + process_document task |
| `backend/requirements.txt` | Modify — add `arq` |
| `backend/pyproject.toml` | Modify — add `arq` dependency |
| `docker/finanse/compose.yaml` | Modify — add `worker` service, enable stirling |
| `frontend/src/pages/Documents.tsx` | Create |
| `frontend/src/components/DocumentUpload.tsx` | Create |
| `frontend/src/components/DocumentList.tsx` | Create |
| `frontend/src/components/DocumentViewer.tsx` | Create |
| `frontend/src/api/documents.ts` | Create |

## Excluded (Future Iterations)

- OpenAI data extraction (structured data from text)
- Auto-creation of finance transactions from documents
- User approval workflow for extracted data
- Advanced OCR settings (deskew, clean, etc. — defaults only)
- Document deletion from disk (DB-only soft delete)
