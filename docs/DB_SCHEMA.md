# DB_SCHEMA.md

Schemat bazy danych PostgreSQL dla Personal Advisor.

## Konwencje

- Wszystkie tabele: `created_at TIMESTAMPTZ NOT NULL DEFAULT now()`, `updated_at TIMESTAMPTZ NOT NULL DEFAULT now()`
- Kwoty: `BIGINT` w najmniejszej jednostce waluty (grosze, centy)
- Soft delete: `deleted_at TIMESTAMPTZ` tam gdzie sensowne
- UUID jako primary keys

---

## identity

### users
| Kolumna | Typ | Opis |
|---------|-----|------|
| id | UUID PK | |
| email | VARCHAR(255) UNIQUE NOT NULL | |
| password_hash | VARCHAR(255) NOT NULL | Argon2id |
| display_name | VARCHAR(255) | |
| household_id | UUID FK → households.id | |
| is_active | BOOLEAN DEFAULT true | |

### households
| Kolumna | Typ | Opis |
|---------|-----|------|
| id | UUID PK | |
| name | VARCHAR(255) NOT NULL | |

### sessions
| Kolumna | Typ | Opis |
|---------|-----|------|
| id | UUID PK | |
| user_id | UUID FK → users.id NOT NULL | `ON DELETE CASCADE`, indexed |
| token_hash | VARCHAR(64) NOT NULL | SHA-256 surowego tokenu; unique index `ix_sessions_token_hash` |
| csrf_token_hash | VARCHAR(64) NOT NULL | SHA-256 tokenu CSRF; walidacja CSRF jest osobnym etapem |
| expires_at | TIMESTAMPTZ NOT NULL | |
| revoked_at | TIMESTAMPTZ | Ustawiane przy wylogowaniu; rekord nie może już uwierzytelnić żądania |
| last_seen_at | TIMESTAMPTZ | Aktualizowane po poprawnym uwierzytelnieniu |
| created_at | TIMESTAMPTZ NOT NULL | |
| updated_at | TIMESTAMPTZ NOT NULL | |

---

## finance

### accounts
| Kolumna | Typ | Opis |
|---------|-----|------|
| id | UUID PK | |
| user_id | UUID FK NOT NULL | |
| name | VARCHAR(255) NOT NULL | |
| type | VARCHAR(50) NOT NULL | checking/savings/cash/credit/investment |
| currency | VARCHAR(3) NOT NULL DEFAULT 'PLN' | |
| is_active | BOOLEAN DEFAULT true | |
| opened_at | DATE | |
| closed_at | DATE | |

### categories
| Kolumna | Typ | Opis |
|---------|-----|------|
| id | UUID PK | |
| user_id | UUID FK NOT NULL | |
| name | VARCHAR(255) NOT NULL | |
| parent_id | UUID FK → categories.id | hierarchia |
| type | VARCHAR(50) NOT NULL | income/expense/transfer |

### financial_transactions
| Kolumna | Typ | Opis |
|---------|-----|------|
| id | UUID PK | |
| user_id | UUID FK NOT NULL | |
| date | DATE NOT NULL | |
| description | TEXT | |
| type | VARCHAR(50) NOT NULL | income/expense/transfer/exchange |
| is_pending | BOOLEAN DEFAULT false | |
| project_id | UUID FK → projects.id | opcjonalne powiązanie |
| created_by | VARCHAR(50) DEFAULT 'human' | human/agent |
| source | VARCHAR(50) DEFAULT 'manual' | manual/import/actual |

### postings
| Kolumna | Typ | Opis |
|---------|-----|------|
| id | UUID PK | |
| transaction_id | UUID FK NOT NULL | |
| account_id | UUID FK NOT NULL | |
| category_id | UUID FK | opcjonalna kategoria |
| source_amount | BIGINT NOT NULL | kwota w walucie źródłowej |
| source_currency | VARCHAR(3) NOT NULL | |
| base_amount_pln | BIGINT NOT NULL | przeliczona na PLN |
| fx_rate | NUMERIC(12,6) | kurs wymiany |
| fx_rate_source | VARCHAR(50) | manual/nbp/api |
| direction | VARCHAR(6) NOT NULL | debit/credit |

**Invariant:** SUM(postings.base_amount_pln) WHERE direction='credit' - SUM(postings.base_amount_pln) WHERE direction='debit' = 0 per transaction.

---

## work

### projects
| Kolumna | Typ | Opis |
|---------|-----|------|
| id | UUID PK | |
| user_id | UUID FK NOT NULL | |
| name | VARCHAR(255) NOT NULL | |
| description | TEXT | |
| status | VARCHAR(50) DEFAULT 'active' | active/on_hold/completed/cancelled |
| deadline | DATE | |
| color | VARCHAR(7) | hex kolor |

