#!/usr/bin/env python3
"""
scripts/compile_reqs.py

Regenerate ``req.txt`` from ``pyproject.toml`` using ``uv pip compile``.

Usage::

    uv run compile-reqs
    # or
    python -m scripts.compile_reqs
"""

import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]


def main() -> None:
    pyproject = REPO_ROOT / "pyproject.toml"
    req_txt = REPO_ROOT / "req.txt"

    if not pyproject.exists():
        print(f"ERROR: {pyproject} not found", file=sys.stderr)
        sys.exit(1)

    print(f"Compiling {pyproject} -> {req_txt} ...")
    result = subprocess.run(
        ["uv", "pip", "compile", str(pyproject), "-o", str(req_txt)],
        cwd=REPO_ROOT,
    )
    if result.returncode == 0:
        print(f"Done. Wrote {req_txt}")
    else:
        print(f"uv pip compile failed (exit code {result.returncode})", file=sys.stderr)
        sys.exit(result.returncode)


if __name__ == "__main__":
    main()
