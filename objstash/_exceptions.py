"""Exception hierarchy for Stash.

All errors raised by Stash derive from :class:`StashError`, so callers can
catch the whole library with a single ``except`` while still being able to
distinguish specific failures.
"""

from __future__ import annotations


class StashError(Exception):
    """Base class for every error raised by Stash."""


class UnsupportedTypeError(StashError, TypeError):
    """Raised when a value has no registered codec and cannot be serialized.

    Subclasses :class:`TypeError` as well so that existing ``except TypeError``
    handlers around serialization keep working.
    """
