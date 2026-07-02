import re
from typing import Optional


def parse_pytest_output(stdout: str, stderr: str) -> dict:
    result = {
        "passed": 0,
        "failed": 0,
        "errors": 0,
        "output": stdout + "\n" + stderr,
        "success": False,
        "failures": [],
    }

    summary_match = re.search(r'=+\s+(\d+) passed', stdout)
    if summary_match:
        result["passed"] = int(summary_match.group(1))

    failed_match = re.search(r'(\d+) failed', stdout)
    if failed_match:
        result["failed"] = int(failed_match.group(1))

    errors_match = re.search(r'(\d+) error', stdout)
    if errors_match:
        result["errors"] = int(errors_match.group(1))

    failure_blocks = re.findall(
        r'FAILED\s+(\S+)\s*-\s*(.+?)(?=\n\s*(?:FAILED|ERRORS|PASSED|short test summary|=+|$))',
        stdout,
        re.DOTALL,
    )
    for test_name, message in failure_blocks:
        result["failures"].append({
            "name": test_name.strip(),
            "message": message.strip()[:500],
            "traceback": "",
        })

    error_blocks = re.findall(
        r'ERROR\s+(\S+)\s*-\s*(.+?)(?=\n\s*(?:FAILED|ERRORS|PASSED|short test summary|=+|$))',
        stdout,
        re.DOTALL,
    )
    for test_name, message in error_blocks:
        result["failures"].append({
            "name": test_name.strip(),
            "message": message.strip()[:500],
            "traceback": "",
        })

    total = result["passed"] + result["failed"] + result["errors"]
    result["success"] = total > 0 and result["failed"] == 0 and result["errors"] == 0

    result["output"] = stdout[-3000:] + "\n" + stderr[-2000:]
    return result


def parse_jest_output(stdout: str, stderr: str) -> dict:
    result = {
        "passed": 0,
        "failed": 0,
        "errors": 0,
        "output": stdout + "\n" + stderr,
        "success": False,
        "failures": [],
    }

    tests_match = re.search(r'Tests:\s+(\d+) passed', stdout)
    if tests_match:
        result["passed"] = int(tests_match.group(1))

    failed_match = re.search(r'(\d+) failed', stdout)
    if failed_match:
        result["failed"] = int(failed_match.group(1))

    suites_match = re.search(r'(\d+) total', stdout)
    if tests_match and not failed_match:
        result["passed"] = int(tests_match.group(1))

    result["success"] = result["failed"] == 0 and result["errors"] == 0
    result["output"] = stdout[-3000:] + "\n" + stderr[-2000:]
    return result


def parse_cargo_output(stdout: str, stderr: str) -> dict:
    result = {
        "passed": 0,
        "failed": 0,
        "errors": 0,
        "output": stdout + "\n" + stderr,
        "success": False,
        "failures": [],
    }

    ok_match = re.search(r'test result:\s+ok\.\s+(\d+) passed', stdout)
    if ok_match:
        result["passed"] = int(ok_match.group(1))
        result["success"] = True
        return result

    failed_match = re.search(r'(\d+) passed;\s*(\d+) failed', stdout)
    if failed_match:
        result["passed"] = int(failed_match.group(1))
        result["failed"] = int(failed_match.group(2))

    error_match = re.search(r'error\[E\d+\]', stderr)
    if error_match:
        result["errors"] = 1

    result["success"] = result["failed"] == 0 and result["errors"] == 0
    result["output"] = stdout[-3000:] + "\n" + stderr[-2000:]
    return result


def parse_go_output(stdout: str, stderr: str) -> dict:
    result = {
        "passed": 0,
        "failed": 0,
        "errors": 0,
        "output": stdout + "\n" + stderr,
        "success": False,
        "failures": [],
    }

    fail_lines = re.findall(r'^---\s+FAIL:\s+(.+)$', stdout, re.MULTILINE)
    pass_lines = re.findall(r'^---\s+PASS:\s+(.+)$', stdout, re.MULTILINE)
    result["passed"] = len(pass_lines)
    result["failed"] = len(fail_lines)

    overall_fail = re.search(r'^(?:FAIL|ok)\s+', stdout, re.MULTILINE)
    if overall_fail:
        result["success"] = "FAIL" not in stdout.split("\n")[0] if stdout else False

    if result["passed"] == 0 and result["failed"] == 0:
        ok_match = re.search(r'^ok\s+\S+\s+([\d.]+)s', stdout, re.MULTILINE)
        if ok_match:
            result["passed"] = 1
            result["success"] = True

    result["success"] = result["failed"] == 0 and result["errors"] == 0
    result["output"] = stdout[-3000:] + "\n" + stderr[-2000:]
    return result


_STACK_PARSERS: dict[str, callable] = {
    "python": parse_pytest_output,
    "node": parse_jest_output,
    "rust": parse_cargo_output,
    "go": parse_go_output,
    "java": parse_pytest_output,
    "dotnet": parse_pytest_output,
}


def parse_output(stack_name: str, stdout: str, stderr: str) -> dict:
    parser = _STACK_PARSERS.get(stack_name, parse_pytest_output)
    return parser(stdout, stderr)
