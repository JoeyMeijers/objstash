# Changelog

All notable changes to this project are documented here. The format is based on
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and this project
adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

## [0.2.0] - 2026-06-28

First release published to PyPI, under the distribution name `objstash`
(`pip install objstash`, `from objstash import Stash`). The `stash` name was
already taken on PyPI; the import package is `objstash`, the class is still
`Stash`.

### Changed

- Renamed the import package from `stash` to `objstash`. The public class and
  API are unchanged: `from objstash import Stash`.
- Deleting a missing key via attribute access (`del stash.x`) is now a no-op
  instead of raising `AttributeError`, matching the forgiving behavior of
  attribute reads. Item access stays strict: `del stash["x"]` still raises
  `KeyError`. The rule is now consistent — attribute access is forgiving, item
  access is strict.

## [0.1.0] - 2026-06-28

Initial release.

### Added

- Persistent namespace backed by SQLite with attribute and item access
  (`stash.theme = "dark"`, `stash["theme"]`). Values persist automatically on
  assignment — no explicit save.
- Nested namespaces created on demand by assignment
  (`stash.settings.theme = "dark"`), with auto-vivifying attribute reads and
  strict item access. See [ADR-0003](docs/adr/ADR-0003-nested-namespaces.md).
- Transparent mutation persistence for stored `list`, `dict`, and `set` values
  (`stash.tags.append(...)`), including arbitrary nesting. See
  [ADR-0004](docs/adr/ADR-0004-mutation-proxies.md).
- JSON serialization with an extensible codec registry (`register_type`).
  Built-in lossless support for `datetime`, `date`, `time`, `Decimal`, `UUID`,
  `bytes`, plus tuples, sets, and non-string dict keys. No `pickle`, so the
  database is safe to load and human-inspectable. See
  [ADR-0002](docs/adr/ADR-0002-serialization-codecs.md).
- Atomic, reentrant `batch()` transactions that coalesce writes into a single
  commit and roll back on error. See
  [ADR-0005](docs/adr/ADR-0005-batch-transactions.md).
- `clear()` to wipe a stash or a namespace subtree, and `checkpoint()` to fold
  the write-ahead log into the database file.
- WAL-mode storage with autocommit for durable writes and concurrent
  many-reader/single-writer access. See
  [ADR-0001](docs/adr/ADR-0001-storage-schema.md).
- Fully type-hinted (`py.typed`), with zero runtime dependencies.

[Unreleased]: https://github.com/JoeyMeijers/objstash/compare/v0.2.0...HEAD
[0.2.0]: https://github.com/JoeyMeijers/objstash/compare/v0.1.0...v0.2.0
[0.1.0]: https://github.com/JoeyMeijers/objstash/releases/tag/v0.1.0
