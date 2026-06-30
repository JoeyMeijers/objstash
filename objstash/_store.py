"""SQLite-backed key/value storage.

A single table holds every value as a JSON payload alongside the name of the
codec used to produce it:

    CREATE TABLE stash (key TEXT PRIMARY KEY, value, codec TEXT NOT NULL)

The ``value`` column is declared without a type so it keeps SQLite's NONE
affinity; binding the JSON string stores it with TEXT storage class, which keeps
the database directly inspectable (``sqlite3 stash.db 'select * from stash'``).

Durability and concurrency: the connection runs in autocommit mode with WAL
journaling, so each write is committed immediately (no explicit save) while many
readers can run alongside a single writer. ``synchronous=NORMAL`` is durable
across process crashes; see docs/adr/ADR-0001 for the power-loss trade-off. A
reentrant process-wide lock guards the shared connection for thread safety.

The :meth:`Store.transaction` context manager opens an explicit transaction so a
batch of writes commits once, atomically. Because a transaction is global to the
shared connection, the lock is held for the batch's whole duration; other threads
block rather than having their writes swept into the batch. See ADR-0005.
"""

from __future__ import annotations

import sqlite3
import threading
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

_SCHEMA = "CREATE TABLE IF NOT EXISTS stash (key TEXT PRIMARY KEY, value, codec TEXT NOT NULL)"

#: Backslash used as the LIKE escape character in prefix queries.
_LIKE_ESCAPE = "\\"


def _like_pattern(prefix: str) -> str:
    """Build a LIKE pattern matching every key starting with ``prefix``.

    The wildcard characters ``%`` and ``_`` (and the escape character itself)
    are escaped, because key segments may legitimately contain them. An empty
    prefix yields ``"%"``, which matches all rows.
    """
    escaped = (
        prefix.replace(_LIKE_ESCAPE, _LIKE_ESCAPE * 2)
        .replace("%", _LIKE_ESCAPE + "%")
        .replace("_", _LIKE_ESCAPE + "_")
    )
    return escaped + "%"


class Store:
    """Thread-safe key/value access to a single SQLite database."""

    def __init__(self, path: str) -> None:
        self._lock = threading.RLock()
        self._depth = 0
        target = path if path == ":memory:" else str(Path(path))
        self._conn = sqlite3.connect(target, check_same_thread=False, isolation_level=None)
        with self._lock:
            self._conn.execute("PRAGMA journal_mode=WAL")
            self._conn.execute("PRAGMA synchronous=NORMAL")
            self._conn.execute(_SCHEMA)

    @contextmanager
    def transaction(self) -> Iterator[None]:
        """Run the block inside a single transaction, committing once at the end.

        Reentrant: nested calls join the outer transaction and only the
        outermost commits. Any exception rolls the whole transaction back. The
        connection lock is held for the duration, so concurrent writers wait.
        """
        with self._lock:
            if self._depth == 0:
                self._conn.execute("BEGIN")
            self._depth += 1
            try:
                yield
            except BaseException:
                self._depth -= 1
                if self._depth == 0:
                    self._conn.execute("ROLLBACK")
                raise
            else:
                self._depth -= 1
                if self._depth == 0:
                    self._conn.execute("COMMIT")

    def get(self, key: str) -> tuple[str, str] | None:
        """Return ``(codec, payload)`` for ``key`` or ``None`` if absent."""
        with self._lock:
            row = self._conn.execute(
                "SELECT codec, value FROM stash WHERE key = ?", (key,)
            ).fetchone()
        if row is None:
            return None
        return (row[0], row[1])

    def put(self, key: str, codec: str, payload: str) -> None:
        """Insert or replace the value stored under ``key``."""
        with self._lock:
            self._conn.execute(
                "INSERT INTO stash (key, value, codec) VALUES (?, ?, ?) "
                "ON CONFLICT(key) DO UPDATE SET value = excluded.value, codec = excluded.codec",
                (key, payload, codec),
            )

    def delete(self, key: str) -> bool:
        """Delete ``key``; return ``True`` if a row was removed."""
        with self._lock:
            cursor = self._conn.execute("DELETE FROM stash WHERE key = ?", (key,))
            return cursor.rowcount > 0

    def keys(self) -> list[str]:
        """Return all stored keys in sorted order."""
        return self.keys_with_prefix("")

    def keys_with_prefix(self, prefix: str) -> list[str]:
        """Return all keys starting with ``prefix`` (all keys if empty)."""
        with self._lock:
            rows = self._conn.execute(
                "SELECT key FROM stash WHERE key LIKE ? ESCAPE ? ORDER BY key",
                (_like_pattern(prefix), _LIKE_ESCAPE),
            ).fetchall()
        return [row[0] for row in rows]

    def has_prefix(self, prefix: str) -> bool:
        """Return whether any key starts with ``prefix``."""
        with self._lock:
            row = self._conn.execute(
                "SELECT 1 FROM stash WHERE key LIKE ? ESCAPE ? LIMIT 1",
                (_like_pattern(prefix), _LIKE_ESCAPE),
            ).fetchone()
        return row is not None

    def delete_prefix(self, prefix: str) -> int:
        """Delete every key starting with ``prefix``; return how many were removed."""
        with self._lock:
            cursor = self._conn.execute(
                "DELETE FROM stash WHERE key LIKE ? ESCAPE ?",
                (_like_pattern(prefix), _LIKE_ESCAPE),
            )
            return cursor.rowcount

    def checkpoint(self) -> None:
        """Fold the write-ahead log into the main file and truncate it.

        A no-op for databases not in WAL mode (e.g. ``:memory:``).
        """
        with self._lock:
            self._conn.execute("PRAGMA wal_checkpoint(TRUNCATE)")

    def close(self) -> None:
        """Close the underlying database connection."""
        with self._lock:
            self._conn.close()
