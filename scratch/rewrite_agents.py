import re
import os

with open("agents.py", "r", encoding="utf-8") as f:
    content = f.read()

# 1. Replace _execute_tool_calls
old_execute = '''def _execute_tool_calls(response, project_path: str, label: str = "") -> tuple[dict[str, str], dict[str, str]]:
    """Execute tool calls from an LLM response and return (written_files, code_map).

    written_files: rel_path -> status string
    code_map: rel_path -> content for tracking
    """
    written: dict[str, str] = {}
    code_blocks: dict[str, str] = {}

    has_calls = hasattr(response, "tool_calls") and bool(response.tool_calls)
    content_len = len((response.content or "").strip()) if hasattr(response, "content") else -1
    prefix = f"   [{label}] " if label else "   "
    print(f"{prefix}response: tool_calls={has_calls}, text_len={content_len}")

    if has_calls:
        for tc in response.tool_calls:
            name = tc.get("name", "")
            args = tc.get("args", {})
            print(f"{prefix}  tool: {name} -> {args.get('filepath') or args.get('path', '')}")
            if name == "write_file_tool":
                rel_path = args.get("filepath", "")
                content = args.get("content", "")
                if rel_path:
                    try:
                        full_path = os.path.join(project_path, rel_path)
                        result = write_file(full_path, content)
                        written[rel_path.replace("\\\\", "/")] = result
                        code_blocks[rel_path.replace("\\\\", "/")] = content
                    except Exception as e:
                        print(f"{prefix}  write_file failed for {rel_path}: {e}")
                        written[rel_path.replace("\\\\", "/")] = f"error: {e}"
            elif name == "create_directory_tool":
                dir_path = args.get("path", "")
                if dir_path:
                    try:
                        full_path = os.path.join(project_path, dir_path)
                        ensure_directory(full_path)
                        written[dir_path.replace("\\\\", "/") + "/"] = "ok"
                    except Exception as e:
                        print(f"{prefix}  create_directory failed for {dir_path}: {e}")
                        written[dir_path.replace("\\\\", "/") + "/"] = f"error: {e}"
    else:
        print(f"{prefix}  (no tool calls in response)")
    return written, code_blocks'''

new_extract = '''import uuid
from file_tools import write_file_tool, create_directory_tool, read_file_tool, edit_file_tool, delete_file_tool

def _extract_pending_tool_calls(response, label: str = "") -> list[dict]:
    """Extract tool calls from LLM response into pending state."""
    pending = []
    has_calls = hasattr(response, "tool_calls") and bool(response.tool_calls)
    content_len = len((response.content or "").strip()) if hasattr(response, "content") else -1
    prefix = f"   [{label}] " if label else "   "
    print(f"{prefix}response: tool_calls={has_calls}, text_len={content_len}")

    if has_calls:
        for tc in response.tool_calls:
            name = tc.get("name", "")
            args = tc.get("args", {})
            print(f"{prefix}  queued tool: {name} -> {args.get('filepath') or args.get('path', '')}")
            pending.append({
                "id": tc.get("id", f"tc_{uuid.uuid4().hex[:8]}"),
                "name": name,
                "args": args
            })
    else:
        print(f"{prefix}  (no tool calls in response)")
    return pending

def _fallback_text_to_tools(content: str) -> list[dict]:
    pending = []
    files = parse_code_blocks(content)
    if files:
        for rel_path, file_content in files.items():
            pending.append({
                "id": f"tc_{uuid.uuid4().hex[:8]}",
                "name": "write_file_tool",
                "args": {"filepath": rel_path, "content": file_content}
            })
    return pending
'''

if old_execute in content:
    content = content.replace(old_execute, new_extract)
else:
    print("Could not find _execute_tool_calls block")

# 2. Add file_review_node and tool_executor_node at the end of the file
new_nodes = """

# ═══════════════════════════════════════════════
# FILE REVIEW & TOOL EXECUTOR (HITL)
# ═══════════════════════════════════════════════

def file_review_node(state):
    pending = state.get("pending_tool_calls") or []
    if not pending:
        return {"file_review_approved": True, "file_review_feedback": ""}
        
    module = state.get("current_module") or state.get("module_name", "unknown")
    print(f"\\n" + "=" * 60)
    print(f"📄 FILE REVIEW: {module} ({len(pending)} pending changes)")
    print("=" * 60)
    
    decision = interrupt({
        "type": "file_review",
        "prompt": "Approve file changes? (yes/no): ",
        "pending_tool_calls": pending,
        "module": module,
    })
    
    if isinstance(decision, dict):
        choice = str(decision.get("choice", "")).strip().lower()
        feedback = decision.get("feedback", "") or ""
    else:
        choice = str(decision).strip().lower()
        feedback = ""
        
    if choice == "no":
        print(f"   Changes rejected. Feedback: {feedback}")
        return {
            "file_review_approved": False, 
            "human_feedback": feedback,
            "pending_tool_calls": [],  # clear so coder regenerates
            "fix_attempts": state.get("fix_attempts", 0) + 1
        }
        
    print("   Changes approved.")
    return {"file_review_approved": True, "file_review_feedback": ""}


def tool_executor_node(state):
    pending = state.get("pending_tool_calls") or []
    if not pending:
        return {}
        
    project_path = state.get("project_path") or os.path.join(state.get("output_dir", "outputs"), "project")
    module = state.get("current_module") or state.get("module_name", "unknown")
    
    written_files = dict(state.get("written_files", {}))
    code_map = dict(state.get("generated_code", {}))
    
    # Store combined blocks per module to update generated_code
    blocks = []
    
    print(f"--- TOOL EXECUTOR: Applying {len(pending)} changes ---")
    for tc in pending:
        name = tc.get("name", "")
        args = tc.get("args", {})
        
        # Tools in file_tools are configured as standard python functions we can call directly,
        # but their actual invocation needs to be inside the project directory.
        filepath = args.get("filepath", "") or args.get("path", "")
        
        try:
            full_path = os.path.join(project_path, filepath) if filepath else ""
            if name == "write_file_tool":
                write_file(full_path, args.get("content", ""))
                written_files[filepath.replace("\\\\", "/")] = "ok"
                blocks.append(f"# --- {filepath} ---\\n{args.get('content', '')}")
            elif name == "create_directory_tool":
                ensure_directory(full_path)
                written_files[filepath.replace("\\\\", "/") + "/"] = "ok"
            elif name == "edit_file_tool":
                # Using the edit_file_tool function directly
                from file_tools import edit_file_tool
                res = edit_file_tool.invoke({"filepath": full_path, "target_content": args.get("target_content", ""), "replacement_content": args.get("replacement_content", "")})
                written_files[filepath.replace("\\\\", "/")] = res
                if "Error" not in res:
                    # Reread to put in blocks
                    blocks.append(f"# --- {filepath} (edited) ---\\n{Path(full_path).read_text(encoding='utf-8')}")
            elif name == "delete_file_tool":
                from file_tools import delete_file_tool
                res = delete_file_tool.invoke({"filepath": full_path})
                written_files[filepath.replace("\\\\", "/")] = res
        except Exception as e:
            print(f"   Error executing {name}: {e}")
            written_files[filepath.replace("\\\\", "/")] = f"error: {e}"
            
    if blocks:
        code_map[module] = "\\n\\n".join(blocks)
        
    return {
        "pending_tool_calls": [],
        "written_files": written_files,
        "generated_code": code_map
    }
"""

if "def file_review_node" not in content:
    content += new_nodes

with open("agents.py", "w", encoding="utf-8") as f:
    f.write(content)
print("Updated agents.py successfully.")
