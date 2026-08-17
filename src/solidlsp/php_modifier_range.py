"""PHP method/function/property modifier-range widening.

Intelephense (and other PHP language servers) report a symbol's ``location.range``
starting at the ``function`` keyword or the symbol name — the leading visibility/
``static``/``final``/``abstract``/``readonly`` modifiers fall OUTSIDE the range.

That asymmetry is a corruption trap for ``replace_symbol_body``: ``include_body=True``
returns a body WITHOUT the modifiers, but a caller naturally re-supplies the full
declaration it sees in the file (``public static function name(...) {...}``). The
replacement is spliced into a range that still contains the original modifiers, so the
result is ``public static function public static function name(...)`` — a parse fatal.

Fix: widen the body-range start LEFTWARD across a contiguous run of leading modifier
tokens so the stored range is modifier-inclusive. Then ``include_body`` RETURNS the
modifiers and ``replace_symbol_body`` CONSUMES them — the round-trip is lossless and
what you read is exactly what you write.

Only ``location.range`` is affected; the identifier position (``selectionRange``) is a
separate range and is left untouched, so reference/definition resolution is unchanged.
"""

from __future__ import annotations

from overrides import override

from solidlsp import ls_types
from solidlsp.ls import DocumentSymbols, LSPFileBuffer, SolidLanguageServer, SymbolBodyFactory

# PHP declaration modifiers that a language server may exclude from a symbol's range.
# `var` is the legacy property-declaration keyword; included for completeness.
PHP_MODIFIER_KEYWORDS = frozenset(
    {
        "public",
        "private",
        "protected",
        "static",
        "final",
        "abstract",
        "readonly",
        "var",
    }
)

# Declaration keywords that sit BETWEEN the symbol name and its modifiers. When a language
# server reports the range start at the symbol NAME, the scan must cross these to reach the
# modifiers in front of them. They are crossed (not absorbed as the widened start) and never
# terminate the run on their own.
PHP_DECLARATION_KEYWORDS = frozenset({"function", "fn", "const"})

# Characters that terminate the preceding statement/block; a modifier run cannot cross one.
_BOUNDARY_CHARS = frozenset({";", "{", "}", ")"})


def widen_start_over_php_modifiers(lines: list[str], start_line: int, start_col: int) -> tuple[int, int]:
    """Return a ``(line, col)`` start position widened leftward over leading PHP modifiers.

    Scans the text immediately preceding ``(start_line, start_col)`` (walking to earlier
    lines as needed) and, as long as it sees only whitespace and whole PHP modifier
    keywords, moves the start position to the beginning of the earliest such keyword.
    Stops at a statement boundary (``;`` ``{`` ``}`` ``)``), a docblock/comment, or any
    non-modifier token — so a docblock, attribute, or the previous statement is never
    absorbed.

    Idempotent: a range that already begins at the first modifier is returned unchanged.

    :param lines: file contents split into lines (no trailing newlines).
    :param start_line: 0-based start line of the symbol's ``location.range``.
    :param start_col: 0-based start column of the symbol's ``location.range``.
    :return: the widened ``(start_line, start_col)``; unchanged if no modifier run precedes.
    """
    if start_line < 0 or start_line >= len(lines):
        return start_line, start_col

    result_line, result_col = start_line, start_col
    cur_line, cur_col = start_line, start_col

    while True:
        # Collect the text on the current line up to the cursor.
        prefix = lines[cur_line][:cur_col]
        stripped = prefix.rstrip()

        if stripped == "":
            # Only whitespace before the cursor on this line — continue on the previous line.
            if cur_line == 0:
                break
            cur_line -= 1
            cur_col = len(lines[cur_line])
            continue

        # A statement/block boundary or comment terminator ends the modifier run.
        last_char = stripped[-1]
        if last_char in _BOUNDARY_CHARS or stripped.endswith("*/"):
            break

        # Identify the last whitespace-delimited token immediately before the cursor.
        token_end = len(stripped)
        token_start = token_end
        while token_start > 0 and not stripped[token_start - 1].isspace():
            token_start -= 1
        token = stripped[token_start:token_end]
        token_lower = token.lower()

        if token_lower in PHP_DECLARATION_KEYWORDS:
            # Cross the declaration keyword (e.g. "function") to reach modifiers in front of
            # it, without recording it as the widened start.
            cur_col = token_start
            continue

        if token_lower not in PHP_MODIFIER_KEYWORDS:
            break

        # Absorb this modifier: move the result start to the token's beginning.
        result_line, result_col = cur_line, token_start
        # Continue scanning from just before this token on the same line.
        cur_col = token_start

    return result_line, result_col


