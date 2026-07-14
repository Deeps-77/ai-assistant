"use client";
import { useState } from "react";
import styles from "./PlanReviewModal.module.css"; // Reuse styling

interface Props {
  data: any;
  onApprove: () => void;
  onReject: (feedback: string) => void;
}

export default function HumanReviewModal({ data, onApprove, onReject }: Props) {
  const [feedback, setFeedback] = useState("");
  const [showFeedback, setShowFeedback] = useState(false);

  const completedModules = data?.completed_modules || [];

  return (
    <div className={styles.overlay}>
      <div className={styles.modal}>
        <div className={styles.header}>
          <span className={styles.icon}>👤</span>
          <div>
            <h2 className={styles.title}>Project Review</h2>
            <p className={styles.subtitle}>Review the completed modules before testing</p>
          </div>
        </div>
        <div className={styles.planBox}>
          <h3>Completed Modules</h3>
          <ul style={{ marginTop: "1rem", marginLeft: "1.5rem" }}>
            {completedModules.map((m: string, i: number) => (
              <li key={i} style={{ marginBottom: "0.5rem" }}>
                <strong>{m}</strong>
              </li>
            ))}
            {completedModules.length === 0 && <li>No modules completed yet.</li>}
          </ul>
        </div>
        {showFeedback && (
          <textarea
            className={styles.feedback}
            placeholder="Provide feedback on what needs to be changed..."
            value={feedback}
            onChange={(e) => setFeedback(e.target.value)}
            rows={3}
          />
        )}
        <div className={styles.actions}>
          <button className="btn btn-primary" onClick={onApprove}>
            ✓ Approve Project
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
