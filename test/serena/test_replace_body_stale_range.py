"""
Regression tests for the stale-range guard in ``CodeEditor.replace_body``.

A language server can report a symbol range computed against an in-memory view that diverges
from the file on disk (e.g. an out-of-band edit that sends no ``didChange``). Replacing at such
coordinates lands mid-signature and corrupts the source. ``replace_body`` verifies the resolved
symbol's identifier lies within the span it is about to replace and fails fast otherwise.

These tests exercise the guard without a running language server by driving ``replace_body``
through in-memory fakes for the symbol and the edited file.
"""

from collections.abc import Iterator
from contextlib import contextmanager

import pytest

from serena.code_editor import CodeEditor
from serena.symbol import PositionInFile


class _FakeSymbol:
    """Minimal stand-in exposing the interface ``replace_body`` consumes."""

    def __init__(self, name: str, start: PositionInFile, end: PositionInFile) -> None:
        self.name = name
        self._start = start
        self._end = end

    def get_body_start_position_or_raise(self) -> PositionInFile:
        return self._start

    def get_body_end_position_or_raise(self) -> PositionInFile:
        return self._end


class _FakeEditedFile(CodeEditor.EditedFile):
    """In-memory edited file that applies deletes/inserts to a string buffer."""

    def __init__(self, relative_path: str, contents: str) -> None:
        super().__init__(relative_path)
        self._contents = contents

    def get_contents(self) -> str:
        return self._contents

    def set_contents(self, contents: str) -> None:
        self._contents = contents

    def _offset(self, pos: PositionInFile) -> int:
        lines = self._contents.split("\n")
        return sum(len(line) + 1 for line in lines[: pos.line]) + pos.col

    def delete_text_between_positions(self, start_pos: PositionInFile, end_pos: PositionInFile) -> None:
        start, end = self._offset(start_pos), self._offset(end_pos)
        self._contents = self._contents[:start] + self._contents[end:]

    def insert_text_at_position(self, pos: PositionInFile, text: str) -> None:
        at = self._offset(pos)
        self._contents = self._contents[:at] + text + self._contents[at:]


class _FakeCodeEditor(CodeEditor):
    """Concrete CodeEditor whose file/symbol resolution is fully in-memory (no language server)."""

    def __init__(self, symbol: _FakeSymbol, edited_file: _FakeEditedFile) -> None:
        # deliberately skip super().__init__ — no Project/encoding/newline needed for these paths
        self._symbol = symbol
        self._edited_file = edited_file

    def _find_unique_symbol(self, name_path: str, relative_file_path: str):
        return self._symbol

    @contextmanager
    def _open_file_context(self, relative_path: str) -> Iterator[CodeEditor.EditedFile]:
        yield self._edited_file

    def edited_file_context(self, relative_path: str) -> Iterator[CodeEditor.EditedFile]:  # type: ignore[override]
        return self._open_file_context(relative_path)

    def rename_symbol(self, name_path: str, relative_path: str, new_name: str) -> str:
        raise NotImplementedError


PHP_METHOD = (
    "class Board {\n  /**\n   * Old doc.\n   */\n  private static function crm_global_population_ids() {\n    return array();\n  }\n}\n"
)


def _lines(text: str) -> list[str]:
    return text.split("\n")


class TestExtractTextBetweenPositions:
    def test_single_line_span(self) -> None:
        contents = "alpha beta gamma"
        start = PositionInFile(line=0, col=6)
        end = PositionInFile(line=0, col=10)
        assert CodeEditor._extract_text_between_positions(contents, start, end) == "beta"

    def test_multi_line_span(self) -> None:
        # span covering the method body incl. its leading docblock
        start = PositionInFile(line=1, col=2)  # start of "/**"
        end = PositionInFile(line=6, col=3)  # just past the closing "  }"
        span = CodeEditor._extract_text_between_positions(PHP_METHOD, start, end)
        assert span.startswith("/**")
        assert "crm_global_population_ids" in span
        assert span.endswith("}")


class TestReplaceBodyStaleRangeGuard:
    def test_raises_when_identifier_not_in_span(self) -> None:
        # Simulate a stale range: the reported span points to the docblock only (lines 1-3),
        # which does NOT contain the identifier — the classic mid-signature-corruption vector.
        stale_start = PositionInFile(line=1, col=2)
        stale_end = PositionInFile(line=3, col=5)
        symbol = _FakeSymbol("crm_global_population_ids", stale_start, stale_end)
        edited = _FakeEditedFile("class-board.php", PHP_METHOD)
        editor = _FakeCodeEditor(symbol, edited)

        with pytest.raises(ValueError, match="resolved symbol range does not match"):
            editor.replace_body("Board/crm_global_population_ids", "class-board.php", "/** new */\n  x")

        # file left untouched
        assert edited.get_contents() == PHP_METHOD

    def test_applies_when_range_is_valid_incl_docblock(self) -> None:
        # A correct range spans the docblock through the closing brace and contains the identifier.
        start = PositionInFile(line=1, col=2)
        lines = _lines(PHP_METHOD)
        end_line = lines.index("  }")
        end = PositionInFile(line=end_line, col=len("  }"))
        symbol = _FakeSymbol("crm_global_population_ids", start, end)
        edited = _FakeEditedFile("class-board.php", PHP_METHOD)
        editor = _FakeCodeEditor(symbol, edited)

        new_body = "/**\n   * New doc.\n   */\n  private static function crm_global_population_ids(): array {\n    return [];\n  }"
        editor.replace_body("Board/crm_global_population_ids", "class-board.php", new_body)

        result = edited.get_contents()
        # exactly one signature, no duplication, no mangling
        assert result.count("private static function crm_global_population_ids") == 1
        assert "private static function /**" not in result
        assert "New doc." in result
        assert "Old doc." not in result
