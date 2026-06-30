# ADR-0004: Transparent mutation persistence via proxies

## Status

Accepted

## Context

The defining feature of Stash over `shelve`/`sqlitedict` is that in-place
mutation of a stored container persists without reassignment:

```python
stash.tags = []
stash.tags.append("x")   # must be saved
```

A naive implementation decodes a fresh value on read, so the `append` happens on
a throwaway object and is silently lost — the exact data-loss trap those other
libraries have. Solving it is what makes Stash worth a dependency.

## Decision

**Reading a stored `list`/`dict`/`set` returns a proxy that mutates in place and
re-serializes the whole top-level value on every change.**

- A proxy (`ListProxy`/`DictProxy`/`SetProxy`) wraps the freshly decoded value
  and a `save` callback bound to that value's key. Every mutating method changes
  the underlying container, then calls `save`, which `encode`s the whole value
  and writes it to its key. JSON has no partial update, so **the unit of
  persistence is the key**, not the sub-object.
- **Child containers wrap lazily on access** and share the parent's `save`, so
  deep mutation persists: `stash.cfg["users"][0]["name"] = "b"` rewrites `cfg`.
- **Snapshots are point-in-time.** A separate read decodes a fresh copy; aliases
  from the *same* read share state, earlier reads are not retro-updated by later
  writes (last-write-wins, ADR-0001).
- **Proxies are unwrapped by the serializer** through a duck-typed
  `__stash_proxy__` marker, so assigning a proxy elsewhere stores its underlying
  value without a circular import between `_codecs` and `_proxies`.
- **`to_dict()` returns plain containers**, never proxies.

Reads that vivify (a missing namespace) are unaffected; only stored container
*values* are proxied.

## Consequences

### Positive

- The headline ergonomic works, including arbitrary nesting, and matches normal
  Python container semantics (`==`, iteration, `len`, `in`, slicing).
- No schema or serialization change; proxies are a thin read-time wrapper.
- Aliases obtained in one read stay consistent with each other.

### Negative

- Every mutation re-serializes the entire top-level value: O(size) per
  operation. Hot loops mutating one large value are slow; the planned
  `batch()` context (phase 4) will coalesce writes within a transaction.
- Snapshot semantics can surprise: a value captured before an external write is
  stale, and mutating it rewrites the whole key (last-write-wins).
- The proxy must mirror the container API; an unimplemented method would not
  persist. The mutator surface is covered by tests to prevent silent gaps.
- A stored `dict` value uses item access (`stash.cfg["k"]`), while a namespace
  uses attribute access (`stash.settings.k`). The distinction — cohesive blob
  vs independently-keyed section — is documented.

## Alternatives

- **Copy-on-read, require reassignment** (`shelve` without `writeback`) —
  rejected: reintroduces the silent-loss trap this project exists to fix.
- **Subclass `list`/`dict`/`set`** instead of composition — rejected: the
  subclass copies its data, breaking shared references needed for nested
  write-back, and complicates re-wrapping inserted containers.
- **Dirty-tracking / journaling sub-object writes** — rejected as premature;
  re-serializing the value is simpler and fast enough for local state.
