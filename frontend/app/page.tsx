"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import Sidebar from "./components/Sidebar";
import TopBar from "./components/TopBar";
import { getHealth, getProjects, getThreads } from "./lib/api";
import styles from "./page.module.css";

interface Project { project_path: string; name?: string; status?: string; updated_at?: number; thread_id?: string; }
interface Thread { thread_id: string; status?: string; message?: string; updated_at?: number; }

const AGENT_PIPELINE = [
  { name: "Supervisor", icon: "🎯", color: "var(--agent-supervisor)", desc: "Decides execution plan & flow" },
  { name: "Planner", icon: "📋", color: "var(--agent-planner)", desc: "Breaks requirement into modules" },
  { name: "Architect", icon: "🏗️", color: "var(--agent-architect)", desc: "Designs system architecture" },
  { name: "Developer", icon: "💻", color: "var(--agent-developer)", desc: "Generates production-ready code" },
  { name: "Reviewer", icon: "🔍", color: "var(--agent-reviewer)", desc: "Code quality & security review" },
  { name: "Tester", icon: "🧪", color: "var(--agent-tester)", desc: "Generates & runs test suites" },
  { name: "Manager", icon: "📊", color: "var(--agent-manager)", desc: "Tracks progress & delivers" },
];

export default function Dashboard() {
  const [health, setHealth] = useState<{ status: string; db: string } | null>(null);
  const [projects, setProjects] = useState<Project[]>([]);
  const [threads, setThreads] = useState<Thread[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    Promise.all([getHealth(), getProjects(), getThreads()]).then(([h, p, t]) => {
      setHealth(h);
      setProjects((p as { projects: Project[] }).projects || []);
      setThreads((t as { threads: Thread[] }).threads?.slice(0, 5) || []);
      setLoading(false);
    });
  }, []);

  return (
    <div className="layout">
      <Sidebar />
      <div className="main-content">
        <TopBar
          title="Dashboard"
          subtitle="Multi-Agent Software Delivery Platform"
          actions={
            <Link href="/chat" className="btn btn-primary">
              + New Delivery
            </Link>
          }
        />
        <div className="page">
          {/* Status Cards */}
          <div className={`grid-4 ${styles.statRow}`}>
            {[
              { label: "Backend", value: health?.status || "—", icon: "⬡", ok: health?.status === "ok" },
              { label: "Database", value: health?.db || "—", icon: "🗄️", ok: health?.db === "chromadb" },
              { label: "Projects", value: loading ? "…" : projects.length.toString(), icon: "📁", ok: true },
              { label: "Recent Runs", value: loading ? "…" : threads.length.toString(), icon: "🔄", ok: true },
            ].map((s) => (
              <div key={s.label} className={`card ${styles.statCard}`}>
                <div className={styles.statIcon}>{s.icon}</div>
                <div>
                  <p className={styles.statLabel}>{s.label}</p>
                  <p className={styles.statValue} style={{ color: s.ok ? "var(--success)" : "var(--warning)" }}>{s.value}</p>
                </div>
              </div>
            ))}
          </div>

          {/* Agent Pipeline */}
          <section className={styles.section}>
            <p className="section-title">Agent Pipeline</p>
            <div className={styles.pipelineRow}>
              {AGENT_PIPELINE.map((a, i) => (
                <div key={a.name} className={`card ${styles.agentCard}`}>
                  <div className={styles.agentIcon} style={{ background: `${a.color}20`, border: `1px solid ${a.color}40` }}>
                    {a.icon}
                  </div>
                  <p className={styles.agentName} style={{ color: a.color }}>{a.name}</p>
                  <p className={styles.agentDesc}>{a.desc}</p>
                  {i < AGENT_PIPELINE.length - 1 && <div className={styles.arrow}>→</div>}
                </div>
              ))}
            </div>
          </section>

          <div className="grid-2" style={{ gap: 24 }}>
            {/* Recent Projects */}
            <section className={styles.section}>
              <p className="section-title">Recent Projects</p>
              {loading ? (
                <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
                  {[1, 2, 3].map((i) => <div key={i} className="skeleton" style={{ height: 56 }} />)}
                </div>
              ) : projects.length === 0 ? (
                <div className={`card ${styles.emptyCard}`}>No projects yet. <Link href="/chat" className={styles.link}>Start a delivery →</Link></div>
              ) : (
                <div className={styles.listCards}>
                  {projects.slice(0, 6).map((p) => (
                    <div key={p.project_path} className={`card ${styles.listCard}`}>
                      <span className={styles.listIcon}>📁</span>
                      <div className={styles.listInfo}>
                        <p className={styles.listTitle}>{p.name || p.project_path.split(/[\\/]/).pop()}</p>
                        <p className={styles.listSub}>{p.project_path}</p>
                      </div>
                      <span className={`badge ${p.status === "active" ? "badge-success" : "badge-muted"}`}>{p.status || "done"}</span>
                    </div>
                  ))}
                </div>
              )}
            </section>

            {/* Recent Runs */}
            <section className={styles.section}>
              <p className="section-title">Recent Runs</p>
              {loading ? (
                <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
                  {[1, 2, 3].map((i) => <div key={i} className="skeleton" style={{ height: 56 }} />)}
                </div>
              ) : threads.length === 0 ? (
                <div className={`card ${styles.emptyCard}`}>No runs yet.</div>
              ) : (
                <div className={styles.listCards}>
                  {threads.map((t) => (
                    <div key={t.thread_id} className={`card ${styles.listCard}`}>
                      <span className={styles.listIcon}>🔄</span>
                      <div className={styles.listInfo}>
                        <p className={styles.listTitle}>{t.message?.slice(0, 50) || t.thread_id}</p>
                        <p className={styles.listSub}>{t.thread_id}</p>
                      </div>
                      <span className={`badge ${t.status === "done" ? "badge-success" : t.status === "running" ? "badge-info" : "badge-muted"}`}>
                        {t.status || "done"}
                      </span>
                    </div>
                  ))}
                </div>
              )}
            </section>
          </div>
        </div>
      </div>
    </div>
  );
}