### tasks
| Kolumna | Typ | Opis |
|---------|-----|------|
| id | UUID PK | |
| user_id | UUID FK NOT NULL | |
| project_id | UUID FK | nullable — zadanie bez projektu |
| title | VARCHAR(500) NOT NULL | |
| description | TEXT | |
| status | VARCHAR(50) DEFAULT 'todo' | todo/in_progress/done/cancelled |
| priority | VARCHAR(20) DEFAULT 'medium' | low/medium/high/urgent |
| due_date | DATE | |
| estimated_minutes | INTEGER | |
| actual_minutes | INTEGER | |
| completed_at | TIMESTAMPTZ | |
| source | VARCHAR(50) DEFAULT 'manual' | manual/inbox/agent |

### time_blocks
| Kolumna | Typ | Opis |
|---------|-----|------|
| id | UUID PK | |
| user_id | UUID FK NOT NULL | |
| task_id | UUID FK | opcjonalne |
| project_id | UUID FK | opcjonalne |
| start_time | TIMESTAMPTZ NOT NULL | |
| end_time | TIMESTAMPTZ NOT NULL | |
| block_type | VARCHAR(50) DEFAULT 'shallow' | deep_work/shallow/meeting/break |
| title | VARCHAR(255) | |

**Constraint:** start_time < end_time.

---

## inbox

### inbox_items
| Kolumna | Typ | Opis |
|---------|-----|------|
| id | UUID PK | |
| user_id | UUID FK NOT NULL | |
| content | TEXT NOT NULL | |
| source_type | VARCHAR(50) DEFAULT 'text' | text/file/link/email/photo |
| target_type | VARCHAR(50) | task/project/transaction/document/decision/reference |
| target_id | UUID | wypełniane po klasyfikacji |
| is_processed | BOOLEAN DEFAULT false | |
| classified_by | VARCHAR(50) | human/agent |
| agent_suggestion | JSONB | propozycja AI |

---

## advisor

### conversations
| Kolumna | Typ | Opis |
|---------|-----|------|
| id | UUID PK | |
| user_id | UUID FK NOT NULL | |
| title | VARCHAR(255) | |

### messages
| Kolumna | Typ | Opis |
|---------|-----|------|
| id | UUID PK | |
| conversation_id | UUID FK NOT NULL | |
| role | VARCHAR(20) NOT NULL | user/assistant/system/tool |
| content | TEXT | |
| tool_calls | JSONB | |

### tool_executions
| Kolumna | Typ | Opis |
|---------|-----|------|
| id | UUID PK | |
| message_id | UUID FK NOT NULL | |
| tool_name | VARCHAR(255) NOT NULL | |
| arguments | JSONB | |
| result | JSONB | |
| status | VARCHAR(50) DEFAULT 'pending' | pending/pending_confirmation/completed/error/denied |
| autonomy_level | INTEGER DEFAULT 0 | 0-4 |
| policy_check_passed | BOOLEAN | |

---

## documents

### documents
| Kolumna | Typ | Opis |
|---------|-----|------|
| id | UUID PK | |
| user_id | UUID FK NOT NULL | |
| filename | VARCHAR(500) NOT NULL | |
| original_name | VARCHAR(500) NOT NULL | |
| mime_type | VARCHAR(100) | |
| sha256_hash | VARCHAR(64) NOT NULL | |
| size_bytes | BIGINT | |
| storage_path | VARCHAR(1000) NOT NULL | |

### document_texts
| Kolumna | Typ | Opis |
|---------|-----|------|
| id | UUID PK | |
| document_id | UUID FK NOT NULL UNIQUE | |
| extracted_text | TEXT | wynik OCR |
| ocr_engine | VARCHAR(50) | stirling/tesseract |
| extracted_at | TIMESTAMPTZ | |

---

## audit

### audit_events
| Kolumna | Typ | Opis |
|---------|-----|------|
| id | UUID PK | |
| user_id | UUID FK | |
| entity_type | VARCHAR(100) NOT NULL | |
| entity_id | UUID NOT NULL | |
| action | VARCHAR(50) NOT NULL | create/update/delete/approve/revert |
| old_state | JSONB | |
| new_state | JSONB | |
| performed_by | VARCHAR(50) DEFAULT 'human' | human/agent |
| source_ip | VARCHAR(45) | |

---

## Indeksy

- `users(email)`, `users(household_id)`
- `sessions(token_hash)` UNIQUE, `sessions(user_id)`
- `accounts(user_id)`, `accounts(currency)`
- `categories(user_id, type)`
- `financial_transactions(user_id, date)`, `financial_transactions(project_id)`
- `postings(transaction_id)`, `postings(account_id)`
- `projects(user_id, status)`
- `tasks(user_id, status)`, `tasks(project_id)`, `tasks(due_date)`
- `time_blocks(user_id, start_time)`, `time_blocks(task_id)`
- `inbox_items(user_id, is_processed)`
- `messages(conversation_id)`
- `documents(user_id)`, `documents(sha256_hash)`
- `audit_events(entity_type, entity_id)`, `audit_events(user_id)`
