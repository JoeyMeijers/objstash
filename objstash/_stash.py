"""The public :class:`Stash` object: a persistent namespace over SQLite.

``Stash`` is the root node of a tree of values and nested namespaces. Assigning
an attribute persists it immediately; nested attributes create sections on
demand::

    stash = Stash("app.db")
    stash.theme = "dark"
    stash.window.width = 1200      # creates the "window" namespace
    stash.window.height = 800

Most behaviour lives in :class:`stash._namespace._Node`, shared with
:class:`~stash._namespace.Namespace`. ``Stash`` adds connection lifecycle.

Reserved names: methods such as ``get``, ``setdefault``, ``keys``, ``to_dict``
and ``close`` live on the class, so ``stash.get`` returns the method, not a
stored value. Use item access (``stash["get"]``) for keys that collide with a
method name or are not valid identifiers.
"""

from __future__ import annotations

from contextlib import AbstractContextManager

from ._namespace import _Node
from ._store import Store


class Stash(_Node):
    """A persistent namespace backed by SQLite.

    Example:
        >>> stash = Stash(":memory:")
        >>> stash.theme = "dark"
        >>> stash.theme
        'dark'
        >>> stash.window.width = 1200
        >>> stash.window.to_dict()
        {'width': 1200}
    """

    def __init__(self, path: str = "stash.db") -> None:
        """Open (creating if needed) the stash at ``path``.

        Args:
            path: Database file path. Defaults to ``stash.db`` in the current
                directory; use an explicit path for anything beyond quick
                scripts. ``":memory:"`` creates an ephemeral, in-process stash.
        """
        object.__setattr__(self, "_store", Store(path))
        object.__setattr__(self, "_prefix", "")

    def batch(self) -> AbstractContextManager[None]:
        """Coalesce every write in the block into one atomic transaction.

        Faster for hot loops (one commit instead of many) and all-or-nothing:
        an exception inside the block rolls back every write made within it.

        Example:
            >>> stash = Stash(":memory:")
            >>> with stash.batch():
            ...     for i in range(1000):
            ...         stash[f"k{i}"] = i
        """
        return self._store.transaction()

    def checkpoint(self) -> None:
        """Fold the write-ahead log into the database file and shrink it.

        Optional maintenance: the WAL is managed automatically, but calling this
        collapses pending changes into the main file — handy before copying or
        shipping the database. A no-op for an in-memory stash.
        """
        self._store.checkpoint()

    def close(self) -> None:
        """Close the underlying database connection."""
        self._store.close()

    def __enter__(self) -> Stash:
        return self

    def __exit__(self, *exc: object) -> None:
        self.close()

    def __repr__(self) -> str:
        return f"Stash(keys={self.keys()!r})"
