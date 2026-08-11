# Advisor Tool Calling — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Connect 6 read-only tools to the Advisor LLM via OpenAI function calling — the Advisor can now answer questions about real user data.

**Architecture:** Tool registry (OpenAI schemas + executors) → modified send_message (tool calling loop) → frontend rendering (expandable tool call banners).

**Tech Stack:** DeepSeek API (OpenAI-compatible tool calling), FastAPI, SQLAlchemy, React, TanStack Query

---

### Task 1: Tool registry

**Files:**
- Create: `backend/app/advisor/tools/registry.py`
- Modify: `backend/app/advisor/service.py`

- [ ] **Step 1: Create tool registry**

Create `backend/app/advisor/tools/registry.py`:

```python
"""Unified tool registry for Advisor. Each tool has an OpenAI function schema + executor."""
from typing import Any, Callable, Coroutine

from sqlalchemy.ext.asyncio import AsyncSession

# Type for async executor functions: takes db + user_id + kwargs, returns serializable dict
ToolExecutor = Callable[[AsyncSession, str, ...], Coroutine[Any, Any, dict]]


class Tool:
    def __init__(
        self,
        name: str,
        description: str,
        parameters: dict,
        executor: ToolExecutor,
        autonomy_level: int = 0,
    ):
        self.name = name
        self.description = description
        self.parameters = parameters
        self.executor = executor
        self.autonomy_level = autonomy_level

    @property
    def openai_schema(self) -> dict:
        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.description,
                "parameters": self.parameters,
            },
        }


# ============================================================
# Executor functions
# ============================================================

async def _execute_get_accounts(db: AsyncSession, user_id: str, **kwargs) -> dict:
    from app.finance.service import get_accounts
    import uuid as _uuid
    accounts = await get_accounts(db, _uuid.UUID(user_id))
    return {
        "accounts": [
            {
                "id": str(a.id),
                "name": a.name,
                "type": a.type,
                "currency": a.currency,
                "balance_pln": getattr(a, "_balance", 0),
            }
            for a in accounts
        ]
    }


async def _execute_get_financial_summary(db: AsyncSession, user_id: str, **kwargs) -> dict:
    from app.finance.service import get_financial_summary
    import uuid as _uuid
    summary = await get_financial_summary(db, _uuid.UUID(user_id))
    return {
        "accounts": summary.accounts,
        "income_total_pln": summary.income_total_pln,
        "expense_total_pln": summary.expense_total_pln,
        "net_total_pln": summary.net_total_pln,
        "month": summary.month,
        "year": summary.year,
    }


async def _execute_get_transactions(db: AsyncSession, user_id: str, **kwargs) -> dict:
    from app.finance.service import get_transactions
    import uuid as _uuid
    txn_type = kwargs.get("type")
    limit = kwargs.get("limit", 20)
    txns = await get_transactions(db, _uuid.UUID(user_id), limit=limit, txn_type=txn_type)
    return {
        "transactions": [
            {
                "id": str(t.id),
                "date": str(t.date),
                "description": t.description,
                "type": t.type,
                "amount": sum(p.source_amount for p in t.postings if p.direction == "credit"),
            }
            for t in txns
        ]
    }


async def _execute_get_today_schedule(db: AsyncSession, user_id: str, **kwargs) -> dict:
    from app.work.service import get_today_schedule
    import uuid as _uuid
    schedule = await get_today_schedule(db, _uuid.UUID(user_id))
    return {
        "time_blocks": [
            {
                "id": str(b.id),
                "title": b.title,
                "start_time": b.start_time.isoformat() if b.start_time else None,
                "end_time": b.end_time.isoformat() if b.end_time else None,
                "block_type": b.block_type,
            }
            for b in schedule.time_blocks
        ],
        "tasks_due": [
            {
                "id": str(t.id),
                "title": t.title,
                "status": t.status,
                "priority": t.priority,
                "project_name": getattr(t, "project_name", None),
            }
            for t in schedule.tasks_due
        ],
    }


async def _execute_get_tasks(db: AsyncSession, user_id: str, **kwargs) -> dict:
    from app.work.service import get_tasks
    import uuid as _uuid
    status = kwargs.get("status")
    project_id = kwargs.get("project_id")
    if project_id:
        import uuid as _uuid2
        project_id = _uuid2.UUID(project_id)
    tasks = await get_tasks(db, _uuid.UUID(user_id), status=status, project_id=project_id)
    return {
        "tasks": [
            {
                "id": str(t.id),
                "title": t.title,
                "status": t.status,
                "priority": t.priority,
                "due_date": str(t.due_date) if t.due_date else None,
            }
            for t in tasks
        ]
    }


async def _execute_get_projects(db: AsyncSession, user_id: str, **kwargs) -> dict:
    from app.work.service import get_projects
    import uuid as _uuid
    projects = await get_projects(db, _uuid.UUID(user_id))
    return {
        "projects": [
            {
                "id": str(p.id),
                "name": p.name,
                "status": p.status,
                "deadline": str(p.deadline) if p.deadline else None,
            }
            for p in projects
        ]
    }


# ============================================================
# Registry
# ============================================================

TOOLS = [
    Tool(
        name="get_accounts",
        description="Pobiera listę wszystkich kont użytkownika wraz z aktualnymi saldami w PLN.",
        parameters={"type": "object", "properties": {}, "required": []},
        executor=_execute_get_accounts,
    ),
    Tool(
        name="get_financial_summary",
        description="Pobiera podsumowanie finansowe za bieżący miesiąc: salda kont, suma przychodów, suma wydatków, bilans netto.",
        parameters={"type": "object", "properties": {}, "required": []},
        executor=_execute_get_financial_summary,
    ),
    Tool(
        name="get_transactions",
        description="Pobiera ostatnie transakcje użytkownika. Można filtrować po typie (income/expense/transfer).",
        parameters={
            "type": "object",
            "properties": {
                "type": {"type": "string", "enum": ["income", "expense", "transfer"], "description": "Filtruj transakcje po typie"},
                "limit": {"type": "integer", "description": "Liczba transakcji do zwrócenia (domyślnie 20)"},
            },
            "required": [],
        },
        executor=_execute_get_transactions,
    ),
    Tool(
        name="get_today_schedule",
        description="Pobiera dzisiejszy harmonogram: zaplanowane bloki czasu (time blocks) i zadania do wykonania.",
        parameters={"type": "object", "properties": {}, "required": []},
        executor=_execute_get_today_schedule,
    ),
    Tool(
        name="get_tasks",
        description="Pobiera listę zadań użytkownika. Można filtrować po statusie (todo/in_progress/done/cancelled) i ID projektu.",
        parameters={
            "type": "object",
            "properties": {
                "status": {"type": "string", "enum": ["todo", "in_progress", "done", "cancelled"], "description": "Filtruj zadania po statusie"},
                "project_id": {"type": "string", "description": "UUID projektu do filtrowania zadań"},
            },
            "required": [],
        },
        executor=_execute_get_tasks,
    ),
    Tool(
        name="get_projects",
        description="Pobiera listę wszystkich projektów użytkownika z ich statusami.",
        parameters={"type": "object", "properties": {}, "required": []},
        executor=_execute_get_projects,
    ),
]


def get_tool_by_name(name: str) -> Tool | None:
    for tool in TOOLS:
        if tool.name == name:
            return tool
    return None


def get_openai_tools() -> list[dict]:
    return [tool.openai_schema for tool in TOOLS]
```

