from langchain_core.prompts import ChatPromptTemplate


def planner_prompt() -> ChatPromptTemplate:
    return ChatPromptTemplate.from_template(
        "You are a software planner. Analyze the following requirement and "
        "break it into user stories and backend modules.\n"
        "Module names must be simple lowercase strings like 'auth', 'users', 'inventory'.\n\n"
        "Requirement: {requirement}\n\n"
        "Previous feedback to incorporate (if any):\n{human_feedback}\n\n"
        "Also detect the likely tech stack from the requirement.\n\n"
        "Return ONLY a single flat JSON object with exactly these three keys:\n"
        '- "stories": an array of strings\n'
        '- "modules": an array of strings\n'
        '- "tech_stack": a string like "Python/FastAPI" or "Node.js/Express" or "Rust/Axum"\n\n'
        '{{"stories": ["..."], "modules": ["..."], "tech_stack": "..."}}'
    )


def planner_fallback_prompt() -> ChatPromptTemplate:
    return ChatPromptTemplate.from_template(
        "You are a software planner. Analyze the following requirement and "
        "break it into user stories and backend modules.\n"
        "Module names must be simple lowercase strings like 'auth', 'users', 'inventory'.\n\n"
        "Requirement: {requirement}\n\n"
        "Also detect the likely tech stack.\n\n"
        "Return ONLY raw JSON with no markdown formatting."
    )


def architect_prompt() -> ChatPromptTemplate:
    return ChatPromptTemplate.from_template(
        "You are a software architect. Design a {tech_stack} backend system.\n"
        "User stories:\n{stories}\n\n"
        "Modules to design:\n{modules}\n\n"
        "Respond ONLY with a single flat JSON object containing exactly these "
        "five string fields: tech_stack, db_schema, api_endpoints, "
        "folder_structure, architecture_diagram. "
        "Each field must be a plain string (not a nested object or array).\n\n"
        "- folder_structure must be a multi-line tree format with proper indentation, "
        "not a single-line list.\n"
        "- architecture_diagram must be a text-based diagram (ASCII) showing "
        "how modules communicate, data flow between layers, "
        "and authentication flow.\n\n"
        '{{"tech_stack": "...", "db_schema": "...", '
        '"api_endpoints": "...", "folder_structure": "app/\\n  api/\\n    ...", '
        '"architecture_diagram": "..."}}'
    )


def architect_fallback_prompt() -> ChatPromptTemplate:
    return ChatPromptTemplate.from_template(
        "You are a software architect. Design a {tech_stack} backend system.\n"
        "User stories:\n{stories}\n\n"
        "Modules to design:\n{modules}\n\n"
        "Return ONLY raw JSON with no markdown formatting."
    )


def quality_guide_prompt() -> ChatPromptTemplate:
    return ChatPromptTemplate.from_template(
        "You are a senior engineer. Generate a concise quality guide for "
        "{tech_stack} development. Include rules for:\n"
        "1. Security best practices specific to this stack\n"
        "2. Architecture patterns (folder structure, separation of concerns)\n"
        "3. Code quality (error handling, typing, naming conventions)\n"
        "4. Database access patterns (if applicable)\n"
        "5. API design principles\n\n"
        "Return as a plain markdown list. Be specific to {tech_stack}, not generic."
    )


def module_planner_prompt() -> ChatPromptTemplate:
    return ChatPromptTemplate.from_template(
        "You are a senior {tech_stack} architect. Plan the files needed "
        "for the '{module}' module.\n\n"
        "Architecture context:\n{architecture}\n\n"
        "Quality requirements:\n{quality_guide}\n\n"
        "Return ONLY a single flat JSON object with exactly these keys:\n"
        '- "module_name": the module name\n'
        '- "files": an array of objects, each with "path", "purpose", and "exports" (array of strings)\n'
        '- "dependencies": array of other module names this depends on\n'
        '- "api_routes": array of route path strings\n\n'
        '{{"module_name": "...", "files": [{{"path": "...", "purpose": "...", "exports": ["..."]}}], '
        '"dependencies": ["..."], "api_routes": ["..."]}}'
    )


