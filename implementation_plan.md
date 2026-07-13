# Multi-Agent Software Delivery Assistant — Alignment & Next.js Frontend

## Background

The problem statement describes a **Multi-Agent Software Delivery Assistant** — an enterprise-grade AI platform where specialized agents (Planner, Developer, Reviewer, Tester, Manager, Communicator) collaborate via LangGraph to automate the SDLC.

The current Python/FastAPI backend is already **very well-aligned** with the problem statement. It has:
- ✅ Supervisor agent deciding graph flow (like deep-agent in LangChain)
- ✅ Plan mode / Build mode (like opencode)
- ✅ Planner, Developer (module coder), Reviewer, Tester (QA), Manager (delivery/analysis report) agents
- ✅ LangGraph orchestration with parallel/sequential execution
- ✅ Human-in-the-loop approvals
- ✅ Interactive REPL + HTTP server (FastAPI)

## Gaps vs. Problem Statement

| Gap | Priority | What to do |
|-----|----------|------------|
| No explicit **Communicator/Manager agent** node returning progress updates to the frontend | High | Add `manager_node` streaming progress events + SSE endpoint |
| HTTP API only exposes `/run` and `/resume` — no **streaming** or **SSE** for real-time agent step events | High | Add `/stream` SSE endpoint that streams node events |
| No **project/thread management** endpoints (list projects, get history) | Medium | Add `/projects`, `/threads`, `/history` endpoints |
| Frontend is just a CLI/REPL, no Next.js app | High | Build a full Next.js 14 (App Router) frontend |
| No agent-specific status reporting (which agent is active, current task) | Medium | Emit agent-step events via SSE |
| Missing `Communicator Agent` role (though REPL/server does some of this) | Low | Wire communicator into server responses |

## Proposed Changes

---

### 1. Backend — Enhanced FastAPI Server (`assistant/server.py`)

#### [MODIFY] [server.py](file:///d:/Indium/ai-assistant/assistant/server.py)

- Add **SSE streaming endpoint** `/stream` that streams agent step events (agent name, status, partial output) using `text/event-stream`
- Add CORS middleware for the Next.js frontend (`localhost:3000`)
- Add `/threads` (list active threads) and `/history/{thread_id}` (get message history)
- Add `/projects` endpoint listing known project paths
- Return richer JSON with `agent_steps` array showing each agent's contribution

---

### 2. Backend — Manager Agent node (`agents.py` or new file)

#### [MODIFY] [agents.py](file:///d:/Indium/ai-assistant/agents.py)

- Add a **`manager_node`** that collects completed modules, test results, review scores, and produces a structured **progress report** (like the problem statement's Manager Agent dashboard)
- Wire it into `graph.py` after delivery

---

### 3. Backend — SSE Event Emitter (`assistant/events.py`) [NEW]

#### [NEW] events.py

- A lightweight pub-sub or queue-based event system so graph nodes can emit events (e.g., `{"agent": "planner", "status": "running", "message": "Analyzing requirements..."}`)
- Used by the `/stream` SSE endpoint to push real-time updates to the Next.js frontend

---

### 4. Frontend — Next.js 14 App Router Application

A brand-new Next.js 14 app in `frontend/` directory with:

#### Pages / Routes

| Route | Description |
|-------|-------------|
| `/` | Landing / Dashboard — shows recent projects, system status |
| `/chat` | Main AI chat interface — like VS Code Copilot / Antigravity |
| `/projects/[id]` | Project detail — generated files, modules, agent steps |
| `/analytics` | Manager Agent dashboard — charts for tasks, test results, reviews |

#### Key Components

- **`ChatPanel`** — VSCode-like chat sidebar with message history, streaming AI responses
- **`AgentTimeline`** — Real-time view of which agent is active (Planner → Developer → Reviewer → Tester → Manager)
- **`CodeViewer`** — Syntax-highlighted code viewer for generated files
- **`PlanReviewModal`** — Modal to approve/reject plans (opencode-style)
- **`ProjectExplorer`** — File tree of generated project
- **`ManagerDashboard`** — Cards showing task progress, module status, test results

#### Tech choices

- **Next.js 14** App Router
- **TypeScript**
- **Vanilla CSS** (custom design system — dark mode, glassmorphism)
- **Server-Sent Events** (native `EventSource` API) for real-time streaming
- **Google Fonts** — Inter

---

### 5. API Contract (Backend → Frontend)

#### `POST /run`
```json
{
  "message": "Build a Login API with JWT",
  "thread_id": "optional-thread-id",
  "project_path": "/path/to/project"
}
```
Response:
```json
{
  "status": "done",
  "thread_id": "srv-abc123",
  "reply": "Delivery complete. 5 modules, 18 files...",
  "agent_steps": [
    {"agent": "supervisor", "status": "done", "message": "Execution plan decided"},
    {"agent": "planner", "status": "done", "message": "6 modules planned"},
    ...
  ]
}
```

#### `GET /stream?thread_id=xxx`  (SSE)
Streams events:
```
event: agent_step
data: {"agent": "planner", "status": "running", "message": "Analyzing requirements..."}

event: agent_step  
data: {"agent": "developer", "status": "done", "message": "Module auth coded (score 8/10)"}

event: done
data: {"reply": "...", "thread_id": "..."}
```

#### `GET /history/{thread_id}`
Returns message history for a thread.

#### `GET /projects`
Returns list of known projects with their threads.

---

## Verification Plan

### Backend
- Run `uvicorn assistant.server:app --reload` and test all new endpoints with curl/Postman
- Test SSE with `curl -N http://localhost:8000/stream?thread_id=xxx`
- Ensure existing `/run` and `/resume` still work

### Frontend
- `npm run dev` and verify all pages render
- Test chat → SSE streaming → real-time agent timeline update
- Test plan approval modal flow
- Test on different screen sizes

## Open Questions

> [!IMPORTANT]
> **1. Next.js location**: Should the frontend be at `d:\Indium\ai-assistant\frontend\` (monorepo) or a separate directory?

> [!IMPORTANT]  
> **2. LLM Provider for the frontend API**: The backend currently talks to Ollama/LM Studio. Should the Next.js frontend connect directly to `localhost:8000` (FastAPI) or do you want Next.js API routes as a BFF (Backend for Frontend)?

> [!NOTE]
> **3. Authentication**: The problem statement mentions Role-Based Access Control. Should we stub out auth (JWT login page) or skip it for now?

> [!NOTE]
> **4. Database**: The problem statement mentions PostgreSQL for storing projects/tasks/logs. Should we add a database layer, or keep the current in-memory approach for now?