- [ ] **Step 2: Run existing advisor tests to verify no regressions**

```bash
cd backend && python -m pytest tests/test_advisor/ -v
```

- [ ] **Step 3: Commit**

```bash
git add backend/app/advisor/tools/registry.py
git commit -m "feat: unified tool registry with OpenAI schemas and 6 executors"
```

---

### Task 2: Modified send_message with tool calling loop

**Files:**
- Modify: `backend/app/advisor/service.py`
- Modify: `backend/app/advisor/schemas.py`

- [ ] **Step 1: Update schemas**

Add to `backend/app/advisor/schemas.py`:

```python
class ToolExecutionResponse(BaseModel):
    id: uuid.UUID
    tool_name: str
    arguments: dict | None = None
    result: dict | None = None
    status: str
    model_config = {"from_attributes": True}


class MessageResponse(BaseModel):
    id: uuid.UUID
    conversation_id: uuid.UUID
    role: str
    content: str | None = None
    tool_calls: list[dict] | None = None
    tool_executions: list[ToolExecutionResponse] | None = None
    created_at: dt.datetime
    model_config = {"from_attributes": True}
```

Note: READ the existing file first. Keep the existing schemas (ChatRequest, SendMessageRequest, ConversationResponse). Only modify MessageResponse by replacing it, and add ToolExecutionResponse.

