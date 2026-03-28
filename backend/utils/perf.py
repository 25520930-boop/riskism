"""
Riskism - Performance utilities
Structured logging, timing, and caching helpers.
"""
import time
import hashlib
import functools
from datetime import datetime, timedelta
from typing import Any, Callable, Dict, Optional


class PerfTimer:
    """Context manager for timing code blocks with structured output."""

    def __init__(self, label: str, log_fn=None):
        self.label = label
        self.log_fn = log_fn or (lambda msg: print(f"[PERF] {msg}"))
        self.elapsed = 0.0

    def __enter__(self):
        self._start = time.perf_counter()
        return self

    def __exit__(self, *args):
        self.elapsed = (time.perf_counter() - self._start) * 1000  # ms
        self.log_fn(f"{self.label}: {self.elapsed:.1f}ms")


class TTLCache:
    """Simple in-memory TTL cache with max-size eviction."""

    def __init__(self, maxsize: int = 256, ttl_seconds: int = 300):
        self.maxsize = maxsize
        self.ttl = ttl_seconds
        self._store: Dict[str, tuple] = {}  # key -> (value, expiry_time)

    def _make_key(self, *args, **kwargs) -> str:
        raw = str(args) + str(sorted(kwargs.items()))
        return hashlib.md5(raw.encode()).hexdigest()

    def get(self, key: str) -> Optional[Any]:
        if key in self._store:
            value, expiry = self._store[key]
            if time.time() < expiry:
                return value
            del self._store[key]
        return None

    def set(self, key: str, value: Any):
        # Evict oldest if at capacity
        if len(self._store) >= self.maxsize:
            oldest_key = min(self._store, key=lambda k: self._store[k][1])
            del self._store[oldest_key]
        self._store[key] = (value, time.time() + self.ttl)

    def clear(self):
        self._store.clear()

    @property
    def size(self):
        return len(self._store)


def cached_ttl(ttl_seconds: int = 300, maxsize: int = 128):
    """Decorator: cache function results with TTL."""
    cache = TTLCache(maxsize=maxsize, ttl_seconds=ttl_seconds)

    def decorator(fn: Callable):
        @functools.wraps(fn)
        def wrapper(*args, **kwargs):
            key = cache._make_key(fn.__name__, *args, **kwargs)
            cached = cache.get(key)
            if cached is not None:
                return cached
            result = fn(*args, **kwargs)
            cache.set(key, result)
            return result
        wrapper.cache = cache
        return wrapper
    return decorator
