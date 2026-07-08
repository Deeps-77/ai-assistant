import time
import random
import types
from typing import Any


def add_retry_to_llm(llm, max_retries: int = 2) -> Any:
    """Wrap an LLM instance's .invoke() with exponential backoff retry.

    Transient errors (ConnectionError, TimeoutError, OSError) trigger a retry
    with exponential backoff + jitter. Logic errors (parsing, validation) are
    not retried — they propagate immediately.

    Uses object.__setattr__ to bypass Pydantic v2's frozen attribute check
    so derived runnables (with_structured_output, prompt|llm, etc.) inherit
    the retry behavior.
    """
    original_invoke = llm.invoke

    def retry_invoke(self, *args, **kwargs):
        last_exception = None
        for attempt in range(max_retries + 1):
            try:
                return original_invoke(*args, **kwargs)
            except (ConnectionError, TimeoutError, OSError) as e:
                last_exception = e
                if attempt < max_retries:
                    delay = min(1.0 * (2 ** attempt) + random.uniform(0, 0.5), 10.0)
                    print(f"   LLM retry {attempt+1}/{max_retries} after {delay:.1f}s: {e}")
                    time.sleep(delay)
                else:
                    print(f"   LLM retries exhausted ({max_retries+1} attempts): {e}")
                    raise
            except Exception:
                # Logic errors — do NOT retry
                raise
        raise last_exception

    bound = types.MethodType(retry_invoke, llm)
    object.__setattr__(llm, "invoke", bound)
    return llm
