"use client";
import styles from "./AgentTimeline.module.css";

export interface AgentStep {
  agent: string;
  status: "running" | "done" | "error";
  message: string;
  timestamp?: number;
}

const AGENT_COLORS: Record<string, string> = {
  Supervisor: "var(--agent-supervisor)",
  Planner: "var(--agent-planner)",
  Architect: "var(--agent-architect)",
  Developer: "var(--agent-developer)",
  Coder: "var(--agent-developer)",
  Reviewer: "var(--agent-reviewer)",
  Tester: "var(--agent-tester)",
  Manager: "var(--agent-manager)",
  "File Writer": "var(--agent-manager)",
  Delivery: "var(--agent-manager)",
  QA: "var(--agent-tester)",
};

const AGENT_ICONS: Record<string, string> = {
  Supervisor: "🎯",
  Planner: "📋",
  Architect: "🏗️",
  Developer: "💻",
  Coder: "💻",
  Reviewer: "🔍",
  Tester: "🧪",
  Manager: "📊",
  QA: "✅",
  "File Writer": "💾",
  "Plan Review": "📝",
};

interface Props {
  steps: AgentStep[];
  isRunning?: boolean;
  currentAgent?: string;
}

export default function AgentTimeline({ steps, isRunning, currentAgent }: Props) {
  if (!steps.length && !isRunning) return null;

  return (
    <div className={styles.timeline}>
      <p className="section-title">Agent Pipeline</p>
      <div className={styles.steps}>
        {steps.map((step, i) => {
          const color = AGENT_COLORS[step.agent] || "var(--accent)";
          const icon = AGENT_ICONS[step.agent] || "⚡";
          return (
            <div key={i} className={`${styles.step} fade-up`} style={{ animationDelay: `${i * 0.04}s` }}>
              <div className={styles.iconWrap} style={{ borderColor: color, boxShadow: `0 0 8px ${color}40` }}>
                <span className={styles.icon}>{icon}</span>
              </div>
              <div className={styles.connector} style={{ background: color }} />
              <div className={styles.content}>
                <div className={styles.header}>
                  <span className={styles.agentName} style={{ color }}>{step.agent}</span>
                  <span className={`badge ${step.status === "done" ? "badge-success" : step.status === "error" ? "badge-error" : "badge-info"}`}>
                    {step.status === "done" ? "✓ Done" : step.status === "error" ? "✗ Error" : "⟳ Running"}
                  </span>
                </div>
                <p className={styles.message}>{step.message}</p>
              </div>
            </div>
          );
        })}
        {isRunning && currentAgent && (
          <div className={`${styles.step} ${styles.running}`}>
            <div className={styles.iconWrap} style={{ borderColor: "var(--accent)", boxShadow: "0 0 12px var(--accent-glow)" }}>
              <span className={styles.icon} style={{ animation: "spin 1s linear infinite" }}>⟳</span>
            </div>
            <div className={styles.content}>
              <div className={styles.header}>
                <span className={styles.agentName} style={{ color: "var(--accent)" }}>{currentAgent}</span>
                <span className="badge badge-accent">Running…</span>
              </div>
              <div className={styles.typingDots}>
                <span /><span /><span />
              </div>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