def module_planner_fallback_prompt() -> ChatPromptTemplate:
    return ChatPromptTemplate.from_template(
        "Plan the files needed for the '{module}' module.\n\n"
        "Architecture:\n{architecture}\n\n"
        "Return ONLY raw JSON with no markdown formatting."
    )


def module_coder_prompt() -> ChatPromptTemplate:
    return ChatPromptTemplate.from_template(
        "You are an expert {tech_stack} developer. "
        "Write production-ready code for the '{module}' module.\n\n"
        "Architecture context:\n{architecture}\n\n"
        "You MUST create these files with these exact paths:\n"
        "{exact_file_paths}\n\n"
        "Quality requirements (follow EVERY rule):\n{quality_guide}\n\n"
        "Human feedback to incorporate (if any):\n{human_feedback}\n\n"
        "IMPORTANT: You have access to file-writing tools. Use them directly:\n"
        "1. First call `create_directory_tool` for any needed directories.\n"
        "2. Then call `write_file_tool` for each file with its exact path and full content.\n"
        "Create every file listed above. Do NOT skip any file."
    )


def reviewer_prompt() -> ChatPromptTemplate:
    return ChatPromptTemplate.from_template(
        "You are a strict {tech_stack} code reviewer. "
        "Review this code for the '{module}' module.\n\n"
        "Security focus: {security_focus}. If 'True', scrutinize especially "
        "for SQL injection, XSS, auth bypass, secret leakage, and input "
        "validation gaps.\n\n"
        "Code:\n{code}\n\n"
        "Return ONLY a single flat JSON object with **exactly** these four top-level keys:\n"
        '- "score": an integer 1-10\n'
        '- "issues": an array of plain strings (each describing one issue)\n'
        '- "logic_correctness": a string\n'
        '- "security_check": a string\n\n'
        '{{"score": 0, "issues": ["..."], '
        '"logic_correctness": "...", "security_check": "..."}}'
    )


def reviewer_fallback_prompt() -> ChatPromptTemplate:
    return ChatPromptTemplate.from_template(
        "You are a strict {tech_stack} code reviewer. Review this code "
        "for the '{module}' module.\n\n"
        "Code:\n{code}\n\n"
        "Return ONLY raw JSON with no markdown formatting."
    )


def fixer_prompt() -> ChatPromptTemplate:
    return ChatPromptTemplate.from_template(
        "Fix the following {tech_stack} code based on the reviewer's issues.\n"
        "Module: {module}\n\n"
        "Current code:\n{code}\n\n"
        "Issues to fix:\n{issues}\n\n"
        "Quality requirements (follow EVERY rule):\n{quality_guide}\n\n"
        "Human feedback to incorporate (if any):\n{human_feedback}\n\n"
        "IMPORTANT: You have access to file-writing tools. Use them directly:\n"
        "1. Call `write_file_tool` for each file you need to rewrite with fixes.\n"
        "2. Use the exact same file paths as the original code.\n"
        "Write every corrected file — do not skip any."
    )


def qa_prompt() -> ChatPromptTemplate:
    return ChatPromptTemplate.from_template(
        "You are a QA engineer specializing in {tech_stack}. "
        "Write comprehensive unit tests for the following {module} module code.\n\n"
        "Code:\n{code}\n\n"
        "Include edge cases. Return ONLY test code in a markdown block."
    )


