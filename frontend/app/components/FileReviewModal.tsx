"use client";
import { useState } from "react";
import styles from "./PlanReviewModal.module.css"; // Reuse styling

interface Props {
  data: any;
  onApprove: () => void;
  onReject: (feedback: string) => void;
}

export default function FileReviewModal({ data, onApprove, onReject }: Props) {
  const [feedback, setFeedback] = useState("");
  const [showFeedback, setShowFeedback] = useState(false);

  const moduleName = data?.module || "Unknown Module";
  const pendingCalls = data?.pending_tool_calls || [];

  return (
    <div className={styles.overlay}>
      <div className={styles.modal} style={{ maxWidth: "800px" }}>
        <div className={styles.header}>
          <span className={styles.icon}>📄</span>
          <div>
            <h2 className={styles.title}>File Changes Review: {moduleName}</h2>
            <p className={styles.subtitle}>Review and approve the pending file operations</p>
          </div>
        </div>
        
        <div className={styles.planBox} style={{ maxHeight: "400px", overflowY: "auto" }}>
          {pendingCalls.length === 0 ? (
            <p>No file changes proposed.</p>
          ) : (
            pendingCalls.map((tc: any, idx: number) => {
              const name = tc.name;
              const args = tc.args || {};
              const filepath = args.filepath || args.path || "Unknown path";

              return (
                <div key={idx} style={{ marginBottom: "1.5rem", borderBottom: "1px solid #333", paddingBottom: "1rem" }}>
                  <h3 style={{ marginBottom: "0.5rem", color: "#61dafb" }}>
                    {name === "write_file_tool" ? "Create / Overwrite File" : 
                     name === "edit_file_tool" ? "Edit File" : 
                     name === "delete_file_tool" ? "Delete File" : 
                     name === "create_directory_tool" ? "Create Directory" : name}: 
                    <span style={{ color: "#fff", marginLeft: "0.5rem" }}>{filepath}</span>
                  </h3>
                  
                  {name === "write_file_tool" && args.content && (
                    <pre className={styles.planText} style={{ marginTop: "0.5rem", padding: "0.5rem", background: "#1e1e1e" }}>
                      {args.content}
                    </pre>
                  )}

                  {name === "edit_file_tool" && (
                    <div style={{ marginTop: "0.5rem" }}>
                      <div style={{ padding: "0.5rem", background: "#3a2a2a", color: "#ff8b8b", marginBottom: "0.25rem" }}>
                        <div style={{ fontSize: "0.75rem", textTransform: "uppercase", marginBottom: "0.25rem", opacity: 0.8 }}>Target (Replace this)</div>
                        <pre style={{ margin: 0, whiteSpace: "pre-wrap" }}>{args.target_content}</pre>
                      </div>
                      <div style={{ padding: "0.5rem", background: "#2a3a2a", color: "#8bff8b" }}>
                        <div style={{ fontSize: "0.75rem", textTransform: "uppercase", marginBottom: "0.25rem", opacity: 0.8 }}>With this</div>
                        <pre style={{ margin: 0, whiteSpace: "pre-wrap" }}>{args.replacement_content}</pre>
                      </div>
                    </div>
                  )}
                </div>
              );
            })
          )}
        </div>

        {showFeedback && (
          <textarea
            className={styles.feedback}
            placeholder="Describe what needs to be changed in these files..."
            value={feedback}
            onChange={(e) => setFeedback(e.target.value)}
            rows={3}
            style={{ marginTop: "1rem" }}
          />
        )}
        
        <div className={styles.actions} style={{ marginTop: "1rem" }}>
          <button className="btn btn-primary" onClick={onApprove}>
            ✓ Approve Changes
          </button>
          {!showFeedback ? (
            <button className="btn btn-ghost" onClick={() => setShowFeedback(true)}>
              ✗ Reject
            </button>
          ) : (
            <button className="btn btn-danger" onClick={() => onReject(feedback)}>
              Send Feedback
            </button>
          )}
        </div>
      </div>
    </div>
  );
}
