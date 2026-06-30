# ADR-0003: Nested namespaces and auto-vivification

## Status

Accepted

## Context

The product vision shows nested sections created by attribute assignment:

```python
stash.settings.theme = "dark"
stash.window.width = 1200
```

For `stash.settings.theme = "dark"` to create a brand-new `settings` section,
the read of `stash.settings` must return an object you can assign attributes to —
even when `settings` does not exist yet. Python evaluates the chain as
`getattr(stash, "settings").__setattr__("theme", "dark")`, so the intermediate
read happens before any write and cannot be distinguished from a plain read.

This conflicts with the phase-1 rule that a missing attribute raises
`AttributeError`. We cannot have all three of: (a) create sections by attribute
assignment, (b) raise on a mistyped attribute, and (c) precise `hasattr`.

## Decision

**Model paths as dotted keys; auto-vivify on attribute read; keep item access
strict.**

- Keys are dotted paths (`settings.theme`). A *namespace* is a path with
  descendants but no scalar; reading it returns a `Namespace` bound to that
  prefix. Both the root `Stash` and `Namespace` share one `_Node` base.
- **Attribute reads vivify**: `node.unknown` returns an empty `Namespace`
  instead of raising, enabling assignment chains. An empty namespace is falsy
  and persists nothing until assigned through.
- **Item reads are strict**: `node["unknown"]` raises `KeyError`, giving callers
  an existence-sensitive option. Dotted item keys address nested paths
  (`node["a.b"]` == `node.a.b`).
- **Delete follows the same split**: `del node.unknown` is a no-op (forgiving,
  matching vivifying reads), while `del node["unknown"]` raises `KeyError`. The
  rule across the API is: attribute access is forgiving, item access is strict.
- **`in` is the exact existence test**: `"settings" in node` is true only when a
  scalar or descendant exists. (`hasattr` is now always true and should not be
  used for existence.)
- A path is unambiguously a value *or* a namespace: assigning a scalar clears
  any subtree at that path, and assigning into a path clears any scalar sitting
  on an ancestor.

## Consequences

### Positive

- The headline ergonomic works: nested sections are created by assignment with
  no ceremony.
- One flat table still backs everything; namespaces are prefix scans, deletes
  are prefix deletes (ADR-0001).
- Callers retain a strict mode (item access, `in`).

### Negative

- A mistyped attribute read returns an empty namespace rather than raising, so
  typos are caught later (e.g. when reading a leaf) instead of immediately.
  Documented; `in`/item access mitigate.
- `stash.counter += 1` on a missing key raises `TypeError` (namespace + int)
  rather than `AttributeError`; the guidance is `setdefault("counter", 0)` first.
- Prefix scans use SQL `LIKE`, so `%`, `_`, and `\` in key segments must be
  escaped. Handled in the store; regression-tested.

## Alternatives

- **Raise on every missing read; require explicit namespace creation** (e.g.
  `stash.ns("settings")`) — rejected: breaks the vision's assignment syntax.
- **Marker rows for namespaces** — rejected: extra writes and bookkeeping for no
  user-visible benefit over prefix scans.
