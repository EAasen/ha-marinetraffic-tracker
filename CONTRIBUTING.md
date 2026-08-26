# Contributing

Thank you for considering contributing to `ha-marinetraffic-tracker`!

## Code Style

This project enforces consistent code style through automated tooling.

### Formatters

| Tool   | Purpose                         | Config                    |
|--------|---------------------------------|---------------------------|
| Ruff   | Linting + formatting (primary)  | `pyproject.toml`          |
| Black  | Python code formatting          | `pyproject.toml`          |
| isort  | Import statement sorting        | `pyproject.toml`          |

- **Line length**: 100 characters
- **Python version**: 3.12+
- Imports are sorted in the [Black-compatible isort profile](https://pycqa.github.io/isort/docs/configuration/profiles.html)

### Linters

| Tool    | Purpose                            | Config         |
|---------|------------------------------------|----------------|
| Ruff    | Fast linter (replaces flake8/isort)| `pyproject.toml` |
| flake8  | PEP 8 style guide enforcement      | `setup.cfg`    |
| pylint  | Code quality and complexity        | `.pylintrc`    |
| mypy    | Static type checking               | `pyproject.toml` |

### Type Hints

All production code in `custom_components/` must include type hints.  The mypy
configuration enforces `disallow_untyped_defs = true` for the main package.

## Pre-commit Hooks

Install pre-commit to run checks automatically before every commit:

```bash
pip install pre-commit
pre-commit install
```

After installation, linters and formatters run automatically on `git commit`.
To run all hooks manually against all files:

```bash
pre-commit run --all-files
```

## Running Checks Locally

```bash
# Fast linting + formatting (primary check — matches CI)
pip install ruff
ruff check custom_components/ tests/
ruff format --check custom_components/ tests/

# Type checking
pip install mypy aiohttp voluptuous
mypy custom_components/ --ignore-missing-imports

# Pylint
pip install pylint aiohttp voluptuous
pylint custom_components/

# flake8
pip install flake8
flake8 custom_components/ tests/

# Black (formatting only)
pip install black
black --check custom_components/ tests/

# isort (import sorting only)
pip install isort
isort --check-only custom_components/ tests/
```

## Running Tests

```bash
pip install pytest pytest-homeassistant-custom-component
pytest tests/ -v
```

## CI/CD

Every pull request runs the following checks automatically:

- **Ruff** — linting and import sorting (fast, primary gate)
- **Mypy** — static type checking
- **Pylint** — code quality and complexity (minimum score: 8.0/10)
- **HASSfest** — Home Assistant integration validation
- **Pytest** — unit tests

All checks must pass before a PR can be merged.

## Commit Messages

Use short, imperative present-tense commit messages, e.g.:
- `Add Kystverket fallback client`
- `Fix stale vessel purge off-by-one`
- `Update mypy configuration`