- [ ] **Step 2: Rewrite send_message in service.py**

Replace the `send_message` function and SYSTEM_PROMPT in `backend/app/advisor/service.py`.

Add imports at top:
```python
import json
from app.advisor.models import Conversation, Message, ToolExecution
from app.advisor.tools.registry import get_openai_tools, get_tool_by_name
```

New SYSTEM_PROMPT:
```python
SYSTEM_PROMPT = """Jesteś osobistym doradcą. Pomagasz użytkownikowi zarządzać czasem, pieniędzmi i projektami.

Masz dostęp do narzędzi, które pozwalają Ci odczytywać dane użytkownika:
- get_accounts — lista kont z saldami
- get_financial_summary — podsumowanie finansowe za bieżący miesiąc
- get_transactions — lista transakcji (filtruj po type: income/expense/transfer)
- get_today_schedule — dzisiejszy kalendarz (time blocki) i zadania
- get_tasks — lista zadań (filtruj po status, project_id)
- get_projects — lista projektów z ich statusami

Zasady:
- Odpowiadasz po polsku, zwięźle i konkretnie
- ZAWSZE używasz narzędzi gdy użytkownik pyta o dane ze swojego konta
- Nigdy nie wymyślasz liczb — pobierasz je przez narzędzia
- Formatujesz kwoty czytelnie: "1 234,56 PLN" (nie "123456")
- Gdy użytkownik prosi o podsumowanie, użyj get_financial_summary
- Sugerujesz działania, ale nie podejmujesz decyzji za użytkownika
- Jesteś pomocny, ale nie nachalny"""
```

New send_message function (replaces lines 67-122):

