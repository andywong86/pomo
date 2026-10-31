# Agent Instructions

## Project conventions

- Use conventional commits: https://www.conventionalcommits.org/en/v1.0.0/
- Keep changes small and focused.
- Prefer simple, readable Python over clever abstractions.
- Add or update tests when changing behavior.
- Do not commit generated files, caches, virtual environments, or build artifacts.

## Commands

Use `uv` for project commands:

```bash
uv run -- test
uv run -- typecheck
uv run -- lint
uv run -- format
uv run -- build
uv run -- clean
```

## Python style

- Use type hints for new functions.
- Prefer `pathlib.Path` for filesystem paths.
- Use `argparse` for command-line interfaces.
- Keep template files generic and reusable.
