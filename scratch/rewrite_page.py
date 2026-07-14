import re

with open("frontend/app/chat/page.tsx", "r", encoding="utf-8") as f:
    content = f.read()

# Add imports
content = content.replace("import PlanReviewModal from \"../components/PlanReviewModal\";", 
"""import PlanReviewModal from "../components/PlanReviewModal";
import HumanReviewModal from "../components/HumanReviewModal";
import FileReviewModal from "../components/FileReviewModal";""")

# Change state
content = content.replace("const [planModal, setPlanModal] = useState<{ threadId: string; plan: string } | null>(null);", 
"const [interruptModal, setInterruptModal] = useState<{ type: string; threadId: string; data: any } | null>(null);")

# Change onPaused in handleSend
old_onPaused = """      onPaused: (data) => {
        const intr = (data.interrupts as { plan?: string }[])[0];
        const planText = intr?.plan || JSON.stringify(intr, null, 2);
        setPlanModal({ threadId, plan: planText });
        setIsRunning(false);
        setCurrentAgent("");
      },"""
new_onPaused = """      onPaused: (data) => {
        const intr = (data.interrupts as any[])[0];
        setInterruptModal({ type: intr?.type || "plan_review", threadId, data: intr });
        setIsRunning(false);
        setCurrentAgent("");
      },"""
content = content.replace(old_onPaused, new_onPaused)

# Change onPaused in handleApprove
old_onPaused2 = """      onPaused: () => { setIsRunning(false); },"""
new_onPaused2 = """      onPaused: (data) => { 
        const intr = (data.interrupts as any[])[0];
        setInterruptModal({ type: intr?.type || "plan_review", threadId: planModal.threadId, data: intr });
        setIsRunning(false); 
      },"""
# Wait, handleApprove needs interruptModal.threadId, not planModal.threadId
content = content.replace(old_onPaused2, new_onPaused2.replace("planModal", "interruptModal"))

# Change handleApprove and handleReject
content = content.replace("if (!planModal) return;", "if (!interruptModal) return;")
content = content.replace("setPlanModal(null);", "setInterruptModal(null);")
content = content.replace("planModal.threadId", "interruptModal.threadId")

# Change render logic
old_render = """      {planModal && (
        <PlanReviewModal plan={planModal.plan} onApprove={handleApprove} onReject={handleReject} />
      )}"""
new_render = """      {interruptModal && interruptModal.type === "plan_review" && (
        <PlanReviewModal plan={interruptModal.data?.plan || JSON.stringify(interruptModal.data, null, 2)} onApprove={handleApprove} onReject={handleReject} />
      )}
      {interruptModal && interruptModal.type === "human_review" && (
        <HumanReviewModal data={interruptModal.data} onApprove={handleApprove} onReject={handleReject} />
      )}
      {interruptModal && interruptModal.type === "file_review" && (
        <FileReviewModal data={interruptModal.data} onApprove={handleApprove} onReject={handleReject} />
      )}"""
content = content.replace(old_render, new_render)

with open("frontend/app/chat/page.tsx", "w", encoding="utf-8") as f:
    f.write(content)
print("Updated page.tsx successfully.")
