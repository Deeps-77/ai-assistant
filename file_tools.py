import os
import re
from pathlib import Path
from typing import Dict, List, Optional


def parse_folder_structure(structure_str: str) -> List[str]:
    lines = [re.sub(r'#.*$', '', l).rstrip() for l in structure_str.split("\n") if l.strip()]
    lines = [l for l in lines if l.strip()]
    if not lines:
        return []

    def _tree_prefix_count(s: str) -> int:
        """Count tree-drawing connectors (├ └ │) in the leading portion."""
        count = 0
        for ch in s:
            if ch in '├└│':
                count += 1
            elif ch in ' ─':
                continue
            else:
                break
        return count

    def _strip_tree_prefix(s: str) -> str:
        return re.sub(r'^[├└│─\s]+', '', s).strip()

    is_tree = any(_tree_prefix_count(l.lstrip()) > 0 for l in lines)

    if not is_tree:
        indents = sorted({len(l) - len(l.lstrip()) for l in lines})
        non_zero = [i for i in indents if i > 0]
        if non_zero:
            import math
            step = math.gcd(*non_zero)
        else:
            step = 2
    else:
        step = 0

    entries: list[tuple[int, str, bool]] = []

    for line in lines:
        if is_tree:
            level = _tree_prefix_count(line.lstrip())
            name = _strip_tree_prefix(line)
            if not name:
                continue
        else:
            ws = len(line) - len(line.lstrip())
            level = ws // step if step else 0
            name = line.strip()
            if not name:
                continue

        is_dir = name.endswith("/") or not Path(name.rstrip("/")).suffix
        name = name.rstrip("/")
        entries.append((level, name, is_dir))

    dirs: set[str] = set()
    path_stack: list[str] = []

    for level, name, is_dir in entries:
        if level < len(path_stack):
            del path_stack[level:]
        while level > len(path_stack):
            path_stack.append(name)

        if is_dir:
            if level == len(path_stack):
                path_stack.append(name)
            else:
                path_stack[level:] = [name]
            dirs.add("/".join(path_stack))
        else:
            if path_stack:
                dirs.add("/".join(path_stack))

    all_dirs: set[str] = set()
    for d in dirs:
        parts = d.replace("\\", "/").split("/")
        for i in range(1, len(parts) + 1):
            all_dirs.add("/".join(parts[:i]))

    return sorted(all_dirs, key=lambda x: (x.count("/"), x))


def ensure_directory(path: str) -> None:
    os.makedirs(path, exist_ok=True)


def write_file(filepath: str, content: str) -> str:
    try:
        path = Path(filepath)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")
        return "ok"
    except Exception as e:
        return f"error: {e}"


def read_file(filepath: str) -> Optional[str]:
    try:
        return Path(filepath).read_text(encoding="utf-8")
    except (FileNotFoundError, OSError):
        return None


def parse_code_blocks(raw_code: str) -> Dict[str, str]:
    if not raw_code.strip():
        return {}

    files: Dict[str, str] = {}

    header_pattern = re.compile(
        r'^[#\s]*[-=]{3,}\s*(.+?)\s*[-=]{3,}\s*$|'
        r'^[#\s]*filename:\s*(.+?)\s*$|'
        r'^[#\s]*[Ff]ile:\s*(.+?)\s*$',
        re.MULTILINE
    )

    lines = raw_code.split("\n")
    current_path: Optional[str] = None
    current_content: List[str] = []

    for line in lines:
        m = header_pattern.match(line)
        if m:
            if current_path:
                files[current_path] = cleanup_code_block_markers(
                    "\n".join(current_content)
                )
            current_path = next(g for g in m.groups() if g is not None).strip()
            current_content = []
        elif current_path is not None:
            current_content.append(line)

    if current_path:
        files[current_path] = cleanup_code_block_markers(
            "\n".join(current_content)
        )

    if files:
        return files

    code_block_pattern = re.compile(r'```(?:\w+)?\n(.*?)```', re.DOTALL)
    for match in code_block_pattern.finditer(raw_code):
        block = match.group(1).strip()
        if not block:
            continue
        first_line = block.split("\n")[0]
        path_match = re.match(r'^[#\s/]*([\w./-]+\.\w+)\s*$', first_line)
        if path_match:
            path = path_match.group(1).strip()
            content = "\n".join(block.split("\n")[1:]).strip()
            if content:
                files[path] = content

    return files


