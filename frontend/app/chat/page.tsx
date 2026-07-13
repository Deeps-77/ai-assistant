"use client";

import { useState, useRef, useEffect, useCallback } from "react";
import Sidebar from "../components/Sidebar";
import TopBar from "../components/TopBar";
import AgentTimeline, { AgentStep } from "../components/AgentTimeline";
import PlanReviewModal from "../components/PlanReviewModal";
import { runDelivery, openStream, resumeDelivery } from "../lib/api";
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

export default function ChatPage() {
  const [messages, setMessages] = useState<Message[]>([]);
  const [input, setInput] = useState("");
  const [isRunning, setIsRunning] = useState(false);
  const [currentAgent, setCurrentAgent] = useState<string>("");
  const [liveSteps, setLiveSteps] = useState<AgentStep[]>([]);
  const [planModal, setPlanModal] = useState<{ threadId: string; plan: string } | null>(null);
  const [planMode, setPlanMode] = useState(false);
  const [projectPath, setProjectPath] = useState("");
  const messagesEndRef = useRef<HTMLDivElement>(null);
  const closeStream = useRef<(() => void) | null>(null);

  useEffect(() => { messagesEndRef.current?.scrollIntoView({ behavior: "smooth" }); }, [messages]);

  const pushMsg = useCallback((msg: Message) => setMessages((p) => [...p, msg]), []);
  const appendSteps = useCallback((steps: AgentStep[]) => setLiveSteps((p) => [...p, ...steps]), []);

  const handleSend = useCallback(async () => {
    const text = input.trim();
    if (!text || isRunning) return;
    setInput("");
    setIsRunning(true);
    setLiveSteps([]);
    setCurrentAgent("Supervisor");
    const userMsg: Message = { id: uid(), role: "user", content: text };
    pushMsg(userMsg);

    // Determine thread id upfront so we can open SSE before /run returns
    const threadId = `chat-${Date.now().toString(36)}`;

    // Open SSE stream first
    closeStream.current = openStream(threadId, {
      onStep: (step) => {
        setCurrentAgent(step.agent);
        setLiveSteps((p) => [...p, step]);
      },
      onDone: (data) => {
        setIsRunning(false);
        setCurrentAgent("");
        const reply: Message = {
          id: uid(),
          role: "assistant",
          content: data.reply || "Delivery complete.",
          steps: data.agent_steps,
          threadId,
        };
        setMessages((p) => [...p, reply]);
        setLiveSteps([]);
      },
      onPaused: (data) => {
        const intr = (data.interrupts as { plan?: string }[])[0];
        const planText = intr?.plan || JSON.stringify(intr, null, 2);
        setPlanModal({ threadId, plan: planText });
        setIsRunning(false);
        setCurrentAgent("");
      },
      onError: (msg) => {
        setIsRunning(false);
        setCurrentAgent("");
        pushMsg({ id: uid(), role: "system", content: `⚠ ${msg}` });
      },
    });

    try {
      await runDelivery(text, threadId, projectPath || undefined, planMode);
    } catch (e) {
      setIsRunning(false);
      setCurrentAgent("");
      pushMsg({ id: uid(), role: "system", content: `⚠ Could not reach backend. Is it running at port 8000?` });
    }
  }, [input, isRunning, planMode, projectPath, pushMsg]);

  const handleApprove = async () => {
    if (!planModal) return;
    setPlanModal(null);
    setIsRunning(true);
    setCurrentAgent("Developer");

    closeStream.current = openStream(planModal.threadId, {
      onStep: (step) => { setCurrentAgent(step.agent); setLiveSteps((p) => [...p, step]); },
      onDone: (data) => {
        setIsRunning(false);
        setCurrentAgent("");
        pushMsg({ id: uid(), role: "assistant", content: data.reply || "Build complete.", steps: data.agent_steps, threadId: planModal.threadId });
        setLiveSteps([]);
      },
      onPaused: () => { setIsRunning(false); },
      onError: (msg) => { setIsRunning(false); pushMsg({ id: uid(), role: "system", content: `⚠ ${msg}` }); },
    });

    await resumeDelivery(planModal.threadId, [{ choice: "yes", feedback: "" }]);
  };

  const handleReject = async (feedback: string) => {
    if (!planModal) return;
    setPlanModal(null);
    await resumeDelivery(planModal.threadId, [{ choice: "no", feedback }]);
    pushMsg({ id: uid(), role: "system", content: "Plan rejected. Regenerating with your feedback…" });
  };

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); handleSend(); }
  };

  return (
    <div className="layout">
      <Sidebar />
      <div className="main-content">
        <TopBar
          title="Chat"
          subtitle="Multi-agent software delivery"
          actions={
            <div className={styles.topActions}>
              <button
                className={`btn ${planMode ? "btn-primary" : "btn-ghost"}`}
                onClick={() => setPlanMode((p) => !p)}
                title="Toggle plan mode (approve plan before building)"
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

      {planModal && (
        <PlanReviewModal plan={planModal.plan} onApprove={handleApprove} onReject={handleReject} />
      )}
    </div>
  );
}
