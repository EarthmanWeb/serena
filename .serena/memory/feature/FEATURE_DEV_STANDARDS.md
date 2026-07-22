---
name: FEATURE_DEV_STANDARDS
description: Development standards index — code style, lint/typing config, commands, git for the serena project.
metadata:
  type: feature
---

# FEATURE_DEV_STANDARDS — Development Standards Index

## Project: serena

- **Primary Language:** python (also typescript for LSP integration tests)

## Project Overview

Serena is a multi-language code assistant with three main components:

1. **Serena Core** (`src/serena/`) — agent framework: tools, MCP server, config, CLI. Entry point `agent.py` (`SerenaAgent` orchestrates everything); `mcp.py` is the MCP server; `cli.py` the CLI (`serena.cli:top_level`).
2. **SolidLSP** (`src/solidlsp/`) — unified Language Server Protocol wrapper; `ls.py` holds `SolidLanguageServer`, one impl per language under `language_servers/`.
3. **Interprompt** (`src/interprompt/`) — Jinja2-based multi-language prompt template system with language fallbacks.

Layout:
- Tests under `test/` (`test/serena/`, `test/solidlsp/`, `test/resources/repos/<lang>/test_repo/`).
- Scripts under `scripts/`; static config/resources under `resources/`.
- Build backend `hatchling` with packages `src/serena`, `src/interprompt`, `src/solidlsp`.

**Tool descriptions (LLM-facing):** to change how a tool is described to the model, edit the Tool class's `apply()` **docstring** in `src/serena/tools/*.py`. `make_mcp_tool` parses the docstring body + `:param:` lines into the MCP tool description/schema. Do NOT use `tool_description_overrides` in context ymls — the docstring is the single source of truth.

## Standards by Language

<!-- Add DEV_* memories for each language used in the project -->

| Language               | Memory          | Status      |
| ---------------------- | --------------- | ----------- |
| python   | `DEV_PYTHON` | TODO: Create |
| typescript | `DEV_TYPESCRIPT` | TODO: Create |

## General Standards

### Code Style (project-instructed)

- Use idiomatic, object-oriented design. Give non-trivial interfaces **explicitly typed abstractions** (strategy pattern etc.), NOT bare functions/callbacks.
- Avoid low-level data structures where an OO abstraction fits. For simple data containers use **dataclasses**, NOT dicts/tuples.
- Structure function bodies into **functional blocks separated by blank lines**, each prefixed with a short elliptical phrase (lowercase, no leading capital) describing the block's purpose.
- Write **docstrings in reStructuredText.** Use `:param x:`, `:return:`, `:raises X:`.
- Begin each parameter/method/class description with a precise elliptical phrase defining *what* the thing is; add detail in later sentences.

### Python formatting / lint (ruff)

- Line length 140, double quotes, target `py311`.
- Check `[tool.ruff.lint] ignore` in `pyproject.toml` before adding workarounds — many "annoying" rules are disabled (`Optional[T]` preferred over `T | None`, `Union` allowed, relative imports forbidden, `%` string formatting allowed).
- `ruff format` and `ruff check` both run on `src scripts test`. mccabe complexity cap: 20.

### Typing (ty)

- Type checker is **ty** (Astral), configured under `[tool.ty]` in `pyproject.toml` (replaced mypy). Test pass relaxes pytest/mock-noisy rules via `[[tool.ty.overrides]]`.

### File Organization

- Put new files in the existing directory structure (per-language subdirs under `src/solidlsp/language_servers/`, one test dir per language under `test/solidlsp/`).
- Group related functionality; keep each file to a single responsibility.

### Error Handling

- Fail fast with clear error messages. NO silent failures, NO empty catch blocks. Log errors at appropriate severity levels.

### Testing

- See `mem:feature/FEATURE_TESTS` for test runner and patterns.
- Language-server tests are pytest-marker-gated (one marker per language; see `pyproject.toml` `[tool.pytest.ini_options].markers`). Default `poe test` runs unmarked tests + whatever `PYTEST_MARKERS` selects.
- Snapshot tests use **syrupy** with a custom `--snapshot-patch-pycharm-diff` plugin (auto-added via `addopts`).

## Commands

Run via `uv run poe <task>` (or `poe <task>` inside the activated venv). Poe executor is `simple`, so plain `poe` works without uv re-resolving.

### Dev loop

- `poe test` — pytest on `test/` (per-language tests marker-gated; pass `-m <marker>` to enable).
- `poe lint` — ruff format-check + ruff check (no fixes).
- `poe format` — ruff `--fix` then `ruff format` (mutates files).
- `poe type-check` — ty on `src/serena`, `src/solidlsp`, and `test/`.
- Single test file: `uv run pytest test/path/to/test_x.py -vv`. Language-gated: add `-m python` etc.

### Docs

- `poe doc-build` — clean + autogen + sphinx (uses `rm -rf`; needs a unix-like shell).

### Entrypoints

- `uv run serena ...` — main CLI (`serena.cli:top_level`).
- `uv run serena-hooks ...` — hook helpers.
- `python scripts/gen_prompt_factory.py` — regenerate `src/serena/generated/generated_prompt_factory.py` after editing prompt templates.

### Package / dep management

- Package/dep manager: **uv** (`uv.lock` present). Exact version pins in `pyproject.toml` because `uvx` installs from git and ignores the lockfile.
- Task runner: **poethepoet** (`poe <task>`), executor `simple` (does NOT shell out via uv — avoids env recreation while MCP server runs).

### Windows notes (PowerShell 7+ is the project shell)

- Use `Remove-Item -Recurse -Force <path>` instead of `rm -rf`. Env vars: `$env:NAME = 'value'`.
- `git`, `uv`, `poe`, `pytest` behave identically to unix.

### Git

- Main branch: `main`. Current fork work branch: `swe`. Read `mem:ref/REF_CREATING_PULL_REQUESTS` when participating in PR creation.

## Per-Project Customization

1. Create `DEV_*` memories for each language (e.g. `DEV_PYTHON`, `DEV_TYPESCRIPT`).
2. Add project-specific standards (naming conventions, file headers, etc.).
3. Document CI/CD requirements (lint checks, coverage thresholds).
