"""CLI state — remember things between runs, like UserDefaults / @AppStorage.

Tracks how many times this script has run, when it last ran, and a list of
"recent files" — all persisted with no save step. Run it several times and
watch the counter climb and the recent list update.

Run it:  python examples/cli_state.py [path ...]
"""

from __future__ import annotations

import sys
import tempfile
from datetime import datetime
from pathlib import Path

from objstash import Stash

# A stable path on purpose: re-running this script (a real process restart) shows
# the state persisting. A real tool would use its OS application-data directory.
DB = str(Path(tempfile.gettempdir()) / "stash_cli_demo.db")


def main(paths: list[str]) -> None:
    stash = Stash(DB)

    run_number = stash.setdefault("runs", 0) + 1
    stash.runs = run_number

    previous_run = stash.get("last_run")
    stash.last_run = datetime.now()

    recent = stash.setdefault("recent", [])
    for path in paths:
        recent.append(path)
    recent[:] = recent[-5:]  # keep the 5 most recent, persisted

    print(f"This is run #{run_number} of this demo.")
    print(f"Previous run: {previous_run or '(first run)'}")
    print(f"Recent files: {list(recent) or '(none — pass some paths as arguments)'}")
    print(f"\nState lives at {DB}")
    print("Run this again to watch it remember.")

    stash.close()


if __name__ == "__main__":
    main(sys.argv[1:])
