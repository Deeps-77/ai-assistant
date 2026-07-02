from langchain_core.prompts import ChatPromptTemplate


def planner_prompt() -> ChatPromptTemplate:
    return ChatPromptTemplate.from_template(
        "You are a software planner. Analyze the following requirement and "
        "break it into user stories and backend modules.\n"
        "Module names must be simple lowercase strings like 'auth', 'users', 'inventory'.\n\n"
        "Requirement: {requirement}\n\n"
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
        "Return ONLY code inside markdown code blocks, one per file. "
        "Separate files with a header like:\n"
        "# --- exact/path/from/above/file.ext ---\n"
        "```\n...code...\n```\n"
        "DO NOT add any files not listed. DO NOT change the paths."
    )


def reviewer_prompt() -> ChatPromptTemplate:
    return ChatPromptTemplate.from_template(
        "You are a strict {tech_stack} code reviewer. "
        "Review this code for the '{module}' module.\n\n"
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
        "Return ONLY the corrected code in a markdown block."
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
