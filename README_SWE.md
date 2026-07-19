# Serena — SWE Fork

This is a fork of [Serena](https://github.com/oraios/serena) maintained for the Convenely / SWE
workflow engine. It tracks the original project and adds a set of improvements on top. This document
explains, in plain terms, what the fork adds and why each change helps.

Everything here is additive: the fork stays in sync with upstream Serena and layers these
enhancements on top.

---

## Finding memories

Serena lets an assistant store and recall notes ("memories") about a project. Upstream can list
memories by folder and read one by its exact name — but there was no way to *search* for a memory
when you only remember roughly what it was about. In practice the assistant would come up empty and
fall back to scanning the whole codebase, often missing notes that actually existed.

The fork adds two ways to find a memory:

- **Search by name** — look up a memory using a keyword from its title, even a partial or slightly
  misspelled one. Asking for "security" now finds the "Security Scanner" note instead of returning
  nothing.
- **Search by description** — look up a memory by what it's *about*, using the short summary stored
  at the top of each note, rather than its file name.

Together these make stored knowledge reliably findable, so the assistant reaches for existing notes
instead of re-deriving things or searching blindly.

## Better-organized, shareable memories

- **Multiple memory locations** — a project can pull in memories from more than one folder, not just
  its own. This lets several projects share a common set of notes.
- **Read-only memories** — a shared folder can be marked read-only, so it can be read but never
  accidentally changed by one project.
- **Tidier updates** — editing an existing memory updates it in place rather than creating
  duplicates.

## Works better inside real projects

Upstream Serena would sometimes ignore or mishandle folders that begin with a dot (like the hidden
`.serena` project folder), which caused it to overlook relevant code and notes. The fork:

- Correctly includes dotted folders when appropriate, so nothing important is skipped.
- Fixes a crash that happened when a project contained a broken shortcut (symlink) to a file that no
  longer exists — Serena now skips it gracefully instead of falling over.

## More reliable code understanding

Serena reads code through "language servers" — helper programs that understand each programming
language. The fork makes this sturdier:

- **One bad language doesn't break the rest** — if the helper for one language fails to start,
  Serena keeps working for every other language instead of failing entirely.
- **PHP** — fixes cases where classes and methods weren't being found correctly.
- **Ruby** — fixes the Ruby helper so it starts reliably regardless of the project's own Ruby setup.
- **Markdown** — fixes how document headings are recognized, so navigating notes and docs works as
  expected.

## Easier troubleshooting

- **Show tool inputs and outputs** — an optional setting that makes Serena include exactly what was
  asked and what came back in each step, so it's much easier to see why something went wrong.

---

## In short

The fork keeps Serena current with the upstream project and adds: searchable memories, shareable and
read-only memory folders, correct handling of hidden project folders, more resilient code
understanding across languages, and clearer troubleshooting. The goal throughout is to make the
assistant find what it already knows, understand code without breaking on edge cases, and stay
dependable inside real, messy projects.

---

## Using the configurable additions

This section is for whoever sets up or operates Serena. Settings live in three places:

- **Command-line flags** — passed when the MCP server is started.
- **Project config** — `.serena/project.yml` in the project.
- **Global config** — `serena_config.yml` in the Serena home folder (`~/.serena`).

### Running it directly (without the SWE plugin)

The SWE plugin launches this fork for you, but you can also run it on its own from any MCP client.
The key detail is to install from **this fork on the `swe` branch** — `EarthmanWeb/serena`, not the
upstream `oraios/serena` — so you get the additions described above:

```
uvx --from "git+https://github.com/EarthmanWeb/serena@swe" \
  serena start-mcp-server \
  --context claude-code \
  --project ./ \
  --memory-path "./.serena/memories,/shared/team-memories:ro"
```

`uvx` fetches and runs the fork in one step; `serena start-mcp-server` is the command that speaks the
MCP protocol to your client. The example above also turns on two of the fork's memory features —
multiple memory folders and a read-only shared folder — via `--memory-path`.

To wire it into an MCP client's config instead of running by hand, use the same command as the
server's launch command:

```json
{
  "mcpServers": {
    "serena": {
      "command": "uvx",
      "args": [
        "--from", "git+https://github.com/EarthmanWeb/serena@swe",
        "serena", "start-mcp-server",
        "--context", "claude-code",
        "--project", "./",
        "--memory-path", "./.serena/memories,/shared/team-memories:ro"
      ]
    }
  }
}
```

Once running, the `search_memories_by_name` and `search_memories_by_front_matter` tools appear
automatically alongside Serena's standard tools — no extra setup.

### Memory search (the two new tools)

Nothing to configure — the tools are always available to the assistant:

- **`search_memories_by_name`** — give it a keyword; it matches memory titles and, if nothing matches
  exactly, falls back to close/fuzzy matches. Turn the fuzzy fallback off with `fuzzy=false` when you
  want exact-substring results only.
- **`search_memories_by_front_matter`** — give it a keyword; it matches the summary block at the top
  of each memory. Only memories that have such a block are searched, so keeping that block filled in
  (see below) is what makes this tool useful.

For the front-matter search to find things, memories should begin with a short block like:

```
---
name: <short title>
description: <one sentence about what this note is for>
metadata:
  type: <category>
---
```

New memories are prompted to include this automatically; existing ones can be backfilled in bulk.

### Multiple and read-only memory folders

Set these with the **`--memory-path`** flag when launching the server. Give it a comma-separated list
of folders:

- The **first** folder is the primary one — new memories and edits are written there.
- **Additional** folders are extra sources that are also searched and read.
- Add **`:ro`** to any extra folder to make it read-only (read but never written).

```
--memory-path "./.serena/memories,/shared/team-memories:ro"
```

This is how you share a common knowledge base across projects while protecting it from accidental
edits. Paths can be absolute or relative to the project root.

You can also mark specific memories (not whole folders) as read-only or hidden from within
`.serena/project.yml`, using regular-expression patterns:

- **`read_only_memory_patterns`** — memories matching these can be read but not changed.
- **`ignored_memory_patterns`** — memories matching these are hidden from listing/search entirely.

### Hidden (dot) folders

By default Serena skips folders whose names start with a dot. If your project keeps real code in such
a folder (for example `.github` workflows), set this in `.serena/project.yml`:

```
ignore_all_dot_files: false
```

With it off, dotted folders are indexed like any other. (`.git` is always skipped regardless.)

### Troubleshooting: see tool inputs and outputs

To diagnose why a step behaved unexpectedly, enable this in the global `serena_config.yml`:

```
debug_tool_calls: true
```

Each tool response then includes exactly what was passed in and what came back — invaluable when a
symbol lookup or edit doesn't do what you expected. Leave it off in normal use, as it makes responses
longer.
