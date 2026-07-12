---
name: run_tests
description: Run the active project's test suite using the correct command for its stack. Use this whenever you need to verify changes, after editing code, or before reporting work as done.
---

# Run Tests

Detect the project's stack and run its test suite via the `execute` tool.

## Detection -> command

- **Python** (`pyproject.toml` / `requirements.txt` with pytest): `uv run pytest -q` or `python -m pytest -q`
- **Node** (`package.json` with a `test` script): `npm test` (or `pnpm test` / `yarn test`)
- **Rust** (`Cargo.toml`): `cargo test`
- **Go** (`go.mod`): `go test ./...`

## Steps

1. From the project root, pick the command that matches the detected stack above.
2. Run it with `execute` and capture output.
3. If tests fail, read the failing output, locate the offending file/line, and fix it (or delegate a broader fix to `software_delivery`).
4. Re-run until green, then report a short summary (passed/failed counts).

## Notes

- Prefer the project's own test runner over ad-hoc commands.
- For very large suites, run a targeted subset first (e.g. `pytest tests/test_x.py`).
