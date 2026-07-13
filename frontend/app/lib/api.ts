// Frontend API client — calls Next.js BFF routes

const BASE = "/api";

export interface AgentStep {
  agent: string;
  status: "running" | "done" | "error";
  message: string;
  timestamp?: number;
}

export interface RunResponse {
  status: string;
  thread_id: string;
  reply: string;
  agent_steps: AgentStep[];
}

export interface PausedResponse {
  status: "paused";
  thread_id: string;
  interrupts: unknown[];
}

export async function runDelivery(message: string, threadId?: string, projectPath?: string, planMode?: boolean): Promise<RunResponse | PausedResponse> {
  const res = await fetch(`${BASE}/run`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ message, thread_id: threadId, project_path: projectPath, plan_mode: planMode ?? false }),
  });
  return res.json();
}

export async function resumeDelivery(threadId: string, decisions: unknown[]) {
  const res = await fetch(`${BASE}/resume`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ thread_id: threadId, decisions }),
  });
  return res.json();
}

export async function getHistory(threadId: string) {
  const res = await fetch(`${BASE}/history/${threadId}`);
  return res.json();
}

export async function getProjects() {
  const res = await fetch(`${BASE}/projects`);
  return res.json();
}

export async function getThreads() {
  const res = await fetch(`${BASE}/threads`);
  return res.json();
}

export async function getHealth() {
  try {
    const res = await fetch(`${BASE}/health`);
    return res.json();
  } catch {
    return { status: "offline" };
  }
}

/** Open an SSE connection to stream agent steps */
export function openStream(threadId: string, handlers: {
  onStep: (step: AgentStep) => void;
  onDone: (data: { reply: string; agent_steps: AgentStep[] }) => void;
  onPaused: (data: { interrupts: unknown[] }) => void;
  onError: (msg: string) => void;
}): () => void {
  const es = new EventSource(`${BASE}/stream?thread_id=${encodeURIComponent(threadId)}`);

  es.addEventListener("agent_step", (e) => {
    try { handlers.onStep(JSON.parse(e.data)); } catch {}
  });
  es.addEventListener("done", (e) => {
    try { handlers.onDone(JSON.parse(e.data)); } catch {}
    es.close();
  });
  es.addEventListener("paused", (e) => {
    try { handlers.onPaused(JSON.parse(e.data)); } catch {}
    es.close();
  });
  es.addEventListener("error", (e: MessageEvent) => {
    try { handlers.onError(JSON.parse(e.data).message); } catch { handlers.onError("Stream error"); }
    es.close();
  });
  es.onerror = () => { handlers.onError("Connection lost"); es.close(); };

  return () => es.close();
}
