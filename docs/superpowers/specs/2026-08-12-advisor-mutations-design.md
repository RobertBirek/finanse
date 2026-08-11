# Advisor Level 2 — Mutations with Confirmation — Design Spec

Data: 2026-08-12 | Status: approved

## Overview

Add 3 mutating tools (create_task, create_time_block, create_transaction) at autonomy level 2. LLM proposes the action, user clicks confirm/deny in the UI.

## Tools

| Tool | Parameters | Executor |
|------|-----------|----------|
| create_task | title (required), priority, due_date, project_id | work_service.create_task() |
| create_time_block | title (required), start_time, end_time, block_type | work_service.create_time_block() |
| create_transaction | type, amount, currency, description, account_name, category_name | finance_service.create_transaction() |

## Flow

1. LLM calls tool → backend sees autonomy_level=2 → saves ToolExecution(status="pending_confirmation")
2. Frontend renders confirmation banner with [Zatwierdź] [Odrzuć]
3. User clicks → POST /api/advisor/tool-executions/{id}/confirm or /deny
4. Backend executes tool, updates status, returns result

## API

```
POST /api/advisor/tool-executions/{id}/confirm → execute + audit log
POST /api/advisor/tool-executions/{id}/deny    → mark as denied
```

## Files

| File | Action |
|------|--------|
| backend/app/advisor/tools/registry.py | +3 tools |
| backend/app/advisor/service.py | pending_confirmation for level≥2 |
| backend/app/advisor/router.py | +confirm/deny endpoints |
| frontend/src/api/advisor.ts | +useConfirmExecution, +useDenyExecution |
| frontend/src/pages/Advisor.tsx | confirmation buttons |
