"""Resumable job — record progress so an interrupted run can resume.

A persisted set of completed item IDs means a crash (or Ctrl-C, or a power cut)
only costs the item in flight: the next run skips everything already done. This
is the mutation-persistence feature doing the work — ``done.add(id)`` is written
to disk immediately, with no explicit save.

Run it:  python examples/resumable_job.py
"""

from __future__ import annotations

import tempfile
from pathlib import Path

from objstash import Stash

ITEMS = list(range(1, 11))


def process(item: int) -> None:
    """Pretend to do real, expensive, side-effecting work."""


def run_session(db: str, crash_at: int | None = None) -> list[int]:
    """Process every not-yet-done item, optionally "crashing" at one of them.

    Returns the items this session completed.
    """
    stash = Stash(db)
    try:
        done = stash.setdefault("done", set())
        completed_now: list[int] = []
        for item in ITEMS:
            if item in done:
                continue
            if item == crash_at:
                raise RuntimeError(f"simulated crash before item {item}")
            process(item)
            done.add(item)  # persisted immediately
            completed_now.append(item)
        return completed_now
    finally:
        stash.close()


def main() -> None:
    tmp = Path(tempfile.mkdtemp())
    db = str(tmp / "resumable_job.db")
    try:
        print("Session 1 (crashes partway through)...")
        try:
            run_session(db, crash_at=6)
        except RuntimeError as exc:
            print(f"  {exc}")

        stash = Stash(db)
        print(f"  survived the crash: {sorted(stash.done)}")
        stash.close()

        print("Session 2 (resumes where it left off)...")
        completed = run_session(db)
        print(f"  completed this run: {completed}")

        stash = Stash(db)
        print(f"  everything done:    {sorted(stash.done)}")
        stash.close()
    finally:
        for leftover in tmp.glob("*"):
            leftover.unlink()
        tmp.rmdir()


if __name__ == "__main__":
    main()
