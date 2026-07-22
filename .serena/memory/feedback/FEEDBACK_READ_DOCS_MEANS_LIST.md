---
name: Read docs means list memories
description: Interpret "read the docs" / "check the docs" as list-and-read Serena memories, not external docs.
metadata:
  type: feedback
---

# "Read the docs" = list Serena memories

When the user says "read the docs", "read docs", or "check the docs": call `mcp__plugin_swe_serena__list_memories()`, then read the memories relevant to the topic BEFORE proceeding.

**Why:** "Docs" = Serena memories in this project, NEVER external documentation or READMEs. Skipping this reads the wrong source.

**How to apply:** On every "read the docs" / "check the docs", call `list_memories` first, then read the applicable memories.
