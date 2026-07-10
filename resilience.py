import time
import random
import types
import functools
from typing import Any, Callable, Optional, Tuple, Type


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


# ── Decorator-based retry (used in tests) ──────────────────────

DEFAULT_RETRYABLE = (ConnectionError, TimeoutError, OSError)


def with_retry(
    max_attempts: int = 3,
    backoff: float = 1.0,
    retryable: Optional[Tuple[Type[Exception], ...]] = None,
) -> Callable:
    """Decorator: retry a function with exponential backoff on transient errors.

    Usage::

        @with_retry(max_attempts=3, backoff=0.5)
        def flaky_call():
            ...
    """
    if retryable is None:
        retryable = DEFAULT_RETRYABLE

    def decorator(func: Callable) -> Callable:
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            last_exception = None
            for attempt in range(max_attempts):
                try:
                    return func(*args, **kwargs)
                except retryable as e:
                    last_exception = e
                    if attempt < max_attempts - 1:
                        delay = min(backoff * (2 ** attempt) + random.uniform(0, 0.3), 10.0)
                        time.sleep(delay)
                    else:
                        raise
                except Exception:
                    # Non-retryable — propagate immediately
                    raise
            raise last_exception
        return wrapper
    return decorator
