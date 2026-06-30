# ADR-0001: Storage schema, durability, and concurrency model

## Status

Accepted

## Context

Stash persists a Python namespace to local disk. We need a storage layout that
supports automatic persistence on assignment, future nested namespaces
(`stash.settings.theme`), human inspection of the data, and safe concurrent
access from threads and multiple processes — without turning into an ORM.

## Decision

**Single key/value table with dotted-path keys.**

```sql
CREATE TABLE stash (key TEXT PRIMARY KEY, value, codec TEXT NOT NULL)
```

- `key` is the full path. Phase 1 uses flat keys; nested namespaces will use
  `.` as a separator (`settings.theme`), so `.` is reserved in keys from day
  one. Namespaces become prefix scans (`WHERE key LIKE 'settings.%'`).
- `value` is declared with no type to keep SQLite's NONE affinity. We bind the
  JSON payload as a string, so it is stored with TEXT storage class and the
  database stays directly readable with the `sqlite3` CLI.
- `codec` names the top-level serialization (`"json"` today) so we can add
  alternative encodings later without a migration.

**Durability:** the connection runs in autocommit mode (`isolation_level=None`)
with `PRAGMA journal_mode=WAL` and `PRAGMA synchronous=NORMAL`. Each assignment
commits immediately, satisfying the "no explicit save" promise.

**Concurrency:** WAL allows many concurrent readers with a single writer. Reads
are read-through (every access queries SQLite) so processes observe each other's
writes without cache-invalidation logic; the conflict policy is last-write-wins.
A process-wide `threading.Lock` guards the shared connection
(`check_same_thread=False`) for thread safety.

## Consequences

### Positive

- One table; nesting, deletion, and namespace clears are simple key/prefix ops.
- Database is inspectable and debuggable with standard SQLite tooling.
- Autocommit + WAL gives durability and multi-reader concurrency for free.
- `codec` column leaves room for future encodings without schema migration.

### Negative

- `synchronous=NORMAL` can lose the most recent commit(s) on OS/power loss
  (not on process crash). Acceptable for local app state; revisit if Stash is
  ever used for data that must survive power failure.
- Read-through reads hit SQLite on every access. Fine for local files; a future
  `batch()` context will cache within a transaction for hot loops.
- A single locked connection serializes operations within a process. Adequate
  for the target use case (local app/script state), not high-throughput servers.

## Alternatives

- **Nested tables per namespace** — rejected: more complex, no real benefit over
  prefix scans for our access patterns.
- **`shelve` / `dbm`** — rejected: no concurrent access story, pickle-based,
  not inspectable.
- **One JSON file** — rejected: no atomic per-key writes, poor concurrency,
  rewrites the whole document on every change.
