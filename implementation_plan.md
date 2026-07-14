# Upgrade File Tools & Implement HITL File Review

The current implementation executes file modifications synchronously within the agent nodes using `write_file_tool`, which overwrites the entire file. This plan details the transition to a true agentic tool-calling architecture, introducing precise file editing tools and a Human-in-the-Loop (HITL) approval step before any disk modifications occur.

## User Review Required

> [!IMPORTANT]
> **Workflow Interruption**: Implementing this will pause the workflow *every time* an agent wants to write or edit a file, requiring the user to explicitly approve the change on the frontend. Do you want this enabled globally, or should it be a toggleable feature (e.g., "Auto-Approve Edits")?

## Open Questions

> [!WARNING]
> 1. **Edit Strategy**: Should the `edit_file_tool` use a **String Replace** strategy (providing exact target string and replacement) or a **Line Range Replace** strategy (start line, end line, new content)? *String replace is generally safer for LLMs to avoid line number drift.*
> 2. **Frontend Diffing**: To show a diff on the frontend, the backend needs to send the current file content and the proposed edits. Are you comfortable with using a library like `diff` on the frontend, or should the backend pre-compute the diff string?

## Proposed Changes

---

### Backend: File Tools

#### [MODIFY] `file_tools.py`
- Refactor `write_file_tool` to explicitly state it is for *creating new files* or *full overwrites*.
- **[NEW]** Add `edit_file_tool(filepath: str, target_content: str, replacement_content: str)`:
  - Validates that `target_content` exists in the file.
  - Replaces `target_content` with `replacement_content`.
  - Returns clear error messages if the target string is not found or is ambiguous (multiple matches).
- **[NEW]** Add `delete_file_tool(filepath: str)`.
- Ensure all tools are registered and available to the `tool_llm` binding.

---

### Backend: Agent Execution & Graph

#### [MODIFY] `agents.py`
- Remove the synchronous `_execute_tool_calls` logic from `worker_coder` and `worker_fixer`.
- Update agents to return the generated `tool_calls` in the state rather than executing them.
- Introduce a mechanism to format rejected tool calls as `ToolMessage`s so the LLM can correct its formatting or logic in the next iteration.

#### [MODIFY] `state.py`
- Add `pending_tool_calls: list[dict]` to `WorkerState` and `SoftwareState`.
- Add `file_review_approved: bool` and `file_review_feedback: str` to handle the user's decision.

#### [MODIFY] `graph.py`
- Add a new **`file_review_node`**: A dummy node that acts as an interrupt breakpoint. LangGraph will pause execution here if `pending_tool_calls` exist.
- Add a new **`tool_executor_node`**: Iterates through approved `pending_tool_calls` and actually executes the python functions from `file_tools.py`, applying changes to the file system.
- Update the `worker_graph` routing:
  - `worker_coder` -> `file_review_node`
  - `file_review_node` -> `tool_executor_node` (if approved) -> `worker_reviewer`
  - `file_review_node` -> `worker_coder` (if rejected, feeding back the user's rejection reason).
  - Apply the exact same loop for `worker_fixer`.

---

### Frontend: Next.js UI

#### [MODIFY] `frontend/app/chat/page.tsx`
- Detect when the agent is paused at `file_review_node`.
- Extract the `pending_tool_calls` from the state.
- **[NEW] `FileDiffViewer` Component**:
  - Displays the proposed file changes. For `write_file_tool`, it shows the full new file. For `edit_file_tool`, it calculates and displays an inline or side-by-side diff.
- Add **Approve** and **Reject** buttons.
- On Reject, prompt the user for feedback (e.g., "The import path is wrong, please fix").
- Submit the decision via `POST /api/resume` with `{ file_review_approved: true/false, file_review_feedback: "..." }`.

#### [NEW] `HumanReviewModal` & Pause Handling Fix
- Currently, `page.tsx` blindly renders a `PlanReviewModal` on *any* pause (even for `human_review_node`).
- **Fix `onPaused` handler**: Inspect `data.interrupts[0].type`. If it's `plan_review`, show `PlanReviewModal`. If it's `human_review`, show a new `HumanReviewModal`. If it's `file_review`, show the `FileDiffViewer`.
- **Create `HumanReviewModal`**: Displays the `completed_modules` list and asks the user to "Approve Project?" before proceeding to QA and delivery.

---

## Verification Plan

### Automated Tests
- Run `pytest tests/` to ensure existing graph paths and fallback logic still hold.
- Write unit tests for `edit_file_tool` to verify exact string replacement handles edge cases (e.g., missing whitespace, non-existent target strings).

### Manual Verification
1. Start the chat UI and request a small code change to an existing file.
2. Verify the pipeline pauses at the new `file_review_node`.
3. Verify the frontend displays the correct file diff.
4. **Reject** the change with feedback and verify the agent regenerates the tool call.
5. **Approve** the change and verify the file is successfully modified on disk, and the pipeline continues to the reviewer node.
