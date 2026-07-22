---
name: Memory Maintenance
description: How memories are created & maintained — discovery model, style, add/update threshold, maintenance actions.
metadata:
  type: reference
---

# Memory Maintenance

## Discovery Model

- Build a graph of memories through progressive discovery via references.
- Agents start with the list of all memory names only.
- Read `mem:arch/ARCH_CORE` as the top-level entry point (graph root). It references memories covering major project domains; those reference more specific memories, and so on. Graph depth scales with project complexity.
- Group related memories with topics/folders to make structure explicit. Mirror project structure (e.g. frontend/backend modules) or topics (debugging, architecture).
- Write every memory reference as `mem:<name>` inside backticks, e.g. `mem:frontend/core`. Surrounding text MUST state when to read the memory and what content to expect — give more precise guidance than the memory name alone.
- Do NOT put "when to read me" guidance inside a memory. That belongs in the referring memory.

## Style

- Write dense agent notes, not prose docs. Prefer invariants and terse bullets.
- Omit obvious context, rationale, and examples UNLESS they prevent a likely mistake.
- Keep guidance durable and generalizable, NEVER task-local.

## Add/Update Threshold

- Add or update a memory ONLY for stable, non-obvious project conventions that avoid complex rediscovery later.
- Do NOT add: quick-read facts; generic language/framework knowledge; one-off task notes; volatile line-level details; behavior likely to change soon.

## Maintenance Actions

- Rename memories via Serena's memory rename tool — it updates `mem:` references automatically.
- After deleting/renaming, run `serena memories check` for a stale-reference report.
