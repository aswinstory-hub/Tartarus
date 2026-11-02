# Development Setup

## Helix

The Helix configuration for the Phylax project is in
[`.helix/languages.toml`](../.helix/languages.toml).
For Python, it starts Pyright for language-server features and Ruff for linting;
Ruff formats files on save. Helix uses `pyright-langserver --stdio` and
`uv run --project . ruff server`, so `pyright-langserver` and `uv` must be
available on `PATH` when Helix starts. Ruff is included in the project's
development dependencies and starts through `uv run`, so it uses Phylax's locked
environment. Pyright requires Node.js and can be installed globally with
`npm install --global pyright` if it is not already available.

The formatter command reads the current buffer from standard input, passes its
filename to Ruff, and writes the formatted content back through standard
output. Configuration applies to Python files in the repository; it does not
change the project's command-line test or lint workflows.

## Project checks

From `Phylax/`, sync the project environment and start Helix in the project:

```powershell
uv sync --dev
hx .
```

Run the project checks from the same directory:

```powershell
uv run pytest
uv run ruff check .
```

See [Testing and project checks](testing.md) for additional guidance.
