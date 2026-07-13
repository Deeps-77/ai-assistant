"use client";
import { useEffect, useState } from "react";
import Link from "next/link";
import Sidebar from "../components/Sidebar";
import TopBar from "../components/TopBar";
import { getProjects, getThreads } from "../lib/api";
import styles from "./page.module.css";

interface Project { project_path: string; name?: string; status?: string; updated_at?: number; thread_id?: string; }
interface Thread { thread_id: string; status?: string; message?: string; updated_at?: number; agent_steps_count?: number; }

export default function ProjectsPage() {
  const [projects, setProjects] = useState<Project[]>([]);
  const [threads, setThreads] = useState<Thread[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    Promise.all([getProjects(), getThreads()]).then(([p, t]) => {
      setProjects((p as { projects: Project[] }).projects || []);
      setThreads((t as { threads: Thread[] }).threads || []);
      setLoading(false);
    });
  }, []);

  const fmt = (ts?: number) => ts ? new Date(ts * 1000).toLocaleString() : "—";

  return (
    <div className="layout">
      <Sidebar />
      <div className="main-content">
        <TopBar title="Projects" subtitle="All delivery runs & generated projects"
          actions={<Link href="/chat" className="btn btn-primary">+ New Delivery</Link>} />
        <div className="page">

          <section style={{ marginBottom: 32 }}>
            <p className="section-title">Projects ({projects.length})</p>
            {loading ? (
              <div style={{ display: "flex", flexDirection: "column", gap: 10 }}>
                {[1,2,3].map(i => <div key={i} className="skeleton" style={{ height: 70 }} />)}
              </div>
            ) : projects.length === 0 ? (
              <div className={`card ${styles.empty}`}>
                <p>No projects yet.</p>
                <Link href="/chat" className="btn btn-primary" style={{ marginTop: 12 }}>Start your first delivery →</Link>
              </div>
            ) : (
              <div className={styles.grid}>
                {projects.map((p) => (
                  <div key={p.project_path} className={`card ${styles.projectCard}`}>
                    <div className={styles.cardTop}>
                      <span className={styles.projIcon}>📁</span>
                      <span className={`badge ${p.status === "active" ? "badge-success" : "badge-muted"}`}>{p.status || "done"}</span>
                    </div>
                    <p className={styles.projName}>{p.name || p.project_path.split(/[\\/]/).pop()}</p>
                    <p className={styles.projPath}>{p.project_path}</p>
                    <p className={styles.projMeta}>Updated: {fmt(p.updated_at)}</p>
                    {p.thread_id && (
                      <Link href={`/chat`} className={`btn btn-ghost ${styles.viewBtn}`}>View in Chat →</Link>
                    )}
                  </div>
                ))}
              </div>
            )}
          </section>

          <section>
            <p className="section-title">All Runs ({threads.length})</p>
            <div className={styles.threadList}>
              {loading ? [1,2,3,4].map(i => <div key={i} className="skeleton" style={{ height: 56 }} />) :
               threads.map((t) => (
                <div key={t.thread_id} className={`card ${styles.threadCard}`}>
                  <div className={styles.threadLeft}>
                    <span className={`dot dot-${t.status === "done" ? "success" : t.status === "running" ? "running" : "idle"}`} />
                    <div>
                      <p className={styles.threadMsg}>{t.message?.slice(0, 80) || "Untitled run"}</p>
                      <p className={styles.threadId}>{t.thread_id} · {fmt(t.updated_at)}</p>
                    </div>
                  </div>
                  <div className={styles.threadRight}>
                    {t.agent_steps_count !== undefined && (
                      <span className="badge badge-accent">{t.agent_steps_count} steps</span>
                    )}
                    <span className={`badge ${t.status === "done" ? "badge-success" : t.status === "error" ? "badge-error" : "badge-info"}`}>
                      {t.status || "done"}
                    </span>
                  </div>
                </div>
              ))}
            </div>
          </section>
        </div>
      </div>
    </div>
  );
}