# Symbol kinds whose PHP declaration may carry leading modifiers the language server excludes
# from the reported range (methods, functions, typed/visibility properties, class constants).
_PHP_MODIFIER_BEARING_KINDS = frozenset(
    {
        ls_types.SymbolKind.Method,
        ls_types.SymbolKind.Function,
        ls_types.SymbolKind.Field,
        ls_types.SymbolKind.Property,
        ls_types.SymbolKind.Constant,
    }
)


class PhpModifierRangeMixin(SolidLanguageServer):
    """Mixin for PHP language servers that widens modifier-bearing symbol ranges.

    Intelephense/phpactor/phpantom report a method/function/property range starting at the
    ``function`` keyword or the symbol name — the leading ``public``/``static``/``final``/
    ``abstract``/``readonly`` modifiers fall OUTSIDE the range. That makes
    :meth:`replace_symbol_body` omit the modifiers from both the displayed body and the
    replacement range, so re-supplying the full declaration in an edit corrupts the file
    (``public static function`` becomes ``public static function public static function``).

    This override extends such ranges leftward to include the modifiers, so ``include_body``
    returns them and ``replace_symbol_body`` consumes them — the round-trip is lossless.
    ``selectionRange`` (the identifier position) is a separate range and is left untouched, so
    reference/definition resolution is unaffected. Mirrors the gopls leading-keyword extension.
    """

    @override
    def request_document_symbols(self, relative_file_path: str, file_buffer: LSPFileBuffer | None = None) -> DocumentSymbols:
        document_symbols = super().request_document_symbols(relative_file_path, file_buffer=file_buffer)
        if not document_symbols.root_symbols:
            return document_symbols

        with self._open_file_context(relative_file_path, file_buffer, open_in_ls=False) as file_data:
            file_lines = file_data.split_lines()
            body_factory = SymbolBodyFactory(file_data)

            def extend_symbol_and_children(symbol: ls_types.UnifiedSymbolInformation) -> ls_types.UnifiedSymbolInformation:
                extended = self._extend_php_symbol_range_over_modifiers(symbol, file_lines, body_factory)
                children = symbol.get("children")
                if children:
                    if extended is symbol:
                        extended = symbol.copy()
                    extended["children"] = [extend_symbol_and_children(child) for child in children]
                return extended

            extended_root_symbols = [extend_symbol_and_children(sym) for sym in document_symbols.root_symbols]

        return DocumentSymbols(extended_root_symbols)

    @staticmethod
    def _extend_php_symbol_range_over_modifiers(
        symbol: ls_types.UnifiedSymbolInformation,
        file_lines: list[str],
        body_factory: SymbolBodyFactory,
    ) -> ls_types.UnifiedSymbolInformation:
        """Return a copy of ``symbol`` whose range start is widened over leading PHP modifiers.

        Returns the original symbol unchanged when it is not a modifier-bearing kind or when no
        modifier run precedes the range start.
        """
        if symbol.get("kind") not in _PHP_MODIFIER_BEARING_KINDS:
            return symbol
        range_info = symbol.get("range")
        if not range_info:
            return symbol

        start_line = range_info["start"]["line"]
        start_char = range_info["start"]["character"]
        new_line, new_char = widen_start_over_php_modifiers(file_lines, start_line, start_char)
        if (new_line, new_char) == (start_line, start_char):
            return symbol

        new_start = ls_types.Position(line=new_line, character=new_char)
        extended = symbol.copy()
        extended["range"] = ls_types.Range(start=new_start, end=range_info["end"])
        location = extended.get("location")
        if location:
            location = location.copy()
            if "range" in location:
                location["range"] = ls_types.Range(start=new_start, end=location["range"]["end"])
            extended["location"] = location

        # recompute the body from the extended location range; the stale SymbolBody must be
        # removed first, since the factory returns an existing SymbolBody as-is.
        extended.pop("body", None)
        extended["body"] = body_factory.create_symbol_body(extended)
        return extended
