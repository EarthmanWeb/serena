"""Regression tests for the PHP modifier-duplication guard in ``CodeEditor.replace_body``.

A PHP language server reports a method's ``location.range`` starting at the ``function``
keyword or the symbol name — the leading ``public``/``static``/``final``/``abstract``
modifiers fall OUTSIDE the range. When a caller re-supplies the full declaration it sees in
the file, the replacement is spliced in front of the still-present modifiers, producing
``public static function public static function name(...)`` — a parse fatal that the tool
would otherwise report as ``OK``.

``replace_body`` (Fix C) detects a newly-introduced duplicated-modifier run, rolls the file
back, and raises instead of returning success. These tests drive it through in-memory fakes
(no running language server), mirroring ``test_replace_body_stale_range.py``.
"""

from collections.abc import Iterator
from contextlib import contextmanager

import pytest

from serena.code_editor import CodeEditor
from serena.symbol import PositionInFile


class _FakeSymbol:
    def __init__(self, name: str, start: PositionInFile, end: PositionInFile) -> None:
        self.name = name
        self._start = start
        self._end = end

    def get_body_start_position_or_raise(self) -> PositionInFile:
        return self._start

    def get_body_end_position_or_raise(self) -> PositionInFile:
        return self._end


class _FakeEditedFile(CodeEditor.EditedFile):
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
    def __init__(self, symbol: _FakeSymbol, edited_file: _FakeEditedFile) -> None:
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


# A file whose method range (as an OLD, modifier-excluding LS would report it) starts at the
# "function" keyword — the modifiers "public static" precede the range.
PHP_MODIFIER_METHOD = "class Foo {\n  public static function bar(): void {\n    return;\n  }\n}\n"


def _positions_at_function_keyword(text: str, decl_line_substr: str) -> tuple[PositionInFile, PositionInFile]:
    lines = text.split("\n")
    decl_idx = next(i for i, ln in enumerate(lines) if decl_line_substr in ln)
    start = PositionInFile(line=decl_idx, col=lines[decl_idx].index("function"))
    close_idx = next(i for i in range(decl_idx, len(lines)) if lines[i] == "  }")
    end = PositionInFile(line=close_idx, col=len("  }"))
    return start, end


class TestReplaceBodyModifierDupGuard:
    def test_raises_and_rolls_back_on_modifier_dup(self) -> None:
        # Range starts at "function" (modifiers excluded). Caller re-supplies the full
        # declaration → would produce "public static function public static function bar".
        start, end = _positions_at_function_keyword(PHP_MODIFIER_METHOD, "function bar")
        symbol = _FakeSymbol("bar", start, end)
        edited = _FakeEditedFile("class-foo.php", PHP_MODIFIER_METHOD)
        editor = _FakeCodeEditor(symbol, edited)

        with pytest.raises(ValueError, match="duplicated"):
            editor.replace_body(
                "Foo/bar",
                "class-foo.php",
                "public static function bar(): void {\n    return;\n  }",
            )

        # File left byte-identical — no silent corruption.
        assert edited.get_contents() == PHP_MODIFIER_METHOD

    def test_valid_modifier_inclusive_range_round_trips(self) -> None:
        # With a modifier-INCLUSIVE range (start at "public"), re-supplying the declaration is
        # correct and must NOT trip the guard.
        lines = PHP_MODIFIER_METHOD.split("\n")
        decl_idx = next(i for i, ln in enumerate(lines) if "function bar" in ln)
        start = PositionInFile(line=decl_idx, col=lines[decl_idx].index("public"))
        end = PositionInFile(line=lines.index("  }"), col=len("  }"))
        symbol = _FakeSymbol("bar", start, end)
        edited = _FakeEditedFile("class-foo.php", PHP_MODIFIER_METHOD)
        editor = _FakeCodeEditor(symbol, edited)

        editor.replace_body(
            "Foo/bar",
            "class-foo.php",
            "public static function bar(): int {\n    return 1;\n  }",
        )

        result = edited.get_contents()
        assert result.count("public static function bar") == 1
        assert "public static function public static function" not in result
        assert "): int {" in result

    def test_body_without_modifiers_does_not_trip_guard(self) -> None:
        # The documented workaround: supply the body WITHOUT re-declaring modifiers.
        start, end = _positions_at_function_keyword(PHP_MODIFIER_METHOD, "function bar")
        symbol = _FakeSymbol("bar", start, end)
        edited = _FakeEditedFile("class-foo.php", PHP_MODIFIER_METHOD)
        editor = _FakeCodeEditor(symbol, edited)

        editor.replace_body("Foo/bar", "class-foo.php", "function bar(): int {\n    return 1;\n  }")

        result = edited.get_contents()
        assert "public static function public static function" not in result
        assert result.count("public static function bar") == 1
