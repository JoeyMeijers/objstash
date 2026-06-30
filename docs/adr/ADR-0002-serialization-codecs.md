# ADR-0002: Serialization via JSON and a codec registry

## Status

Accepted

## Context

Stash must "automatically serialize" values with zero user effort, while staying
safe, portable, and inspectable. The headline candidates:

- **pickle** — handles almost any object automatically, but executes arbitrary
  code on load (security risk), breaks across class/library versions, and
  produces opaque blobs. Conflicts with the repository security standards.
- **JSON** — safe and human-readable, but only covers a handful of types and,
  worse, *silently corrupts* some inputs: `json.dumps` turns tuples into lists
  and coerces non-string dict keys to strings.

## Decision

**JSON as the on-disk format, with a codec registry for non-native types, and no
pickle.**

- Values are converted by a recursive walk (not `json.dumps(default=...)`), so
  the round-trip is lossless and explicit. Tuples, sets, and dicts with
  non-string keys are preserved via tagged objects
  (`{"__stash__": <tag>, ...}`).
- A registry maps types to `(tag, encode, decode)`. Built-ins cover `datetime`,
  `date`, `time`, `Decimal`, `UUID`, and `bytes`. Users extend it with
  `register_type(...)`.
- A codec's encoded output is recursed back through the serializer, so it may
  contain other registered or structural types (e.g. a dataclass with a
  `datetime` field). Built-in codecs return primitives, for which this is a
  no-op. Decode mirrors this, reconstructing nested types before the codec runs.
- Unknown types raise `UnsupportedTypeError` instead of silently falling back to
  an unsafe encoding.
- The reserved tag key (`__stash__`) is escaped: a plain dict that happens to
  contain that key is encoded with the explicit `"map"` form so reads are
  unambiguous.

## Consequences

### Positive

- No arbitrary-code-execution risk on read; database is portable and
  human-inspectable.
- Lossless round-trips for the common Python types, including the cases stdlib
  JSON gets wrong (tuples, non-string keys).
- Extensible: applications register their own types without forking Stash.

### Negative

- Arbitrary objects (e.g. unregistered dataclasses, custom classes) are not
  stored automatically; users must register a codec. This is a deliberate
  safety/explicitness trade-off.
- The recursive transform is slower than a single `json.dumps`. Correctness is
  prioritized over micro-performance for local state.
- Circular references are rejected (raise `StashError`) rather than supported.

## Alternatives

- **pickle (default or fallback)** — rejected on security, portability, and
  version-fragility grounds.
- **`json.dumps(default=...)` only** — rejected: silently lossy for tuples and
  non-string dict keys.
- **Opt-in pickle codec** — deferred. Could be added later for power users who
  accept the trade-off, gated behind an explicit flag.

## Future work

- A `register_dataclass(cls)` convenience wrapper over `register_type`. Dataclass
  and pydantic models are already supported today via explicit `register_type`
  (see the README); this would only remove the one-line boilerplate.
- Optional opt-in pickle codec behind a per-stash flag.
