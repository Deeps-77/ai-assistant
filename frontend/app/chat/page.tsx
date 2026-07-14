"use client";

import { useState, useRef, useEffect, useCallback, Suspense } from "react";
import { useSearchParams } from "next/navigation";
import Sidebar from "../components/Sidebar";
import TopBar from "../components/TopBar";
import AgentTimeline, { AgentStep } from "../components/AgentTimeline";
import PlanReviewModal from "../components/PlanReviewModal";
import HumanReviewModal from "../components/HumanReviewModal";
import FileReviewModal from "../components/FileReviewModal";
import { runDelivery, openStream, resumeDelivery, getHistory } from "../lib/api";
import styles from "./page.module.css";

type Role = "user" | "assistant" | "system";
interface Message { id: string; role: Role; content: string; steps?: AgentStep[]; threadId?: string; }

const SUGGESTIONS = [
  "Build a Login API with JWT authentication",
  "Create a user management microservice with CRUD operations",
  "Analyze the current project structure and suggest improvements",
  "Build a REST API for a todo application with PostgreSQL",
];

let msgCounter = 0;
const uid = () => `m${++msgCounter}`;

function ChatContent() {
  const [messages, setMessages] = useState<Message[]>([]);
  const [input, setInput] = useState("");
  const [isRunning, setIsRunning] = useState(false);
  const [currentAgent, setCurrentAgent] = useState<string>("");
  const [liveSteps, setLiveSteps] = useState<AgentStep[]>([]);
  const [interruptModal, setInterruptModal] = useState<{ type: string; threadId: string; data: any } | null>(null);
  const [planMode, setPlanMode] = useState(false);
  const [projectPath, setProjectPath] = useState("");
  const messagesEndRef = useRef<HTMLDivElement>(null);
  const closeStream = useRef<(() => void) | null>(null);

  const searchParams = useSearchParams();
  const queryThreadId = searchParams.get("thread_id");

  useEffect(() => { messagesEndRef.current?.scrollIntoView({ behavior: "smooth" }); }, [messages]);

  const pushMsg = useCallback((msg: Message) => setMessages((p) => [...p, msg]), []);

  const connectStream = useCallback((threadId: string) => {
    setIsRunning(true);
    setLiveSteps([]);
    setCurrentAgent("Supervisor");

    if (closeStream.current) {
      closeStream.current();
    }

    closeStream.current = openStream(threadId, {
      onStep: (step) => {
        setCurrentAgent(step.agent);
        setLiveSteps((p) => [...p, step]);
      },
      onDone: (data) => {
        setIsRunning(false);
        setCurrentAgent("");
        setMessages((p) => [
          ...p,
          {
            id: uid(),
            role: "assistant",
            content: data.reply || "Delivery complete.",
            steps: data.agent_steps,
            threadId,
          },
        ]);
        setLiveSteps([]);
      },
      onPaused: (data) => {
        setIsRunning(false);
        setCurrentAgent("");
        const intr = (data.interrupts as any[])[0];
        if (intr) {
          setInterruptModal({ type: intr.type, threadId, data: intr });
        }
      },
      onError: (msg) => {
        setIsRunning(false);
        setCurrentAgent("");
        setMessages((p) => [
          ...p,
          { id: uid(), role: "system", content: `⚠ ${msg}` },
        ]);
      },
    });
  }, []);

  // Load thread history on mount or when queryThreadId changes
  useEffect(() => {
    if (!queryThreadId) {
      setMessages([]);
      setLiveSteps([]);
      setIsRunning(false);
      setInterruptModal(null);
      return;
    }

    let active = true;

    async function loadThread() {
      try {
        const history = await getHistory(queryThreadId);
        if (!active) return;

        const metadata = history.metadata || {};
        const steps = history.agent_steps || [];

        const loadedMessages: Message[] = [];
        if (metadata.message) {
          loadedMessages.push({
            id: "user-msg",
            role: "user",
            content: metadata.message,
          });
        }

        if (metadata.reply) {
          loadedMessages.push({
            id: "assistant-reply",
            role: "assistant",
            content: metadata.reply,
            steps: steps,
          });
        }

        setMessages(loadedMessages);
        setLiveSteps(steps);
        setProjectPath(metadata.project_path || "");
        setPlanMode(metadata.plan_mode ?? false);

        if (metadata.status === "paused" && metadata.interrupts && metadata.interrupts.length > 0) {
          const intr = metadata.interrupts[0];
          setInterruptModal({
            type: intr.type,
            threadId: queryThreadId,
            data: intr,
          });
        }

        if (metadata.status === "running") {
          connectStream(queryThreadId);
        }
      } catch (err) {
        console.error("Failed to load thread history:", err);
      }
    }

    loadThread();

    return () => {
      active = false;
      if (closeStream.current) {
        closeStream.current();
      }
    };
  }, [queryThreadId, connectStream]);

  const handleSend = useCallback(async () => {
    const text = input.trim();
    if (!text || isRunning) return;
    setInput("");
    
    // Determine thread id upfront
    const threadId = queryThreadId || `chat-${Date.now().toString(36)}`;
    
    const userMsg: Message = { id: uid(), role: "user", content: text };
    pushMsg(userMsg);
    connectStream(threadId);

    try {
      await runDelivery(text, threadId, projectPath || undefined, planMode);
    } catch (e) {
      setIsRunning(false);
      setCurrentAgent("");
      pushMsg({ id: uid(), role: "system", content: `⚠ Could not reach backend. Is it running at port 8000?` });
    }
  }, [input, isRunning, planMode, projectPath, pushMsg, connectStream, queryThreadId]);

  const handleApprove = useCallback(async () => {
    if (!interruptModal) return;
    const threadId = interruptModal.threadId;
    setInterruptModal(null);
    connectStream(threadId);
    try {
      await resumeDelivery(threadId, [{ choice: "yes", feedback: "" }]);
    } catch (e) {
      console.error(e);
      setIsRunning(false);
      setCurrentAgent("");
    }
  }, [interruptModal, connectStream]);

  const handleReject = useCallback(async (feedback: string) => {
    if (!interruptModal) return;
    const threadId = interruptModal.threadId;
    setInterruptModal(null);
    connectStream(threadId);
    try {
      await resumeDelivery(threadId, [{ choice: "no", feedback }]);
    } catch (e) {
      console.error(e);
      setIsRunning(false);
      setCurrentAgent("");
    }
  }, [interruptModal, connectStream]);

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); handleSend(); }
  };

  return (
    <div className="layout">
      <Sidebar />
      <div className="main-content">
        <TopBar
          title="Chat"
          subtitle={queryThreadId ? `Viewing run ${queryThreadId}` : "Multi-agent software delivery"}
          actions={
            <div className={styles.topActions}>
              <button
                className={`btn ${planMode ? "btn-primary" : "btn-ghost"}`}
                onClick={() => setPlanMode((p) => !p)}
                title="Toggle plan mode (approve plan before building)"
                disabled={isRunning}
              >
                📋 {planMode ? "Plan Mode ON" : "Plan Mode"}
              </button>
            </div>
          }
        />
        <div className={styles.chatLayout}>
          {/* Messages */}
          <div className={styles.messagesArea}>
            {messages.length === 0 && !isRunning && (
              <div className={styles.empty}>
                <div className={styles.emptyIcon}>⬡</div>
                <h2 className="gradient-text" style={{ fontSize: 22, fontWeight: 700 }}>AI Software Delivery Assistant</h2>
                <p className={styles.emptySubtitle}>Describe a requirement and your multi-agent team will plan, build, review, and test it.</p>
                <div className={styles.suggestions}>
                  {SUGGESTIONS.map((s) => (
                    <button key={s} className={`card ${styles.suggestion}`} onClick={() => { setInput(s); }}>
                      {s}
                    </button>
                  ))}
                </div>
              </div>
            )}
            {messages.map((m) => (
              <div key={m.id} className={`${styles.message} ${styles[m.role]} fade-up`}>
                {m.role === "assistant" && <div className={styles.avatarAI}>⬡</div>}
                {m.role === "user" && <div className={styles.avatarUser}>U</div>}
                <div className={styles.bubble}>
                  <p className={styles.msgContent}>{m.content}</p>
                  {m.steps && m.steps.length > 0 && (
                    <details className={styles.stepsDetails}>
                      <summary>{m.steps.length} agent steps</summary>
                      <div style={{ marginTop: 12 }}>
                        <AgentTimeline steps={m.steps} />
                      </div>
                    </details>
                  )}
                </div>
              </div>
            ))}
            {isRunning && (
              <div className={`${styles.message} ${styles.assistant} fade-up`}>
                <div className={styles.avatarAI}>⬡</div>
                <div className={styles.bubble}>
                  <div className={styles.thinkingDots}><span /><span /><span /></div>
                </div>
              </div>
            )}
            <div ref={messagesEndRef} />
          </div>

          {/* Right panel: agent timeline */}
          <div className={styles.sidePanel}>
            <AgentTimeline steps={liveSteps} isRunning={isRunning} currentAgent={currentAgent} />
          </div>
        </div>

        {/* Input */}
        <div className={styles.inputArea}>
          <div className={styles.inputRow}>
            <input
              className={styles.projectInput}
              placeholder="Project path (optional)"
              value={projectPath}
              onChange={(e) => setProjectPath(e.target.value)}
              disabled={isRunning || !!queryThreadId}
            />
          </div>
          <div className={styles.inputBox}>
            <textarea
              className={styles.textarea}
              placeholder="Describe your requirement…  (Enter to send, Shift+Enter for newline)"
              value={input}
              onChange={(e) => setInput(e.target.value)}
              onKeyDown={handleKeyDown}
              rows={3}
              disabled={isRunning}
            />
            <button className={`btn btn-primary ${styles.sendBtn}`} onClick={handleSend} disabled={isRunning || !input.trim()}>
              {isRunning ? "⟳" : "↑"}
            </button>
          </div>
          <p className={styles.hint}>
            {planMode ? "📋 Plan mode: the assistant will pause for your approval before building." : "⚡ Build mode: the assistant builds immediately."}
          </p>
        </div>
      </div>

      {interruptModal && interruptModal.type === "plan_review" && (
        <PlanReviewModal plan={interruptModal.data?.plan || JSON.stringify(interruptModal.data, null, 2)} onApprove={handleApprove} onReject={handleReject} />
      )}
      {interruptModal && interruptModal.type === "human_review" && (
        <HumanReviewModal data={interruptModal.data} onApprove={handleApprove} onReject={handleReject} />
      )}
      {interruptModal && interruptModal.type === "file_review" && (
        <FileReviewModal data={interruptModal.data} onApprove={handleApprove} onReject={handleReject} />
      )}
    </div>
  );
}

export default function ChatPage() {
  return (
    <Suspense fallback={
      <div className="layout">
        <Sidebar />
        <div className="main-content">
          <div style={{ display: "flex", justifyContent: "center", alignItems: "center", height: "100%" }}>
            <p>Loading Chat Session...</p>
          </div>
        </div>
      </div>
    }>
      <ChatContent />
    </Suspense>
  );
}