```python
MAX_TOOL_ITERATIONS = 3


async def send_message(
    db: AsyncSession,
    user_id: uuid.UUID,
    conversation_id: uuid.UUID | None,
    content: str,
) -> Message:
    # Get or create conversation
    if conversation_id:
        conv = await get_conversation(db, user_id, conversation_id)
        if conv is None:
            conv = await create_conversation(db, user_id)
            conversation_id = conv.id
    else:
        conv = await create_conversation(db, user_id)
        conversation_id = conv.id

    # Save user message
    user_msg = Message(conversation_id=conversation_id, role="user", content=content)
    db.add(user_msg)
    await db.flush()

    # Build message history for LLM
    history = await get_conversation_messages(db, user_id, conversation_id)
    messages = [{"role": "system", "content": SYSTEM_PROMPT}]
    for msg in history:
        if msg.role == "tool":
            continue  # tool messages are re-added during the loop
        entry = {"role": msg.role, "content": msg.content}
        if msg.tool_calls:
            entry["tool_calls"] = msg.tool_calls
        messages.append(entry)

    client = _get_llm_client()
    tools = get_openai_tools()

    # Tool calling loop
    for iteration in range(MAX_TOOL_ITERATIONS):
        try:
            response = await client.chat.completions.create(
                model=settings.LLM_MODEL,
                messages=messages,
                tools=tools,
                tool_choice="auto",
                temperature=0.7,
                max_tokens=1024,
            )
        except Exception as e:
            assistant_msg = Message(
                conversation_id=conversation_id,
                role="assistant",
                content=f"Przepraszam, wystąpił błąd: {str(e)[:200]}",
            )
            db.add(assistant_msg)
            await db.flush()
            return assistant_msg

        choice = response.choices[0]
        msg = choice.message

        # If no tool calls, this is the final text response
        if not msg.tool_calls:
            assistant_msg = Message(
                conversation_id=conversation_id,
                role="assistant",
                content=msg.content or "",
            )
            db.add(assistant_msg)
            await db.flush()
            _update_conversation_title(conv, content, len(history))
            return assistant_msg

        # Save assistant message with tool_calls
        raw_tool_calls = [
            {
                "id": tc.id,
                "type": "function",
                "function": {"name": tc.function.name, "arguments": tc.function.arguments},
            }
            for tc in msg.tool_calls
        ]
        assistant_msg = Message(
            conversation_id=conversation_id,
            role="assistant",
            content=msg.content,
            tool_calls=raw_tool_calls,
        )
        db.add(assistant_msg)
        await db.flush()

        # Append assistant message to LLM history
        messages.append({
            "role": "assistant",
            "content": msg.content,
            "tool_calls": raw_tool_calls,
        })

        # Execute each tool call
        for tc in msg.tool_calls:
            tool_name = tc.function.name
            tool = get_tool_by_name(tool_name)

            try:
                arguments = json.loads(tc.function.arguments)
            except json.JSONDecodeError:
                arguments = {}

            if tool is None:
                result = {"error": f"Unknown tool: {tool_name}"}
                status = "error"
            else:
                try:
                    result = await tool.executor(db, str(user_id), **arguments)
                    status = "completed"
                except Exception as e:
                    result = {"error": str(e)}
                    status = "error"

            # Save tool execution
            tool_exec = ToolExecution(
                message_id=assistant_msg.id,
                tool_name=tool_name,
                arguments=arguments,
                result=result,
                status=status,
                autonomy_level=tool.autonomy_level,
            )
            db.add(tool_exec)

            # Add tool result to LLM history
            messages.append({
                "role": "tool",
                "tool_call_id": tc.id,
                "content": json.dumps(result, ensure_ascii=False, default=str),
            })

        await db.flush()

    # Max iterations reached — return last response as-is
    assistant_msg = Message(
        conversation_id=conversation_id,
        role="assistant",
        content="Przetworzyłem dane. Czy potrzebujesz dodatkowych informacji?",
    )
    db.add(assistant_msg)
    _update_conversation_title(conv, content, len(history))
    await db.flush()
    return assistant_msg


def _update_conversation_title(conv: Conversation, first_message: str, history_length: int):
    """Auto-title conversation from first user message."""
    if conv.title == "Nowa rozmowa" and history_length <= 1:
        title = first_message[:60] + ("..." if len(first_message) > 60 else "")
        conv.title = title
```

- [ ] **Step 3: Update router to include tool_executions in response**

In `backend/app/advisor/router.py`, the `send_message_endpoint` needs to eager-load `tool_executions`. Update the import to add `selectinload`:

```python
from sqlalchemy.orm import selectinload
```

And after saving the message, reload it with eager-loaded relationships. Add after the service call:
```python
    from sqlalchemy import select as sa_select
    from app.advisor.models import Message as MsgModel
    result = await db.execute(
        sa_select(MsgModel).options(
            selectinload(MsgModel.tool_executions)
        ).where(MsgModel.id == assistant_msg.id)
    )
    assistant_msg = result.scalar_one()
```

- [ ] **Step 4: Commit**

