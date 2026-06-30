# ADR-0005: Batch writes via explicit transactions

## Status

Accepted

## Context

By default every assignment autocommits (ADR-0001), which is convenient but has
two costs for bulk work:

- **Throughput** — a tight loop (`for i in range(10_000): stash[...] = i`, or many
  proxy mutations) pays a commit per write.
- **Atomicity** — a multi-write update that fails partway leaves the store in a
  half-written state.

We want an opt-in way to group writes into one atomic, single-commit unit
without abandoning the zero-ceremony default.

## Decision

**Add `stash.batch()`, a context manager that runs its block inside one explicit
SQLite transaction.**

- On entry it issues `BEGIN`; on clean exit `COMMIT`; on any exception
  `ROLLBACK`. All writes in the block — including mutation-proxy re-saves —
  land in that single transaction.
- **Reentrant**: nested `batch()` calls join the outer transaction via a depth
  counter; only the outermost commits, and an exception anywhere rolls the whole
  thing back.
- **Locking**: a transaction is global to the shared connection, so the
  connection lock is held for the batch's entire duration. The lock was changed
  from `Lock` to `RLock` so the batching thread can still call the per-operation
  methods (which re-acquire it) without deadlocking; other threads block until
  the batch finishes.

## Consequences

### Positive

- One commit per batch instead of one per write — materially faster for bulk
  loads and proxy-heavy loops.
- All-or-nothing semantics: a failed block leaves the store unchanged.
- Read-your-writes holds within the block (same connection).
- A separate connection/process does not observe the batch until it commits
  (regression-tested), preserving isolation.

### Negative

- The lock is held across user code inside the block, so other threads writing
  to the same `Stash` wait. This serializes concurrent batches (no lost
  updates) at the cost of parallelism — acceptable for local app state.
- A long-running or blocking operation inside `batch()` stalls other writers;
  callers should keep batches short.
- Proxy mutations still re-encode the whole value per change (ADR-0004); batch
  reduces commits, not re-encoding work.

## Alternatives

- **A connection (or thread-local connection) per thread** — would allow truly
  concurrent transactions but adds connection-pool complexity and cross-thread
  visibility questions; deferred until there is a server-style use case.
- **Autocommit-only, document manual SQL for bulk** — rejected: leaks the
  database abstraction the project is built to hide.
- **Savepoints for nested batches** — unnecessary; a depth counter gives the
  same all-or-nothing nesting semantics more simply.
