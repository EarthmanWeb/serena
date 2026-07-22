<!--
MEMORY.md is an INDEX, not a content store. It loads into context every session,
so keep it lean — aim for < 200 lines.
  • One line per memory: `- [Title](path) — short hook` (≤ 200 chars).
  • The detail lives in the linked topic file, NOT here. Never paste a summary in.
  • Group entries under a few category headers — do NOT add a `##` section per memory.
  • Do NOT index spec/, report/, research/, or project/ memories — those are browsed
    with list_memories(topic="…"), never listed here.
The write_memory hook warns when these are violated; trim on the warning.
-->

## Response & Style
- [Response Format](feedback/FEEDBACK_RESPONSE_FORMAT.md) — no conversational language, use functional/direct phrasing only
- [Read docs = list memories](feedback/FEEDBACK_READ_DOCS_MEANS_LIST.md) — "read the docs" means check MEMORY.md and use Serena to list_memories, not external docs

## Architecture
- [Serena Project Core](arch/ARCH_CORE.md) — graph root: source map (`src/serena`, `src/solidlsp`, `src/interprompt`) + project-wide invariants

## Features
- [Dev Standards](feature/FEATURE_DEV_STANDARDS.md) — code style, ruff/ty config, poe commands, git branches
- [Test Suite](feature/FEATURE_TESTS.md) — runner commands, test gate, completion checklist, Gherkin specs
- [Custom Agents](feature/FEATURE_AGENTS.md) — custom-agents index (template stub, not yet customized)

## Reference
- [Memory Maintenance](ref/REF_MEMORY_MAINTENANCE.md) — how memories are created & maintained (discovery model, style, add/update threshold, maintenance actions)
- [Adding New Language Support](ref/REF_ADDING_LANGUAGE_SUPPORT.md) — language server class, registration, test repo/suite, docs to update
- [Creating Pull Requests](ref/REF_CREATING_PULL_REQUESTS.md) — PR scope rules (CONTRIBUTING.md) + CHANGELOG requirement

## Browser Session Isolation
- [MCP Browser DevTools](ref/REF_MCP_BROWSER_DEVTOOLS.md) — scenarios-first rule, storageState reuse for parallel agents, tool reference

## Workflow Routing

| Situation                  | Go To                                         |
| -------------------------- | --------------------------------------------- |
| Simple lookup ("find X")   | `WF_RESEARCH`                                 |
| Starting work (full)       | `WF_INIT`                                     |
| Researching                | `WF_RESEARCH`                                 |
| Making changes             | `WF_CLASSIFY`                                 |
| Continuing                 | `WF_CONTINUE`                                 |
| Verifying                  | `WF_VERIFY`                                   |

## Memory Types

| Prefix   | Purpose           |
| -------- | ----------------- |
| FEATURE_ | Feature configs   |
| DOM_     | Domain behaviors  |
| SYS_     | System references |
| REF_     | Reference docs    |
| INDEX_   | Navigation        |
| ARCH_    | Architecture      |
| SPEC_    | Specifications    |
| WF_      | Workflow states   |
| WM_      | Session state     |