```bash
git add backend/app/advisor/service.py backend/app/advisor/schemas.py backend/app/advisor/router.py
git commit -m "feat: tool calling loop in Advisor — 6 read-only tools via OpenAI function calling"
```

---

### Task 3: Frontend — render tool calls

**Files:**
- Modify: `frontend/src/api/advisor.ts`
- Modify: `frontend/src/pages/Advisor.tsx`

- [ ] **Step 1: Update API types**

In `frontend/src/api/advisor.ts`, update the `Message` type:

```typescript
export interface ToolExecution {
  id: string;
  tool_name: string;
  arguments: Record<string, unknown> | null;
  result: Record<string, unknown> | null;
  status: string;
}

export interface Message {
  id: string;
  conversation_id: string;
  role: "user" | "assistant";
  content: string;
  tool_calls?: Array<{
    id: string;
    type: string;
    function: { name: string; arguments: string };
  }> | null;
  tool_executions?: ToolExecution[] | null;
  created_at: string;
}
```

- [ ] **Step 2: Add tool call rendering to Advisor page**

In `frontend/src/pages/Advisor.tsx`, add a `ToolCallBanner` component and render it between messages that have `tool_calls`:

```tsx
function ToolCallBanner({ message }: { message: Message }) {
  const [expanded, setExpanded] = useState(false);
  if (!message.tool_executions?.length) return null;

  return (
    <div className="my-2 mx-4">
      {message.tool_executions.map((te) => (
        <div key={te.id} className="bg-gray-800/50 border border-gray-700 rounded-lg text-sm">
          <button
            onClick={() => setExpanded(!expanded)}
            className="w-full flex items-center gap-2 px-3 py-2 text-gray-400 hover:text-gray-200 transition-colors"
          >
            <svg className={`w-3 h-3 transition-transform ${expanded ? "rotate-90" : ""}`} fill="currentColor" viewBox="0 0 20 20">
              <path fillRule="evenodd" d="M7.21 14.77a.75.75 0 01.02-1.06L11.168 10 7.23 6.29a.75.75 0 111.04-1.08l4.5 4.25a.75.75 0 010 1.08l-4.5 4.25a.75.75 0 01-1.06-.02z" clipRule="evenodd" />
            </svg>
            <span className="text-advisor-400">🔧 {te.tool_name}</span>
            <span className={te.status === "completed" ? "text-green-400" : "text-red-400"}>•</span>
          </button>
          {expanded && (
            <div className="px-3 pb-3 border-t border-gray-700/50">
              <pre className="mt-2 text-xs text-gray-400 whitespace-pre-wrap font-mono max-h-40 overflow-y-auto">
                {JSON.stringify(te.result, null, 2)}
              </pre>
            </div>
          )}
        </div>
      ))}
    </div>
  );
}
```

Then in the message rendering loop, after each message div, add:
```tsx
{msg.role === "assistant" && msg.tool_calls && msg.tool_calls.length > 0 && (
  <ToolCallBanner message={msg} />
)}
```

- [ ] **Step 3: Commit**

```bash
git add frontend/src/api/advisor.ts frontend/src/pages/Advisor.tsx
git commit -m "feat: render Advisor tool calls as expandable banners in chat"
```

---

### Task 4: Deploy and test

**Files:** None (operational)

- [ ] **Step 1: Restart backend**

```bash
cd /docker/finanse && docker compose restart backend
```

- [ ] **Step 2: Test tool calling E2E**

```bash
# Login, send a message that should trigger tools
curl -X POST https://finanse.birek.online/api/advisor/messages \
  -H "Content-Type: application/json" \
  -d '{"content": "Jakie mam saldo na kontach?"}' \
  -b "advisor_session=..."
```

Expected: response with tool_calls containing `get_accounts`, followed by financial summary text.

- [ ] **Step 3: Commit + push**

```bash
git push
```

- [ ] **Step 4: Update docs**

```bash
# Update TASKS.md, JOURNAL.md, CHANGELOG.md
```
