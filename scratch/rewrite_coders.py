import re

with open("agents.py", "r", encoding="utf-8") as f:
    content = f.read()

# For module_coder_node
mc_old = r"(?s)# Try tool calling path first.*?code_map = dict\(state\.get\(\"generated_code\", \{\}\)\)\s*code_map\[module\] = content.*?return \{.*?\"fix_attempts\": 0,?\s*\}"
mc_new = """# Extract tool calls to pending state
        pending = _extract_pending_tool_calls(response, label="code")
        if pending:
            return {"pending_tool_calls": pending, "fix_attempts": 0}

        # Fallback: text-based approach
        content = response.content or ""
        if not content.strip():
            print(f"   Empty response from tool_llm; retrying with plain LLM...")
            try:
                response = (prompt | llms["llm"]).invoke({
                    "tech_stack": tech_stack,
                    "module": module,
                    "architecture": state["architecture"],
                    "exact_file_paths": exact_file_paths,
                    "quality_guide": state.get("quality_guide", ""),
                    "human_feedback": state.get("human_feedback", ""),
                })
                content = response.content or ""
            except Exception:
                content = ""
            if not content.strip():
                print(f"   Empty response for [{module}]; generating placeholder.")
                content = f"# {module} module\\n# TODO: implement\\n"

        pending_fallback = _fallback_text_to_tools(content)
        if pending_fallback:
            return {"pending_tool_calls": pending_fallback, "fix_attempts": 0}

        print(f"   No tools extracted for [{module}]; returning empty pending_tool_calls.")
        return {"pending_tool_calls": [], "fix_attempts": 0}"""

content = re.sub(mc_old, mc_new, content, count=1)


# For fixer_node
fn_old = r"(?s)# Try tool calling path first.*?code_map = dict\(state\[\"generated_code\"\]\)\s*code_map\[module\] = text\s*return \{\s*\"generated_code\": code_map,\s*\"fix_attempts\": attempts,?\s*\}"
fn_new = """# Extract tool calls to pending state
        pending = _extract_pending_tool_calls(response, label="fix")
        if pending:
            return {"pending_tool_calls": pending, "fix_attempts": attempts}

        # Fallback: text-based response
        text = (response.content or "").strip()
        if not text:
            print(f"   Empty fix from tool_llm; retrying with plain LLM...")
            try:
                response = (prompt | llms["llm"]).invoke({
                    "tech_stack": tech_stack,
                    "module": module,
                    "code": code,
                    "issues": "\\n".join(f"- {i}" for i in issues),
                    "quality_guide": quality,
                    "human_feedback": state.get("human_feedback", ""),
                })
                text = (response.content or "").strip()
            except Exception:
                text = ""
            
            if not text:
                print(f"   Fixer produced nothing for [{module}]; returning empty.")
                return {"pending_tool_calls": [], "fix_attempts": attempts}

        pending_fallback = _fallback_text_to_tools(text)
        if pending_fallback:
            return {"pending_tool_calls": pending_fallback, "fix_attempts": attempts}

        return {"pending_tool_calls": [], "fix_attempts": attempts}"""

content = re.sub(fn_old, fn_new, content, count=1)


# For worker_coder
wc_old = r"(?s)# Try tool calling path first.*?write_module_files\(project_path, module, content, \"\"\)\s*return \{\"generated_code\": \{module: combined\}\}"
wc_new = """# Extract tool calls to pending state
        pending = _extract_pending_tool_calls(response, label="w_code")
        if pending:
            return {"pending_tool_calls": pending}

        # Fallback: text-based response
        content = response.content or ""
        pending_fallback = _fallback_text_to_tools(content)
        if pending_fallback:
            return {"pending_tool_calls": pending_fallback}

        print(f"   No tools extracted for [{module}]; returning empty pending_tool_calls.")
        return {"pending_tool_calls": []}"""

content = re.sub(wc_old, wc_new, content, count=1)


# For worker_fixer
wf_old = r"(?s)# Try tool calling path first.*?write_module_files\(project_path, module, text, \"\"\)\s*return \{\"generated_code\": \{module: combined\}, \"fix_attempts\": attempts\}"
wf_new = """# Extract tool calls to pending state
        pending = _extract_pending_tool_calls(response, label="w_fix")
        if pending:
            return {"pending_tool_calls": pending, "fix_attempts": attempts}

        # Fallback: text-based response
        text = (response.content or "").strip()
        if not text:
            print(f"      * [{module}] Empty fix from tool_llm; retrying with plain LLM...")
            try:
                response = (prompt | llms["llm"]).invoke({
                    "tech_stack": tech_stack,
                    "module": module,
                    "code": code,
                    "issues": "\\n".join(f"- {i}" for i in issues),
                    "quality_guide": state.get("quality_guide", ""),
                    "human_feedback": state.get("human_feedback", ""),
                })
                text = (response.content or "").strip()
            except Exception:
                text = ""

        pending_fallback = _fallback_text_to_tools(text)
        if pending_fallback:
            return {"pending_tool_calls": pending_fallback, "fix_attempts": attempts}

        return {"pending_tool_calls": [], "fix_attempts": attempts}"""

content = re.sub(wf_old, wf_new, content, count=1)

with open("agents.py", "w", encoding="utf-8") as f:
    f.write(content)
print("Rewrote the 4 coder functions successfully.")
