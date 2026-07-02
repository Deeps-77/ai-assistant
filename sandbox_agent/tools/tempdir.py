import tempfile


def create_temp_directory(prefix: str = "ai_sandbox_") -> str:
    return tempfile.mkdtemp(prefix=prefix)
