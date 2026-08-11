# Advisor with Tool Calling — Design Spec

Data: 2026-08-12 | Status: approved

## Overview

Connect 6 read-only tools to the Advisor LLM via OpenAI-compatible function calling. The LLM can now answer questions about real user data: account balances, transactions, tasks, schedule, projects.

Scope: autonomy level 0 (observation) only. Mutating tools (create_transaction, create_task) planned for next iteration.

## Tool Calling Flow

```
User message
  → Save Message(role=user)
  → Build messages = [system_prompt, ...history]
  → Add tools = [OpenAI function schemas for 6 tools]
  → LLM call with tools + tool_choice="auto"

If LLM returns tool_call:
  → Save Message(role=assistant, content=None, tool_calls=[...])
  → For each tool_call:
      → Execute via registry
      → Save ToolExecution(status=completed, result=...)
      → Append {role: "tool", tool_call_id, content: result}
  → LLM call again with tool results
  → Save final Message(role=assistant, content=...)
  → Return to user

If LLM returns text directly:
  → Save Message(role=assistant, content=...)
  → Return to user
```

Max 3 iterations (prevent infinite tool loop). Tools can call tools (e.g. get_tasks → get_projects).

## System Prompt

Dynamic, includes tool descriptions:

```
Jesteś osobistym doradcą. Pomagasz zarządzać czasem, pieniędzmi i projektami.

Masz dostęp do narzędzi:
- get_accounts — lista kont z saldami
- get_financial_summary — podsumowanie finansowe (przychody, wydatki, miesiąc)
- get_transactions — lista transakcji (filtruj po type: income/expense/transfer)
- get_today_schedule — dzisiejszy kalendarz i zadania
- get_tasks — lista zadań (filtruj po status, project_id)
- get_projects — lista projektów z ich statusami

Zasady:
- Odpowiadasz po polsku, zwięźle i konkretnie
- ZAWSZE używasz narzędzi gdy użytkownik pyta o dane
- Nie wymyślasz liczb — pobierasz je przez narzędzia
- Formatujesz kwoty czytelnie (123.45 PLN, nie 12345)
- Sugerujesz działania, ale nie podejmujesz decyzji
```

## Tools Registry

New file: `backend/app/advisor/tools/registry.py`

```python
# 6 read-only tools, each with:
# - OpenAI function schema (name, description, parameters)
# - execute function (async, takes user_id + arguments, returns serializable dict)
# - autonomy_level = 0

async def execute_get_accounts(user_id, **kwargs):
    accounts = await finance_service.get_accounts(db, user_id)
    return [{"name": a.name, "type": a.type, "currency": a.currency, "balance_pln": a._balance} for a in accounts]
```

## OpenAI Tool Schemas

Each tool gets a standard OpenAI function definition with typed parameters and clear descriptions.

## API Changes

MessageResponse extended:
```python
class MessageResponse:
    ...
    tool_calls: list[dict] | None = None  # raw OpenAI tool_calls array
    tool_executions: list[ToolExecutionResponse] | None = None  # execution results
```

## Frontend

- Tool calls shown as expandable banners between messages
- Default: collapsed (tool name + status)
- Expanded: full result (formatted text or structured data)
- Loading spinner while tool is executing

## Files

| File | Action |
|------|--------|
| `backend/app/advisor/tools/registry.py` | Create — unified tool registry |
| `backend/app/advisor/service.py` | Modify — tool calling loop in send_message |
| `backend/app/advisor/schemas.py` | Modify — ToolExecutionResponse, extended MessageResponse |
| `frontend/src/pages/Advisor.tsx` | Modify — render tool calls |
| `frontend/src/api/advisor.ts` | Modify — extended types |

## Excluded
- Mutating tools (create_transaction, create_task) — level 2
- Policy engine integration — level 2
- Audit logging — level 2
- Multi-step autonomous tool chains — level 4
