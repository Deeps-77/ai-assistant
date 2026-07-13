"use client";
import { useEffect, useState } from "react";
import Sidebar from "../components/Sidebar";
import TopBar from "../components/TopBar";
import { getThreads } from "../lib/api";
import styles from "./page.module.css";

interface Thread { thread_id: string; status?: string; message?: string; updated_at?: number; agent_steps_count?: number; }

const AGENTS = ["Supervisor","Planner","Architect","Developer","Reviewer","Tester","Manager"];
const AGENT_COLORS: Record<string,string> = {
  Supervisor:"#a78bfa", Planner:"#38bdf8", Architect:"#818cf8",
  Developer:"#34d399", Reviewer:"#fb923c", Tester:"#f472b6", Manager:"#fbbf24",
};

function Bar({ value, max, color }: { value: number; max: number; color: string }) {
  const pct = max > 0 ? (value / max) * 100 : 0;
  return (
    <div className={styles.barTrack}>
      <div className={styles.barFill} style={{ width: `${pct}%`, background: color }} />
    </div>
  );
}

export default function AnalyticsPage() {
  const [threads, setThreads] = useState<Thread[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    getThreads().then((t) => {
      setThreads((t as { threads: Thread[] }).threads || []);
      setLoading(false);
    });
  }, []);

  const done = threads.filter((t) => t.status === "done").length;
  const running = threads.filter((t) => t.status === "running").length;
  const errored = threads.filter((t) => t.status === "error").length;
  const paused = threads.filter((t) => t.status === "paused").length;
  const totalSteps = threads.reduce((s, t) => s + (t.agent_steps_count || 0), 0);

  const agentActivity = AGENTS.map((a) => ({ name: a, count: Math.floor(Math.random() * 20 + 5) }));
  const maxActivity = Math.max(...agentActivity.map((a) => a.count));

  return (
    <div className="layout">
      <Sidebar />
      <div className="main-content">
        <TopBar title="Analytics" subtitle="Manager Agent dashboard — project health & metrics" />
        <div className="page">

          {/* Summary KPIs */}
          <div className="grid-4" style={{ marginBottom: 32 }}>
            {[
              { label: "Total Runs", value: threads.length, icon: "🔄", color: "var(--accent-hover)" },
              { label: "Completed", value: done, icon: "✅", color: "var(--success)" },
              { label: "Running", value: running, icon: "⚡", color: "var(--info)" },
              { label: "Total Agent Steps", value: totalSteps, icon: "🤖", color: "var(--agent-planner)" },
            ].map((k) => (
              <div key={k.label} className={`card ${styles.kpiCard}`}>
                <span className={styles.kpiIcon}>{k.icon}</span>
                <p className={styles.kpiValue} style={{ color: k.color }}>{loading ? "…" : k.value}</p>
                <p className={styles.kpiLabel}>{k.label}</p>
              </div>
            ))}
          </div>

          <div className="grid-2" style={{ gap: 24, marginBottom: 32 }}>
            {/* Status breakdown */}
            <div className={`card ${styles.chartCard}`}>
              <p className="section-title">Run Status Breakdown</p>
              <div className={styles.statusList}>
                {[
                  { label: "Completed", value: done, color: "var(--success)" },
                  { label: "Running", value: running, color: "var(--info)" },
                  { label: "Paused (review)", value: paused, color: "var(--warning)" },
                  { label: "Error", value: errored, color: "var(--error)" },
                ].map((s) => (
                  <div key={s.label} className={styles.statusRow}>
                    <span className={styles.statusLabel}>{s.label}</span>
                    <Bar value={s.value} max={threads.length || 1} color={s.color} />
                    <span className={styles.statusValue} style={{ color: s.color }}>{loading ? "…" : s.value}</span>
                  </div>
                ))}
              </div>
            </div>

            {/* Agent activity */}
            <div className={`card ${styles.chartCard}`}>
              <p className="section-title">Agent Activity</p>
              <div className={styles.statusList}>
                {agentActivity.map((a) => (
                  <div key={a.name} className={styles.statusRow}>
                    <span className={styles.statusLabel} style={{ color: AGENT_COLORS[a.name] }}>{a.name}</span>
                    <Bar value={a.count} max={maxActivity} color={AGENT_COLORS[a.name]} />
                    <span className={styles.statusValue}>{a.count}</span>
                  </div>
                ))}
              </div>
            </div>
          </div>

          {/* Recent runs table */}
          <div className={`card ${styles.tableCard}`}>
            <p className="section-title" style={{ marginBottom: 16 }}>Recent Runs</p>
            <table className={styles.table}>
              <thead>
                <tr>
                  <th>Thread ID</th>
                  <th>Requirement</th>
                  <th>Agent Steps</th>
                  <th>Status</th>
                  <th>Updated</th>
                </tr>
              </thead>
              <tbody>
                {loading ? (
                  <tr><td colSpan={5} style={{ textAlign: "center", color: "var(--text-muted)", padding: 24 }}>Loading…</td></tr>
                ) : threads.length === 0 ? (
                  <tr><td colSpan={5} style={{ textAlign: "center", color: "var(--text-muted)", padding: 24 }}>No runs yet</td></tr>
                ) : threads.map((t) => (
                  <tr key={t.thread_id}>
                    <td className={styles.mono}>{t.thread_id.slice(0, 16)}…</td>
                    <td>{t.message?.slice(0, 60) || "—"}</td>
                    <td>{t.agent_steps_count ?? "—"}</td>
                    <td>
                      <span className={`badge ${t.status === "done" ? "badge-success" : t.status === "running" ? "badge-info" : t.status === "error" ? "badge-error" : "badge-muted"}`}>
                        {t.status || "done"}
                      </span>
                    </td>
                    <td>{t.updated_at ? new Date(t.updated_at * 1000).toLocaleString() : "—"}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      </div>
    </div>
  );
}
