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
