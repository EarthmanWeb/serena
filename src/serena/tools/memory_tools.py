import logging
import re
from typing import Literal

from serena.tools import Tool, ToolMarkerCanEdit

log = logging.getLogger(__name__)


class WriteMemoryTool(Tool, ToolMarkerCanEdit):
    """
    Write some information (utf-8-encoded) about this project that can be useful for future tasks to a memory in md format.
    The memory name should be meaningful.
    """

    def apply(self, memory_name: str, content: str, max_chars: int = -1) -> str:
        """
        Write information about this project that can be useful for future tasks in md format.
        The name should be meaningful and can include "/" to organize into topics.
        If explicitly instructed, use the "global/" prefix for writing a memory that is shared across projects.
        References to other memories should be inside backticks and prefixed with mem:,
        e.g., `mem:auth`.

        Begin the content with a YAML front-matter block so the memory is discoverable by
        `search_memories_by_front_matter`:

            ---
            name: <short title of this memory>
            description: <one sentence: what this memory is about / why you'd open it>
            metadata:
              type: <category, e.g. reference | feedback | project | feature | domain>
            ---

        Then the body. (A project may define a stricter front-matter convention; follow it if present.)

        :param memory_name: memory name
        :param content: memory content, utf8-encoded
        :param max_chars: see other tools
        """
        # NOTE: utf-8 encoding is configured in the MemoriesManager
        if max_chars == -1:
            max_chars = self.agent.serena_config.default_max_tool_answer_chars
        if len(content) > max_chars:
            raise ValueError(
                f"Content for {memory_name} is too long. Max length is {max_chars} characters. " + "Please make the content shorter."
            )

        return self.memory_manager.save_memory(memory_name, content, is_tool_context=True)


def _demote_leading_h1(content: str) -> str:
    """Demote a memory's leading top-level ``# `` heading to bold text.

    Claude Code disables structured tool output (see the claude-code context), so memory content is
    returned as raw markdown. Some clients (e.g. the VS Code extension) then render a leading H1 as an
    oversized title block. Demoting only the first top-level heading to ``**bold**`` keeps the title
    text and all deeper headings intact while avoiding that giant-lettering rendering. Front matter
    and the body are otherwise untouched.
    """
    lines = content.split("\n")
    idx = 0
    # Skip a leading YAML front-matter block, if present.
    if lines and lines[0].strip() == "---":
        for i in range(1, len(lines)):
            if lines[i].strip() == "---":
                idx = i + 1
                break
    # Advance to the first non-blank content line.
    while idx < len(lines) and lines[idx].strip() == "":
        idx += 1
    if idx < len(lines):
        m = re.match(r"# (?!#)(.*)$", lines[idx])
        if m:
            lines[idx] = f"**{m.group(1).strip()}**"
    return "\n".join(lines)


class ReadMemoryTool(Tool):
    """
    Reads the content of a memory file.
    """

    def apply(self, memory_name: str) -> str:
        """
        Use to read a memory that is likely to be relevant to the current task, inferring relevance e.g. from the name.
        """
        return _demote_leading_h1(self.memory_manager.load_memory(memory_name))


class ListMemoriesTool(Tool):
    """
    Lists available memories.
    """

    def apply(self, topic: str = "") -> str:
        """
        Lists available memories. The optional `topic` filters by directory prefix (the leading
        path segment of a memory name): e.g. topic="ref" lists every memory under `ref/`, and
        topic="global" lists global memories. `topic` matches a directory prefix, not a keyword
        anywhere in the name — to search by keyword use `search_memories_by_name`, and to search by
        what a memory is about use `search_memories_by_front_matter`.
        """
        return self._to_json(self.memory_manager.list_memories(topic).to_dict())


