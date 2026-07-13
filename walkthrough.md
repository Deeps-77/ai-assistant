# Walkthrough — AI Software Delivery Assistant Alignment

## What Was Built

### Backend Enhancements

#### `assistant/db.py` [NEW]
- **ChromaDB vector store** with 4 collections:
  - `threads` — conversation/run metadata keyed by thread_id
  - `projects` — project records keyed by project_path
  - `agent_steps` — per-run step events (timestamped, queryable)
  - `code_embeddings` — generated code chunks with semantic search via embeddings
- Functions: `save_thread`, `get_thread`, `list_threads`, `save_project`, `list_projects`, `append_agent_step`, `get_agent_steps`, `save_code_embedding`, `search_code`

#### `assistant/events.py` [NEW]
- **SSE event emitter** using `asyncio.Queue` per thread_id
- Functions: `emit_agent_step`, `emit_done`, `emit_error`, `emit_paused`
- `event_stream()` async generator that yields SSE-formatted strings
- Heartbeat to keep connections alive; automatic timeout after 300s

#### `assistant/server.py` [ENHANCED]
- **CORS middleware** allowing `localhost:3000` (Next.js dev)
- **`POST /run`** — enhanced with SSE event registration, ChromaDB persistence, `agent_steps` in response
- **`POST /resume`** — resumes paused threads, persists to ChromaDB
- **`GET /stream?thread_id=`** — SSE stream of real-time agent step events
- **`GET /history/{thread_id}`** — full thread metadata + agent steps from ChromaDB
- **`GET /threads`** — list recent threads
- **`GET /projects`** — list all known projects
- **`GET /search?q=`** — semantic code search via ChromaDB embeddings
- **`GET /health`** — returns backend + DB status
- Node-to-agent name mapping for human-readable SSE events
- Streaming via `agent.stream()` with per-node SSE emission

---

### Frontend — Next.js 14 App Router (`frontend/`)

#### Architecture
```
Next.js (localhost:3000)
  └── /api/* routes (BFF — no CORS)
        └── FastAPI (localhost:8000)
              └── ChromaDB (.chroma/)
```

#### Pages

| Page | Route | Description |
|------|-------|-------------|
| Dashboard | `/` | Status cards, agent pipeline visualization, recent projects & runs |
| Chat | `/chat` | VSCode/Copilot-style AI chat with streaming, agent timeline, plan mode |
| Projects | `/projects` | All projects and delivery run history |
| Analytics | `/analytics` | Manager Dashboard with KPIs, status breakdown, agent activity, runs table |

#### Key Components

- **`AgentTimeline`** — real-time step-by-step pipeline with colored agent icons, typing dots for running agent
- **`PlanReviewModal`** — opencode-style plan approval modal (approve → build, reject → feedback → regenerate)
- **`Sidebar`** — dark sidebar with gradient logo and active route highlighting
- **`TopBar`** — sticky header with title, subtitle, and actions slot

#### API Client (`app/lib/api.ts`)
- `runDelivery()`, `resumeDelivery()`, `getHistory()`, `getProjects()`, `getThreads()`, `getHealth()`
- `openStream()` — opens SSE `EventSource` and dispatches `onStep`, `onDone`, `onPaused`, `onError`

#### BFF Routes (`app/api/`)
- All routes proxy to `FASTAPI_URL` (default `http://127.0.0.1:8000`)
- `/api/stream` — proxies the SSE response body directly

---

## How to Run

### Backend
```bash
cd d:\Indium\ai-assistant

# Option 1: Interactive REPL
uv run python -m assistant.repl

# Option 2: HTTP server (needed for frontend)
uv run uvicorn assistant.server:app --host 127.0.0.1 --port 8000 --reload
```

### Frontend
```bash
cd d:\Indium\ai-assistant\frontend
npm run dev
# → http://localhost:3000
```

---

## Design System Highlights
- Dark mode (`#0a0a0f` background) with glassmorphism cards
- Agent-specific color tokens (`--agent-supervisor`, `--agent-planner`, etc.)
- `Inter` font + `JetBrains Mono` for code
- Micro-animations: `fadeUp`, `pulse`, `shimmer` skeleton, typing dots
- Responsive grid layouts collapsing on mobile

---

## Screenshots

![Dashboard](/C:/Users/deepa/.gemini/antigravity/brain/fa645385-f399-47f3-9f1a-38f7471e6461/home_page_1783958786210.png)
*Dashboard — Agent pipeline, status cards, recent projects*

![Chat Interface](/C:/Users/deepa/.gemini/antigravity/brain/fa645385-f399-47f3-9f1a-38f7471e6461/chat_page_1783958819810.png)
*Chat — Copilot-style interface with suggestion cards and Plan Mode toggle*

---

## Troubleshooting & Bug Fixes

### 1. Fixed KeyError: `'supervisor'` in `graph.py`
- **Issue**: In `update` mode, after `project_analyzer` node runs, `route_after_analyzer` returns `"supervisor"`. However, the conditional edge mapping on `project_analyzer` in `graph.py` mapped `"planner"` instead of `"supervisor"`. This mismatch caused a `KeyError: 'supervisor'` to be thrown, leading to connection lost errors on the UI.
- **Fix**: Replaced `"planner": "planner"` with `"supervisor": "supervisor"` in the conditional edge mapping for `project_analyzer` in `graph.py`.

### 2. Fixed Potential KeyError: `'delivery'` in `graph.py`
- **Issue**: When a user approved the plan and `skip_tests` was enabled (e.g. via a plan-only request), `route_after_human` returned `"delivery"`. However, the `"delivery"` route was not mapped in the `"human_review"` conditional edge mapping, which would cause a `KeyError: 'delivery'`.
- **Fix**: Added `"delivery": "delivery"` to the `"human_review"` conditional edge mapping in `graph.py`.

