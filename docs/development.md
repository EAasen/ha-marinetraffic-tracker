# Development Guide

This guide is for contributors who want to work on the Norwegian Maritime Tracker codebase.

---

## Prerequisites

- Python 3.12 or later
- `git`
- A GitHub account

---

## Getting Started

### 1. Fork and clone the repository

```bash
git clone https://github.com/<your-username>/ha-marinetraffic-tracker.git
cd ha-marinetraffic-tracker
```

### 2. Create a virtual environment

```bash
python -m venv venv
source venv/bin/activate   # Windows: venv\Scripts\activate
```

### 3. Install development dependencies

```bash
pip install pytest pytest-homeassistant-custom-component ruff
```

---

## Running Tests

```bash
pytest tests/ -v
```

Exit code 5 means no tests were collected for a given file — this is treated as success in CI.

---

## Linting and Type Checking

The project uses [Ruff](https://docs.astral.sh/ruff/) for linting and code formatting.

```bash
ruff check custom_components/ tests/
```

To auto-fix safe issues:

```bash
ruff check --fix custom_components/ tests/
```

### Ruff configuration

Ruff is configured in `pyproject.toml`.  The enabled rule sets are:

| Code | Rule set |
|---|---|
| `E` | pycodestyle errors |
| `F` | Pyflakes |
| `I` | isort import ordering |
| `UP` | pyupgrade |
| `S` | Bandit security checks |
| `B` | flake8-bugbear |
| `W` | pycodestyle warnings |

---

## Code Style

- Follow [PEP 8](https://peps.python.org/pep-0008/), enforced by Ruff.
- Maximum line length: **100 characters**.
- Use `from __future__ import annotations` at the top of every module.
- All public functions and classes **must** have docstrings.
- Use type annotations throughout.

---

## Pull Request Process

1. Create a new branch from `main`:
   ```bash
   git checkout -b feature/my-feature
   ```
2. Make your changes.  Ensure tests pass and Ruff reports no errors.
3. Write or update tests for any changed behaviour.
4. Commit using a descriptive message (see *Commit Message Conventions* below).
5. Push and open a pull request against `main`.
6. Wait for CI to pass; address any review comments.

---

## Commit Message Conventions

Use [Conventional Commits](https://www.conventionalcommits.org/) format:

```
<type>(<scope>): <short summary>
```

Common types:

| Type | When to use |
|---|---|
| `feat` | A new feature |
| `fix` | A bug fix |
| `docs` | Documentation changes only |
| `refactor` | Code change that is neither a feature nor a bug fix |
| `test` | Adding or updating tests |
| `chore` | Build or tooling changes |

Examples:

```
feat(coordinator): add position history pruning
fix(config_flow): handle missing HA latitude gracefully
docs: add troubleshooting section for credential errors
test(sensor): cover anchored vessel exclusion logic
```

---

## Testing Requirements

- New features **must** include unit tests.
- Bug fixes **should** include a regression test.
- All tests live in the `tests/` directory.
- Tests use `pytest` and `pytest-homeassistant-custom-component`.

---

## Adding a New Data Source

1. Create a new client module in `custom_components/marinetraffic_tracker/` following the pattern of `kystverket_client.py`.
2. The client must implement the same async interface expected by `coordinator.py`.
3. Add a constant for the new source in `const.py` and add it to `DATA_SOURCES`.
4. Update `coordinator.py` to instantiate the new client based on the `CONF_DATA_SOURCE` config value.
5. Add tests in `tests/`.

---

## CI Pipeline

The CI pipeline (GitHub Actions) runs three jobs on every push and pull request:

| Job | Tool | Scope |
|---|---|---|
| Ruff | `ruff check` | `custom_components/`, `tests/` |
| HASSfest | `home-assistant/actions/hassfest` | Validates manifest and integration structure |
| Pytest | `pytest` | `tests/` |

All three jobs must pass before a pull request can be merged.
