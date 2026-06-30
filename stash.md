# Project Prompt: Stash

## Overview

Stash is a Python library that provides a persistent namespace backed by SQLite.

The goal is to make persistent local storage feel like native Python objects instead of a database.

Users should never have to think about SQL, tables, schemas, commits, or serialization. They simply assign values to objects, and Stash transparently persists them.

> Use Python objects. Forget databases.

---

## Vision

Persisting local application state should be as simple as writing normal Python code.

Instead of:

```python
config["theme"] = "dark"
```

Users write:

```python
stash.theme = "dark"
stash.counter += 1
stash.last_login = datetime.now()
```

Everything is automatically persisted. No explicit save. No boilerplate.

---

## Goals

- Python-first API
- Zero configuration
- Works in any script
- SQLite internal storage
- Automatic serialization
- Nested namespaces
- Minimal learning curve

---

## Non-Goals

- Not an ORM
- Not a query builder
- Not a distributed database

Stash solves one thing:

> Persist local Python state effortlessly.

---

## Example Usage

```python
from stash import Stash

stash = Stash()

stash.counter += 1
stash.theme = "dark"
```

```python
stash.settings.theme = "dark"
stash.window.width = 1200
```

---

## Guiding Principle

> Persistent state should feel like normal Python objects. SQLite is an implementation detail.
