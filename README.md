# objstash

> Use Python objects. Forget databases.

[![PyPI](https://img.shields.io/pypi/v/objstash)](https://pypi.org/project/objstash/)
[![Python](https://img.shields.io/pypi/pyversions/objstash)](https://pypi.org/project/objstash/)
[![License: MIT](https://img.shields.io/pypi/l/objstash)](LICENSE)

objstash is a persistent namespace backed by SQLite (the `Stash` class). Assign
values to attributes and they are transparently saved — no SQL, no schemas, no
explicit commit, no serialization boilerplate. Read them back in a later run of
your program.

```python
from objstash import Stash

stash = Stash("app.db")

stash.theme = "dark"
stash.setdefault("counter", 0)
stash.counter += 1
```

Run it again tomorrow and `stash.counter` keeps counting.

## Install

```bash
pip install objstash
```

Or with uv:

```bash
uv add objstash
```

Zero runtime dependencies — only the Python standard library. For the latest
unreleased `main`, install from GitHub:
`pip install git+https://github.com/JoeyMeijers/objstash.git`.

**Developing this repo**

```bash
git clone https://github.com/JoeyMeijers/objstash.git
cd objstash
uv sync          # creates the venv and installs dev dependencies
uv run pytest    # run the tests
```

## Usage

```python
from datetime import datetime
from objstash import Stash

stash = Stash("app.db")

# Scalars, lists, dicts, and many stdlib types persist on assignment.
stash.theme = "dark"
stash.recent = ["a", "b", "c"]
stash.last_login = datetime.now()

# Read it back (this process or a future one).
stash.theme            # "dark"

# Dict-like helpers.
stash.get("missing", default=0)     # 0
stash.setdefault("counter", 0)      # 0 (and stores it)
"theme" in stash                    # True
list(stash.keys())                  # ['last_login', 'recent', 'theme']

# Item access is the escape hatch for keys that aren't valid identifiers
# or that collide with a method name (get, keys, setdefault, to_dict, close).
stash["get"] = 5                    # stored under "get"; read via stash["get"]
```

### Nested namespaces

Assign through a dotted path and the section is created for you:

```python
stash.settings.theme = "dark"
stash.window.width = 1200
stash.window.height = 800

stash.window.width                  # 1200
stash.window.to_dict()              # {'width': 1200, 'height': 800}
stash.window == {"width": 1200, "height": 800}   # True

del stash.window                    # removes the whole subtree
```

Reading and existence semantics:

```python
# Attribute reads auto-vivify, so chains can create sections. A missing
# attribute returns an empty (falsy) namespace rather than raising:
bool(stash.does_not_exist)          # False

# Use `in` for an exact existence check (hasattr is always true here):
"settings" in stash                 # True only if a value/subtree exists

# Item access is strict and supports dotted paths:
stash["settings.theme"]             # "dark"  (same as stash.settings.theme)
stash["missing"]                    # raises KeyError
```

### Mutating containers persists automatically

Stored lists, dicts, and sets are mutated in place and saved — no reassignment,
unlike `shelve`:

```python
stash.tags = []
stash.tags.append("admin")          # persisted
stash.tags.sort()                   # persisted

stash.config = {"theme": "dark"}
stash.config["lang"] = "en"         # persisted

# Nesting works to any depth — the whole value is rewritten on change:
stash.cfg = {"users": [{"name": "a"}]}
stash.cfg["users"][0]["name"] = "b"
stash.cfg["users"].append({"name": "c"})
```

Proxies behave like the underlying container (`==`, iteration, `len`, `in`,
slicing). Two caveats: a stored **dict value** uses item access
(`stash.config["lang"]`) while a **namespace** uses attribute access
(`stash.settings.lang`); and each mutation rewrites the entire top-level value,
so very hot loops are better wrapped in `batch()` (below). Reads are
point-in-time snapshots — last write wins.

### Batching writes

Every assignment commits on its own. For bulk work, `batch()` groups writes into
a single atomic transaction — faster, and all-or-nothing:

```python
with stash.batch():
    for i in range(10_000):
        stash[f"item.{i}"] = i
# one commit; if the block raises, nothing in it is saved

with stash.batch():
    stash.account.balance -= 100
    stash.ledger.append({"delta": -100})   # both land together, or neither
```

Batches are reentrant (nested ones join the outer transaction). The connection
lock is held for the block, so concurrent writers wait — keep batches short.

### Deleting and clearing

```python
del stash.theme              # delete one value
del stash.settings.window    # delete a namespace and its whole subtree
del stash["settings.theme"]  # item access; dotted = nested path

stash.settings.clear()       # empty a namespace subtree
stash.clear()                # wipe the entire stash
```

Deleting follows the same forgiving/strict split as reading: `del stash.x` is a
no-op if `x` is absent, while `del stash["x"]` raises `KeyError`. Use item access
when you want a missing key to be an error.

### Supported value types

JSON-native types plus a registry of common stdlib types, round-tripped
losslessly (including tuples vs lists and non-string dict keys):

`None`, `bool`, `int`, `float`, `str`, `list`, `tuple`, `dict`, `set`,
`datetime`, `date`, `time`, `Decimal`, `UUID`, `bytes`.

Unknown types raise `UnsupportedTypeError`. Register your own:

```python
from objstash import register_type

register_type(MyType, "mytype", encode=lambda v: v.to_str(), decode=MyType.from_str)
```

A codec's encoded form may itself contain other registered types, so a value
with `datetime`, `Decimal`, or `set` fields round-trips without extra work.

### Storing your own classes

There is no automatic class persistence — by design. Reconstructing an arbitrary
class by name is exactly what makes `pickle` unsafe (it runs code on load) and
brittle (renaming the class breaks old data). Instead you register the class
explicitly, in one line, and stay in full control. There is no dependency on
`pydantic`; the snippet below only applies if you already use it.

**Dataclasses** (standard library):

```python
from dataclasses import dataclass, asdict
from objstash import register_type

@dataclass
class Point:
    x: int
    y: int

register_type(Point, "point", asdict, lambda d: Point(**d))

stash.origin = Point(1, 2)     # persists; reads back as a Point
```

**Pydantic** models:

```python
from pydantic import BaseModel
from objstash import register_type

class User(BaseModel):
    name: str
    age: int

register_type(User, "user", lambda u: u.model_dump(mode="json"), User.model_validate)

stash.user = User(name="Ada", age=36)
```

**Arbitrary objects, at your own risk.** If you need to store something with no
clean JSON form (a trained model, a closure, a complex object graph), you can
opt a specific type into `pickle` — the equivalent of R's `saveRDS` or a manual
`pickle.dump`:

```python
import base64
import pickle

from objstash import register_type

register_type(
    Model,
    "pickle:Model",
    lambda obj: base64.b64encode(pickle.dumps(obj)).decode("ascii"),
    lambda data: pickle.loads(base64.b64decode(data)),
)

stash.model = Model(...)        # now persists
```

This is opt-in and per type on purpose: that value becomes an opaque blob, so
for it you give up the things JSON buys you — it is no longer human-inspectable
or portable, it can break if the class changes, and `pickle.loads` will execute
code on read, so only ever load a database you trust. Prefer a JSON codec when
the type has any reasonable serial form; reach for `pickle` only when it does
not.

Register the type once at import time, before reading values of that type back.

By default Stash never uses `pickle`, so the database is safe to load and
human-inspectable (`sqlite3 app.db 'select * from stash'`) — that guarantee
holds for every type except ones you explicitly opt into `pickle` as above.

## Examples

Runnable scripts in [examples/](examples/):

- [resumable_job.py](examples/resumable_job.py) — a crash-safe job that resumes
  where it left off using a persisted set.
- [persistent_cache.py](examples/persistent_cache.py) — a memoization decorator
  whose cache survives restarts.
- [cli_state.py](examples/cli_state.py) — remembering state between runs
  (run counter, last-run time, recent files).

```bash
uv run python examples/resumable_job.py
```

## Status

Early (0.1, alpha). Implemented today: top-level keys, nested namespaces
(`stash.settings.theme`), transparent mutation persistence
(`stash.tags.append(...)`), atomic `batch()` writes, and the type registry — all
with automatic persistence. See [docs/adr/](docs/adr/) for design decisions.

## Concurrency & durability

The database runs in WAL mode with autocommit: every assignment is committed
immediately and is durable across process crashes. Multiple processes may share
a file (many readers, one writer, last-write-wins). See
[ADR-0001](docs/adr/ADR-0001-storage-schema.md) for details.

WAL keeps two sidecar files next to the database (`-wal`, `-shm`) while it is in
use — this is normal SQLite behaviour, not a leak. They are reused between runs
and your data always lives in the main file. `stash.checkpoint()` folds the WAL
back into the main file and shrinks it, which is handy before copying or shipping
the database.

## License

MIT
