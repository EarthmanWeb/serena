---
name: FEATURE_TESTS
description: Test suite — runner commands, test gate, completion checklist, Gherkin specs, scope.
metadata:
  type: feature
---

# FEATURE_TESTS — Test Suite

## Feature Overview

| Property      | Value                  |
| ------------- | ---------------------- |
| **Name**      | Test Suite             |
| **Key**       | TESTS                  |
| **Type**      | infrastructure         |
| **Language**  | python   |
| **Framework** | pytest     |

## Running Tests

ALWAYS use project scripts. Run all commands from the project root.

```bash
# Full suite (unmarked tests + PYTEST_MARKERS selection)
uv run poe test
# Single file
uv run pytest test/path/to/test_x.py -vv
# Language-gated language-server tests (one marker per language)
uv run pytest -m python        # or -m typescript, -m csharp, etc.
```

- Per-language language-server tests are pytest-marker-gated (markers declared in `pyproject.toml` `[tool.pytest.ini_options].markers`).
- Snapshot tests use **syrupy** with the custom `--snapshot-patch-pycharm-diff` plugin (auto-added via `addopts`).
- Test infra: `test/conftest.py` provides shared fixtures (`create_ls()`, the parametrized `language_server` fixture).

### Test Gate

The test gate hook (`swe_pre_bash_test_gate.py`) BLOCKS direct test-runner commands until this memory has been read in the current session.

Mechanism:

1. `swe_pre_bash_test_gate.py` intercepts Bash commands matching test patterns.
2. Checks for sentinel file `.serena/streams/.test_feature_{session_id}`.
3. If missing → BLOCKS with instruction to read FEATURE_TESTS.
4. On read of FEATURE_TESTS, `swe_post_read_state.py` calls `create_feature_sentinel(session_id, 'test')`, creating the sentinel.
5. Subsequent test commands pass instantly (file-existence check).

## Task Completion Checklist

After any code change in `src/` or `test/`, run in order:

1. `uv run poe format` — applies ruff fixes + formatting (mutates files).
2. `uv run poe type-check` — ty on `src/serena`, `src/solidlsp`, `test/`.
3. `uv run poe test` — pytest on affected files or affected languages, using `-m` markers.

- If prompt templates changed: `uv run python scripts/gen_prompt_factory.py` (regenerates `src/serena/generated/generated_prompt_factory.py`; then `uv run poe format` and commit the result).
- If memories were edited/renamed/split: run `uv run serena memories check` from the project root to find broken `mem:` references.

## Gherkin BDD Specs

Gherkin `.feature` files define testable behavioral specifications using Given/When/Then syntax.

| Property | Value |
| -------- | ----- |
| **Specs Directory** | `tests/specs/` |
| **File Pattern** | `[feature-key]-[slug].feature` |
| **Spec Authoring** | `/swe-gherkin-spec [KEY]` |
| **TDD from Spec** | `/swe-gherkin-dev [slug]` |

### Workflow Integration

- New features: Gherkin specs are prompted during `/swe-feature-onboard` and enforced at `WF_ARCH_REVIEW`.
- Feature additions: `WF_VERIFY` checks whether existing specs need new scenarios for changed behavior.
- Spec memories: each spec creates a `SPEC_[KEY]_[SLUG]` memory tracking coverage status.

### Convention

- One `.feature` file per logical feature area.
- Scenarios cover happy path, error cases, edge cases, and state transitions.
- Each Given/When/Then step maps 1:1 to a test assertion.
- NEVER use `test.fixme()` or `test.skip()` — 100% coverage required.

## Scope Definition

### Primary Directories

| Directory           | Purpose                        |
| ------------------- | ------------------------------ |
| `test/`    | Root of the test suite         |
| `test/solidlsp/` | Per-language language-server tests |
| `test/serena/` | Serena agent/framework tests |
| `test/resources/repos/` | Minimal per-language test repos |
| `tests/specs/` | Gherkin BDD specification files |

## Test Runner Config

| Setting      | Value                  |
| ------------ | ---------------------- |
| **Framework**| `pytest`   |
| **Root**     | `test/`        |
| **Plugins**  | pytest-xdist, pytest-timeout, syrupy |

## Test Suites

| Suite   | File   | Focus   |
| ------- | ------ | ------- |
| Language servers | `test/solidlsp/<lang>/` | Per-language LSP behavior (marker-gated) |
| Serena agent | `test/serena/` | Agent framework, tools, config |
