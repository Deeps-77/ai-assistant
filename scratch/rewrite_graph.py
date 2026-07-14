import re

with open("graph.py", "r", encoding="utf-8") as f:
    content = f.read()

# 1. Add imports
if "file_review_node" not in content[:1000]:
    content = content.replace("worker_complete,", "worker_complete,\\n    file_review_node,\\n    tool_executor_node,")

# 2. Add nodes to main workflow
nodes_str = """workflow.add_node("module_coder", trace_node("module_coder")(module_coder_node))
workflow.add_node("file_review_node", trace_node("file_review_node")(file_review_node))
workflow.add_node("tool_executor_node", trace_node("tool_executor_node")(tool_executor_node))"""
content = re.sub(r'workflow\.add_node\("module_coder", trace_node\("module_coder"\)\(module_coder_node\)\)', nodes_str, content)


# 3. Add nodes to worker_builder
wb_nodes_str = """worker_builder.add_node("worker_coder", trace_node("worker_coder")(worker_coder))
worker_builder.add_node("worker_file_review_node", trace_node("file_review_node")(file_review_node))
worker_builder.add_node("worker_tool_executor_node", trace_node("tool_executor_node")(tool_executor_node))"""
content = re.sub(r'worker_builder\.add_node\("worker_coder", trace_node\("worker_coder"\)\(worker_coder\)\)', wb_nodes_str, content)

# 4. Update worker_builder edges
wb_edges_old = """worker_builder.add_edge("worker_module_planner", "worker_coder")
worker_builder.add_edge("worker_coder", "worker_reviewer")

worker_builder.add_conditional_edges(
    "worker_reviewer",
    _route_after_worker_review,
    {
        "worker_fixer": "worker_fixer",
        "worker_complete": "worker_complete",
    },
)

worker_builder.add_edge("worker_fixer", "worker_reviewer")"""

wb_edges_new = """worker_builder.add_edge("worker_module_planner", "worker_coder")
worker_builder.add_edge("worker_coder", "worker_file_review_node")

def route_worker_after_file_review(state: WorkerState):
    if state.get("file_review_approved", True):
        return "worker_tool_executor_node"
    if state.get("fix_attempts", 0) > 0:
        return "worker_fixer"
    return "worker_coder"

worker_builder.add_conditional_edges(
    "worker_file_review_node",
    route_worker_after_file_review,
    {
        "worker_tool_executor_node": "worker_tool_executor_node",
        "worker_fixer": "worker_fixer",
        "worker_coder": "worker_coder",
    }
)

worker_builder.add_edge("worker_tool_executor_node", "worker_reviewer")

worker_builder.add_conditional_edges(
    "worker_reviewer",
    _route_after_worker_review,
    {
        "worker_fixer": "worker_fixer",
        "worker_complete": "worker_complete",
    },
)

worker_builder.add_edge("worker_fixer", "worker_file_review_node")"""

content = content.replace(wb_edges_old, wb_edges_new)

# 5. Update sequential workflow edges
wf_edges_old = """workflow.add_edge("module_planner", "module_coder")
workflow.add_edge("module_coder", "reviewer")

workflow.add_conditional_edges(
    "reviewer",
    route_after_review,
    {
        "fixer": "fixer",
        "complete_module": "complete_module",
    },
)

workflow.add_edge("fixer", "reviewer")"""

wf_edges_new = """workflow.add_edge("module_planner", "module_coder")
workflow.add_edge("module_coder", "file_review_node")

def route_after_file_review(state: SoftwareState):
    if state.get("file_review_approved", True):
        return "tool_executor_node"
    if state.get("fix_attempts", 0) > 0:
        return "fixer"
    return "module_coder"

workflow.add_conditional_edges(
    "file_review_node",
    route_after_file_review,
    {
        "tool_executor_node": "tool_executor_node",
        "fixer": "fixer",
        "module_coder": "module_coder",
    }
)

workflow.add_edge("tool_executor_node", "reviewer")

workflow.add_conditional_edges(
    "reviewer",
    route_after_review,
    {
        "fixer": "fixer",
        "complete_module": "complete_module",
    },
)

workflow.add_edge("fixer", "file_review_node")"""

content = content.replace(wf_edges_old, wf_edges_new)

with open("graph.py", "w", encoding="utf-8") as f:
    f.write(content)
print("Updated graph.py successfully.")
