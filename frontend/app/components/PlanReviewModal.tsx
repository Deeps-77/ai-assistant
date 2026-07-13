"use client";
import { useState } from "react";
import styles from "./PlanReviewModal.module.css";

interface Props {
  plan: string;
  onApprove: () => void;
  onReject: (feedback: string) => void;
}

export default function PlanReviewModal({ plan, onApprove, onReject }: Props) {
  const [feedback, setFeedback] = useState("");
  const [showFeedback, setShowFeedback] = useState(false);

  return (
    <div className={styles.overlay}>
      <div className={styles.modal}>
        <div className={styles.header}>
          <span className={styles.icon}>📋</span>
          <div>
            <h2 className={styles.title}>Plan Review</h2>
            <p className={styles.subtitle}>opencode-style — approve before building</p>
          </div>
        </div>
        <div className={styles.planBox}>
          <pre className={styles.planText}>{plan}</pre>
        </div>
        {showFeedback && (
          <textarea
            className={styles.feedback}
            placeholder="Describe changes you want to the plan…"
            value={feedback}
            onChange={(e) => setFeedback(e.target.value)}
            rows={3}
          />
        )}
        <div className={styles.actions}>
          <button className="btn btn-primary" onClick={onApprove}>
            ✓ Approve &amp; Build
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
