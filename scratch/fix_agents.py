import re

with open("agents.py", "r", encoding="utf-8") as f:
    content = f.read()

# 1. Fix project_init_node
# Replace _execute_tool_calls(response, project_path, label="init") with programmatic fallback because we removed _execute_tool_calls
init_old = """    try:
        response = llms["tool_llm"].invoke(prompt_text)
        written, _ = _execute_tool_calls(response, project_path, label="init")
        if written:
            print(f"   Tool calls created {len(written)} directories")
        else:
            # Fallback: parse and create programmatically
            print("   No tool calls received; falling back to programmatic directory creation.")
            init_project_structure(project_path, folder_structure)
    except Exception as e:
        print(f"   LLM tool call failed ({e}); falling back to programmatic creation.")
        init_project_structure(project_path, folder_structure)"""

init_new = """    try:
        response = llms["tool_llm"].invoke(prompt_text)
        pending = _extract_pending_tool_calls(response, label="init")
        if pending:
            print(f"   Tool calls extracted {len(pending)} directories; falling back to programmatic since init skips file review.")
        init_project_structure(project_path, folder_structure)
    except Exception as e:
        print(f"   LLM tool call failed ({e}); falling back to programmatic creation.")
        init_project_structure(project_path, folder_structure)"""

content = content.replace(init_old, init_new)


# 2. Fix the coder fallbacks returning empty generated_code

# module_coder_node
mc_old = """        pending_fallback = _fallback_text_to_tools(content)
        if pending_fallback:
            return {"pending_tool_calls": pending_fallback, "fix_attempts": 0}

        print(f"   No tools extracted for [{module}]; returning empty pending_tool_calls.")
        return {"pending_tool_calls": [], "fix_attempts": 0}"""

mc_new = """        pending_fallback = _fallback_text_to_tools(content)
        if pending_fallback:
            return {"pending_tool_calls": pending_fallback, "fix_attempts": 0}

        print(f"   No tools extracted for [{module}]; keeping placeholder text.")
        code_map = dict(state.get("generated_code", {}))
        code_map[module] = content
        return {"pending_tool_calls": [], "generated_code": code_map, "fix_attempts": 0}"""
content = content.replace(mc_old, mc_new)


# fixer_node
fn_old = """        pending_fallback = _fallback_text_to_tools(text)
        if pending_fallback:
            return {"pending_tool_calls": pending_fallback, "fix_attempts": attempts}

        return {"pending_tool_calls": [], "fix_attempts": attempts}"""
        
fn_new = """        pending_fallback = _fallback_text_to_tools(text)
        if pending_fallback:
            return {"pending_tool_calls": pending_fallback, "fix_attempts": attempts}

        code_map = dict(state.get("generated_code", {}))
        code_map[module] = text
        return {"pending_tool_calls": [], "generated_code": code_map, "fix_attempts": attempts}"""
content = content.replace(fn_old, fn_new)


# worker_coder
wc_old = """        pending_fallback = _fallback_text_to_tools(content)
        if pending_fallback:
            return {"pending_tool_calls": pending_fallback}

        return {"pending_tool_calls": []}"""

wc_new = """        pending_fallback = _fallback_text_to_tools(content)
        if pending_fallback:
            return {"pending_tool_calls": pending_fallback}

        return {"pending_tool_calls": [], "generated_code": {module: content}}"""
content = content.replace(wc_old, wc_new)


# worker_fixer
wf_old = """        pending_fallback = _fallback_text_to_tools(text)
        if pending_fallback:
            return {"pending_tool_calls": pending_fallback, "fix_attempts": attempts}

        return {"pending_tool_calls": [], "fix_attempts": attempts}"""

wf_new = """        pending_fallback = _fallback_text_to_tools(text)
        if pending_fallback:
            return {"pending_tool_calls": pending_fallback, "fix_attempts": attempts}

        return {"pending_tool_calls": [], "generated_code": {module: text}, "fix_attempts": attempts}"""
content = content.replace(wf_old, wf_new)


with open("agents.py", "w", encoding="utf-8") as f:
    f.write(content)
print("Applied fixes to agents.py")
