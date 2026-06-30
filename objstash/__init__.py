"""Stash: use Python objects, forget databases.

A persistent namespace backed by SQLite. Assign values to attributes and they
are transparently saved; read them back in a later process.

    >>> from objstash import Stash
    >>> stash = Stash("app.db")
    >>> stash.theme = "dark"
    >>> stash.setdefault("counter", 0)
    0
"""

from __future__ import annotations

from ._codecs import register_type
from ._exceptions import StashError, UnsupportedTypeError
from ._namespace import Namespace
from ._stash import Stash

__all__ = ["Stash", "Namespace", "register_type", "StashError", "UnsupportedTypeError"]
__version__ = "0.2.0"
