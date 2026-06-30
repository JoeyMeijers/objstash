# ADR-0006: A `stash.ext` module for optional conveniences

## Status

Rejected (reverted before any release)

> **Reversal note.** The `stash.ext.cache` decorator was implemented and then
> removed. On reflection it did not earn a place in the library: it duplicates
> dedicated tools (`diskcache`, `joblib.Memory`), lacked TTL/eviction (limiting
> it to values that never change), and was not a reason anyone would adopt Stash.
> The pattern now lives only as a recipe in `examples/persistent_cache.py`, and
> the core stays lean. The original reasoning is kept below for the record, and
> as a guard against re-proposing a built-in cache without a stronger case.

## Context

Common patterns (e.g. persistent memoization) are valuable to ship, but adding
them to the package root risks turning a small, one-purpose library into a
kitchen-sink framework — directly against the project's non-goals and its
KISS/YAGNI stance. We want a place for batteries-included helpers that does not
dilute the core API contract.

## Decision

**Put optional conveniences in a separate `stash.ext` module**, imported
explicitly (`from stash.ext import cache`) and *not* re-exported from the package
root. The core (`from stash import Stash, ...`) stays minimal; `stash.ext` is the
clearly-labelled home for higher-level helpers.

The first member is `cache(stash, name)`, a persistent memoization decorator:

- **One row per cache entry** (`name.<sha256>`), not a single growing dict, so
  inserts are O(1) and concurrent processes caching different arguments do not
  clobber one another (preserves the WAL multi-process story, ADR-0001).
- **Keys** are derived by canonicalizing the call's arguments through Stash's own
  serializer (deterministic across runs, supports registered types) and hashing
  the result with SHA-256 (no dot/length issues; unserializable arguments raise
  `UnsupportedTypeError`).
- **Fresh read per call** so a process sees entries written by others.
- The wrapped function exposes `cache_clear()` to drop all entries for that name.

## Consequences

### Positive

- Ships a genuinely useful helper without growing the core surface.
- The cache is concurrency-safe and persists across restarts.
- Establishes a clear convention: conveniences live in `stash.ext`, behind an
  explicit import, and can be added or changed without touching the core.

### Negative

- A second public surface to document, test, and version (mitigated by keeping it
  small and explicit).
- The memoization is not call-locked: two threads missing the same key may both
  compute it (the second simply overwrites with the same value). Matches
  `functools.lru_cache`'s unlocked behavior.
- Result values are subject to the same serialization rules as any stored value.

## Alternatives

- **Put helpers in the package root** — rejected: blurs the core contract and
  invites scope creep.
- **Examples only, no shipped helper** — reasonable, but a correct, concurrency-
  safe cache is easy to get subtly wrong; shipping one tested implementation is
  worth more than a copy-paste recipe.
- **A single-dict cache** — rejected: O(n) re-serialization per entry and
  cross-process clobbering.
