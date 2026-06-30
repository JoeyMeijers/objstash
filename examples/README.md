# Examples

Runnable scripts showing what Stash is good at. Each is self-contained and
leaves nothing behind (except `cli_state.py`, which keeps a small file on
purpose so repeated runs can demonstrate persistence).

```bash
uv run python examples/resumable_job.py
uv run python examples/persistent_cache.py
uv run python examples/cli_state.py ~/notes.md ~/todo.md
```

- **[resumable_job.py](resumable_job.py)** — a crash-safe job. A persisted set of
  completed IDs lets an interrupted run resume without redoing finished work.
- **[persistent_cache.py](persistent_cache.py)** — a memoization decorator whose
  cache survives process restarts: `functools.lru_cache`, but on disk.
- **[cli_state.py](cli_state.py)** — remembering state between runs (run counter,
  last-run time, recent files), the Python equivalent of `UserDefaults` /
  `@AppStorage`. Run it repeatedly to watch it remember.
