import os
from pathlib import Path
from sandbox_agent.context import SandboxStack


_STACK_SIGNATURES: list[tuple[str, str, SandboxStack]] = [
    (
        "python",
        "requirements.txt",
        SandboxStack(
            name="python",
            test_cmd=["pytest", "-v"],
            dep_cmd=["pip", "install"],
            test_file_patterns=["**/test_*.py", "**/*_test.py", "**/tests/**/*.py"],
            docker_default_image="python:3.12-slim",
        ),
    ),
    (
        "python",
        "pyproject.toml",
        SandboxStack(
            name="python",
            test_cmd=["pytest", "-v"],
            dep_cmd=["pip", "install"],
            test_file_patterns=["**/test_*.py", "**/*_test.py", "**/tests/**/*.py"],
            docker_default_image="python:3.12-slim",
        ),
    ),
    (
        "node",
        "package.json",
        SandboxStack(
            name="node",
            test_cmd=["npm", "test"],
            dep_cmd=["npm", "ci"],
            test_file_patterns=[
                "**/*.test.js", "**/*.test.ts",
                "**/*.spec.js", "**/*.spec.ts",
                "**/__tests__/**/*.js", "**/__tests__/**/*.ts",
            ],
            docker_default_image="node:20-slim",
        ),
    ),
    (
        "rust",
        "Cargo.toml",
        SandboxStack(
            name="rust",
            test_cmd=["cargo", "test"],
            dep_cmd=["cargo", "build"],
            test_file_patterns=[],
            docker_default_image="rust:1.77-slim",
        ),
    ),
    (
        "go",
        "go.mod",
        SandboxStack(
            name="go",
            test_cmd=["go", "test", "./..."],
            dep_cmd=["go", "mod", "download"],
            test_file_patterns=["**/*_test.go"],
            docker_default_image="golang:1.22",
        ),
    ),
    (
        "java",
        "pom.xml",
        SandboxStack(
            name="java",
            test_cmd=["mvn", "test"],
            dep_cmd=["mvn", "dependency:resolve"],
            test_file_patterns=["**/*Test.java"],
            docker_default_image="maven:3.9-eclipse-temurin-21",
        ),
    ),
    (
        "java",
        "build.gradle",
        SandboxStack(
            name="java",
            test_cmd=["gradle", "test"],
            dep_cmd=["gradle", "dependencies"],
            test_file_patterns=["**/*Test.java", "**/*Spec.groovy"],
            docker_default_image="gradle:8-jdk21",
        ),
    ),
    (
        "dotnet",
        ".csproj",
        SandboxStack(
            name="dotnet",
            test_cmd=["dotnet", "test"],
            dep_cmd=["dotnet", "restore"],
            test_file_patterns=["**/*Test.cs", "**/*Tests.cs"],
            docker_default_image="mcr.microsoft.com/dotnet/sdk:8.0",
        ),
    ),
]


def _check_file_exists(project_path: str, filename: str) -> bool:
    path = os.path.join(project_path, filename)
    return os.path.isfile(path)


def _check_file_pattern(project_path: str, pattern: str) -> bool:
    for p in Path(project_path).glob(f"**/{pattern}"):
        if p.is_file():
            return True
    return False


def detect_stack(project_path: str, tech_stack_hint: str = "") -> SandboxStack:
    for stack_name, signature, stack in _STACK_SIGNATURES:
        found = _check_file_exists(project_path, signature)
        if not found:
            found = _check_file_pattern(project_path, signature)
        if found:
            return stack

    hint_lower = tech_stack_hint.lower()
    if "node" in hint_lower or "express" in hint_lower or "react" in hint_lower or "vue" in hint_lower or "svelte" in hint_lower or "javascript" in hint_lower or "typescript" in hint_lower:
        return _STACK_SIGNATURES[2][2]
    if "rust" in hint_lower:
        return _STACK_SIGNATURES[3][2]
    if "go" in hint_lower:
        return _STACK_SIGNATURES[4][2]
    if "java" in hint_lower or "maven" in hint_lower:
        return _STACK_SIGNATURES[5][2]
    if "dotnet" in hint_lower or "c#" in hint_lower or ".net" in hint_lower:
        return _STACK_SIGNATURES[7][2]

    return _STACK_SIGNATURES[0][2]