class SearchMemoriesByNameTool(Tool):
    """
    Finds memories whose name matches a keyword.
    """

    def apply(self, query: str, fuzzy: bool = True) -> str:
        """
        Finds memories whose NAME matches `query`, for when you know roughly what a memory is
        called but not its exact name or directory prefix. Matches `query` case-insensitively as a
        substring of the memory name (both the full `dir/NAME` form and the base `NAME`). When no
        substring matches and `fuzzy` is true, falls back to similarity ranking so a loose keyword
        still surfaces close names. Searches names only, not memory content.

        :param query: the keyword or partial name to search for
        :param fuzzy: whether to fall back to fuzzy similarity ranking when no substring matches
        :return: JSON with matching memory names (and read-only memory names)
        """
        return self._to_json(self.memory_manager.search_memories_by_name(query, fuzzy=fuzzy).to_dict())


class SearchMemoriesByFrontMatterTool(Tool):
    """
    Finds memories by searching their YAML front-matter.
    """

    def apply(self, query: str, max_answer_chars: int = -1) -> str:
        """
        Finds memories by what they are ABOUT, searching each memory's YAML front-matter
        (`name`, `description`, `metadata`) rather than its file name. Matches `query`
        case-insensitively against those fields. Memories that have no front-matter block are
        skipped (use `search_memories_by_name` to find those by name).

        :param query: the keyword to look for in the front matter
        :param max_answer_chars: if the output exceeds this many characters, a shortened summary is
            returned instead. Defaults to the configured tool-answer limit.
        :return: JSON list of matches, each `{memory, field, value, read_only}`
        """
        hits = self.memory_manager.search_memories_by_front_matter(query)
        result = self._to_json(hits)

        def _names_only() -> str:
            return self._to_json(sorted({h["memory"] for h in hits}))

        return self._limit_length(result, max_answer_chars, shortened_result_factories=[_names_only])


class DeleteMemoryTool(Tool, ToolMarkerCanEdit):
    """
    Delete a memory file.
    """

    def apply(self, memory_name: str) -> str:
        """
        Delete a memory, only call if instructed explicitly or permission was granted by the user.
        """
        return self.memory_manager.delete_memory(memory_name, is_tool_context=True)


class RenameMemoryTool(Tool, ToolMarkerCanEdit):
    """
    Renames or moves a memory, updating references that are marked with the `mem:` prefix.
    """

    def apply(self, old_name: str, new_name: str) -> str:
        """
        Rename or move a memory, use "/" in the name to organize into topics.
        The "global" topic should only be used if explicitly instructed.
        References to other memories that are marked with the `mem:` prefix will be updated accordingly.
        References in read-only memories are not affected.
        """
        renaming_message, n_references_updated = self.memory_manager.rename_memory_and_propagate_references(
            old_name, new_name, is_tool_context=True
        )
        if n_references_updated > 0:
            log.info(f"Updated {n_references_updated} references to memory {old_name} to {new_name}")
        return renaming_message


class EditMemoryTool(Tool, ToolMarkerCanEdit):
    """
    Replaces content matching a regular expression in a memory.
    """

    def apply(
        self,
        memory_name: str,
        needle: str,
        repl: str,
        mode: Literal["literal", "regex"],
        allow_multiple_occurrences: bool = False,
    ) -> str:
        r"""
        Replace content matching a regular expression in a memory.

        :param memory_name: the name of the memory
        :param needle: the string or regex pattern to search for. In regex mode, be careful to not replace too much!
            If `mode` is "literal", this string will be matched exactly.
            If `mode` is "regex", this string will be treated as a regular expression (syntax of Python's `re` module,
            with the MULTILINE and DOTALL flags enabled).
        :param repl: the replacement string (verbatim).
        :param mode: either "literal" or "regex", specifying how the `needle` parameter is to be interpreted.
        :param allow_multiple_occurrences: whether to allow matching and replacing multiple occurrences.
            If false and multiple occurrences are found, an error will be returned.
        """
        return self.memory_manager.edit_memory(
            memory_name, needle, repl, mode, allow_multiple_occurrences, is_tool_context=True, regex_multiline=True
        )
