"""Persistent memoization — a cache that survives process restarts.

``persist_cache`` stores results under a Stash namespace, so an expensive call
computed in one run is free in the next. Like ``functools.lru_cache``, but on
disk and shared across processes.

Run it:  python examples/persistent_cache.py
"""

from __future__ import annotations

import tempfile
import time
from collections.abc import Callable
from pathlib import Path
from typing import Any

from objstash import Stash


def persist_cache(stash: Stash, name: str) -> Callable[[Callable[..., Any]], Callable[..., Any]]:
    """Decorator factory caching a function's results under ``stash[name]``."""
    cache = stash.setdefault(name, {})  # a DictProxy that writes through to disk

    def decorator(fn: Callable[..., Any]) -> Callable[..., Any]:
        def wrapper(*args: Any) -> Any:
            key = repr(args)
            if key not in cache:
                cache[key] = fn(*args)  # persisted on assignment
            return cache[key]

        return wrapper

    return decorator


def main() -> None:
    tmp = Path(tempfile.mkdtemp())
    db = str(tmp / "cache.db")
    try:
        stash = Stash(db)

        @persist_cache(stash, "squares")
        def slow_square(n: int) -> int:
            print(f"  computing {n}**2 (slow)...")
            time.sleep(0.5)
            return n * n

        print("First call:")
        print("  result:", slow_square(12))
        print("Second call, same args (no 'computing' line — served from cache):")
        print("  result:", slow_square(12))

        stash.close()

        # Prove it is on disk: a brand-new connection already has the value, so
        # the result would still be there after a real process restart.
        fresh = Stash(db)
        print("From a fresh connection (survives restart):", dict(fresh["squares"]))
        fresh.close()
    finally:
        for leftover in tmp.glob("*"):
            leftover.unlink()
        tmp.rmdir()


if __name__ == "__main__":
    main()