def cleanup_code_block_markers(raw_code: str) -> str:
    result = re.sub(r'^```\w*\s*$', '', raw_code, flags=re.MULTILINE)
    result = re.sub(r'^```\s*$', '', result, flags=re.MULTILINE)
    result = re.sub(r'^# --- .+$', '', result, flags=re.MULTILINE)
    result = re.sub(r'^# filename: .+$', '', result, flags=re.MULTILINE)
    result = re.sub(r'^# File: .+$', '', result, flags=re.MULTILINE)
    return result.strip()


def write_module_files(base_path: str, module: str, code: str,
                       folder_structure: str = "") -> Dict[str, str]:
    results: Dict[str, str] = {}
    files = parse_code_blocks(code)

    if not files:
        module_dir = os.path.join(base_path, module)
        filepath = os.path.join(module_dir, module)
        status = write_file(filepath, cleanup_code_block_markers(code))
        results[os.path.relpath(filepath, base_path).replace("\\", "/")] = status
    else:
        for rel_path, content in files.items():
            full_path = os.path.join(base_path, rel_path.replace("\\", "/"))
            status = write_file(full_path, cleanup_code_block_markers(content))
            results[rel_path.replace("\\", "/")] = status

    return results


def write_test_files(base_path: str, tests: Dict[str, str]) -> Dict[str, str]:
    results: Dict[str, str] = {}
    for module, content in tests.items():
        files = parse_code_blocks(content)
        if files:
            for rel_path, file_content in files.items():
                full_path = os.path.join(base_path, rel_path.replace("\\", "/"))
                status = write_file(full_path, cleanup_code_block_markers(file_content))
                results[rel_path.replace("\\", "/")] = status
        else:
            filepath = os.path.join(base_path, module)
            status = write_file(filepath, cleanup_code_block_markers(content))
            results[os.path.relpath(filepath, base_path).replace("\\", "/")] = status
    return results


def generate_config_files(project_path: str, tech_stack: str,
                          project_name: str = "") -> Dict[str, str]:
    results: Dict[str, str] = {}
    if not project_name:
        project_name = os.path.basename(os.path.abspath(project_path))

    tech = tech_stack.lower()

    if any(k in tech for k in ("python", "fastapi", "django", "flask")):
        pyproject = f"""[project]
name = "{project_name}"
version = "0.1.0"
description = "Generated by AI Software Delivery Team"
requires-python = ">=3.12"
dependencies = []
"""
        results["pyproject.toml"] = write_file(
            os.path.join(project_path, "pyproject.toml"), pyproject)
        results["requirements.txt"] = write_file(
            os.path.join(project_path, "requirements.txt"),
            "# Add your dependencies here\n")
        results[".env.example"] = write_file(
            os.path.join(project_path, ".env.example"),
            "# Environment Variables\nDATABASE_URL=\nSECRET_KEY=\n")

    elif any(k in tech for k in ("node", "express", "react", "vue", "svelte")):
        pkg = f"""{{
  "name": "{project_name}",
  "version": "1.0.0",
  "description": "Generated by AI Software Delivery Team",
  "main": "index.js",
  "scripts": {{}},
  "dependencies": {{}},
  "devDependencies": {{}}
}}
"""
        results["package.json"] = write_file(
            os.path.join(project_path, "package.json"), pkg)
        results[".env.example"] = write_file(
            os.path.join(project_path, ".env.example"),
            "# Environment Variables\nDATABASE_URL=\nSECRET_KEY=\n")

    elif "rust" in tech:
        cargo = f"""[package]
name = "{project_name}"
version = "0.1.0"
edition = "2021"

[dependencies]
"""
        results["Cargo.toml"] = write_file(
            os.path.join(project_path, "Cargo.toml"), cargo)

    elif "go" in tech:
        results["go.mod"] = write_file(
            os.path.join(project_path, "go.mod"),
            f"module {project_name}\n\ngo 1.22\n")

    gitignore_map = {
        "python": "*.pyc\n__pycache__/\n.venv/\n.env\n*.egg-info/\ndist/\nbuild/\n.pytest_cache/\n",
        "node": "node_modules/\n.env\ndist/\nbuild/\n*.log\n.next/\n",
        "rust": "target/\n.env\n",
        "go": "bin/\n.env\n*.exe\n",
    }
    gitignore_key = "python"
    for key in gitignore_map:
        if key in tech:
            gitignore_key = key
            break
    results[".gitignore"] = write_file(
        os.path.join(project_path, ".gitignore"), gitignore_map[gitignore_key])

    return results