def test_fixer_prompt() -> ChatPromptTemplate:
    return ChatPromptTemplate.from_template(
        "You are a QA engineer fixing failing tests for a {tech_stack} project.\n\n"
        "Module: {module}\n\n"
        "Generated code:\n{code}\n\n"
        "Generated tests:\n{tests}\n\n"
        "Test run output (failures/errors):\n{test_output}\n\n"
        "Analyze the test failures and fix the ROOT CAUSE. You may fix:\n"
        "1. The **code** (if it has bugs) — return the fixed code\n"
        "2. The **tests** (if they have incorrect expectations) — return the fixed tests\n"
        "3. Both, if needed\n\n"
        "IMPORTANT: Return your output in this exact format:\n"
        "# --- relative/path/to/file.ext ---\n"
        "```\n...fixed code...\n```\n\n"
        "Include ALL relevant files, not just the changed ones. "
        "Prefix each file with its relative path header."
    )


def analyze_project_prompt() -> ChatPromptTemplate:
    return ChatPromptTemplate.from_template(
        "You are a senior software engineer analyzing an existing project.\n\n"
        "Project structure:\n{structure}\n\n"
        "Key files:\n{files}\n\n"
        "User requirement (if any): {requirement}\n\n"
        "Analyze this project and return a JSON object with:\n"
        '- "tech_stack": the detected tech stack\n'
        '- "modules": list of existing module names (lowercase, like "auth")\n'
        '- "missing_modules": modules that should exist but don\'t\n'
        '- "issues": list of quality/security issues found\n'
        '- "architecture_summary": summary of what exists\n\n'
        '{{"tech_stack": "...", "modules": [...], '
        '"missing_modules": [...], "issues": [...], '
        '"architecture_summary": "..."}}'
    )


def analysis_report_prompt() -> ChatPromptTemplate:
    return ChatPromptTemplate.from_template(
        "You are a senior software engineer writing a clear, concise report about "
        "an existing codebase for its owner.\n\n"
        "Detected tech stack: {tech_stack}\n\n"
        "Existing modules: {modules}\n\n"
        "Missing modules: {missing_modules}\n\n"
        "Issues found:\n{issues}\n\n"
        "Architecture summary:\n{architecture_summary}\n\n"
        "Write a markdown report with these sections:\n"
        "1. **Overview** — what the project is and its tech stack.\n"
        "2. **Architecture & Modules** — how it is organized, key modules and their roles.\n"
        "3. **Observations & Issues** — the issues found, briefly explained.\n"
        "4. **Suggestions** — 2-4 concrete, prioritized recommendations.\n\n"
        "Be specific and grounded in the details above. Do not invent modules or "
        "capabilities that were not detected. Keep it readable."
    )


def supervisor_prompt() -> ChatPromptTemplate:
    return ChatPromptTemplate.from_template(
        "You are the SUPERVISOR of a multi-agent software delivery team. "
        "Given a user requirement, decide HOW the delivery pipeline should run "
        "by choosing which stages to execute and with what strictness.\n\n"
        "Requirement: {requirement}\n\n"
        "Plan mode requested (user toggled /plan): {plan_mode}\n\n"
        "Return ONLY a single flat JSON object with exactly these keys:\n"
        '- "pause_for_plan_approval": boolean — if true, show the plan and '
        "pause for the user's approval BEFORE generating any code (set true when "
        "plan_mode is true or the user asked for a plan).\n"
        '- "skip_build": boolean — true only if the user explicitly wants ONLY a '
        "plan and no code generated yet.\n"
        '- "skip_tests": boolean — true to skip the QA / test stage entirely '
        "(e.g. for throwaway prototypes).\n"
        '- "execution_mode": "parallel" or "sequential"\n'
        '- "review_threshold": integer 1-10 (higher = stricter quality bar)\n'
        '- "max_fix_attempts": integer >= 1 (review-fix cycles per module)\n'
        '- "security_focus": boolean — true for auth/security-sensitive work\n'
        '- "notes": a short string explaining your decision\n\n'
        "Example:\n"
        '{{"pause_for_plan_approval": false, "skip_build": false, '
        '"skip_tests": false, "execution_mode": "parallel", '
        '"review_threshold": 7, "max_fix_attempts": 3, '
        '"security_focus": false, "notes": "standard build"}}'
    )