def init_project_structure(base_path: str, folder_structure: str) -> None:
    dirs = parse_folder_structure(folder_structure)
    for d in dirs:
        if d == ".":
            continue
        full_path = os.path.join(base_path, d.replace("\\", "/"))
        ensure_directory(full_path)


def read_project_structure(project_path: str) -> str:
    base = Path(project_path)
    if not base.exists():
        return f"[Project path not found: {project_path}]"

    lines: List[str] = [f"{base.name}/"]
    _build_tree(base, lines, "")
    return "\n".join(lines)


def _build_tree(path: Path, lines: List[str], prefix: str) -> None:
    entries = sorted(path.iterdir(), key=lambda p: (not p.is_dir(), p.name.lower()))
    entries = [e for e in entries if not e.name.startswith(".") and e.name != "__pycache__"]

    for i, entry in enumerate(entries):
        is_last = i == len(entries) - 1
        connector = "└── " if is_last else "├── "
        lines.append(f"{prefix}{connector}{entry.name}")
        if entry.is_dir():
            extension = "    " if is_last else "│   "
            _build_tree(entry, lines, prefix + extension)


def read_project_files(project_path: str,
                       patterns: Optional[List[str]] = None) -> Dict[str, str]:
    if patterns is None:
        patterns = ["**/*.py", "**/*.js", "**/*.ts", "**/*.rs", "**/*.go",
                     "**/*.toml", "**/*.json", "**/*.yaml", "**/*.yml",
                     "**/*.md", "**/*.env*", "**/*.txt"]

    base = Path(project_path)
    if not base.exists():
        return {}

    files: Dict[str, str] = {}
    for pattern in patterns:
        for path in base.glob(pattern):
            if (path.is_file()
                    and "node_modules" not in str(path)
                    and ".venv" not in str(path)
                    and "__pycache__" not in str(path)):
                rel = str(path.relative_to(base)).replace("\\", "/")
                content = read_file(str(path))
                if content is not None:
                    files[rel] = content
    return files


def extract_folder_structure_from_architecture(architecture: str) -> str:
    if not architecture:
        return ""

    if "## Folder Structure" in architecture:
        section = architecture.split("## Folder Structure")[1]
        if "##" in section:
            section = section.split("##")[0]
        return section.strip()

    if "folder_structure" in architecture:
        m = re.search(
            r'folder_structure["\']?\s*:\s*["\'](.+?)["\']',
            architecture, re.DOTALL
        )
        if m:
            return m.group(1).strip()

    if "folder_structure" in architecture:
        m = re.search(
            r'folder_structure["\']?\s*:\s*\n\s*([\s\S]*?)(?=\n\s*\w+|$)',
            architecture
        )
        if m:
            return m.group(1).strip()

    return ""
