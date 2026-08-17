"""Unit tests for the PHP modifier-range widener.

Pins the contract that ``widen_start_over_php_modifiers`` moves a symbol's body-range
start leftward across a contiguous run of leading PHP modifier keywords (visibility,
``static``, ``final``, ``abstract``, ``readonly``, ``var``) and STOPS at whitespace-only
gaps' end, statement boundaries, docblocks, and non-modifier tokens. The widening is what
makes ``replace_symbol_body`` round-trips lossless for modifier-bearing PHP symbols.
"""

from solidlsp.php_modifier_range import widen_start_over_php_modifiers


def _lines(text: str) -> list[str]:
    return text.split("\n")


class TestWidenStartOverPhpModifiers:
    def test_public_static_method_same_line(self) -> None:
        # "  public static function bar(): void {" — LS start at "function" (col 16).
        line = "  public static function bar(): void {"
        assert line.index("function") == 16
        assert widen_start_over_php_modifiers([line], 0, 16) == (0, 2)

    def test_start_at_name_widens_to_first_modifier(self) -> None:
        # Some LSs report start at the symbol NAME rather than "function".
        line = "  private static function bar(): void {"
        col = line.index("bar")
        assert widen_start_over_php_modifiers([line], 0, col) == (0, 2)

    def test_single_visibility_modifier(self) -> None:
        line = "    public function baz() {"
        col = line.index("function")
        assert widen_start_over_php_modifiers([line], 0, col) == (0, 4)

    def test_final_abstract_run(self) -> None:
        line = "  final public function q() {}"
        col = line.index("function")
        assert widen_start_over_php_modifiers([line], 0, col) == (0, 2)

    def test_typed_property_readonly(self) -> None:
        # "  public readonly int $x;" — LS range often starts at the type or the var.
        line = "  public readonly int $x;"
        col = line.index("int")
        assert widen_start_over_php_modifiers([line], 0, col) == (0, 2)

    def test_no_modifiers_unchanged(self) -> None:
        line = "  function bar() {}"
        col = line.index("function")
        assert widen_start_over_php_modifiers([line], 0, col) == (0, col)

    def test_idempotent_when_already_at_modifier(self) -> None:
        line = "  public static function bar() {}"
        # Already at "public" (col 2) — must not move further left.
        assert widen_start_over_php_modifiers([line], 0, 2) == (0, 2)

    def test_stops_at_docblock(self) -> None:
        # A docblock line precedes the declaration; it must NOT be absorbed.
        text = "  /** doc */\n  public function bar() {}"
        lines = _lines(text)
        col = lines[1].index("function")
        assert widen_start_over_php_modifiers(lines, 1, col) == (1, 2)

    def test_stops_at_previous_statement_boundary(self) -> None:
        # Preceding line ends in ';' — the modifier run cannot cross it.
        text = "    $x = 1;\n    public function bar() {}"
        lines = _lines(text)
        col = lines[1].index("function")
        assert widen_start_over_php_modifiers(lines, 1, col) == (1, 4)

    def test_modifiers_span_previous_line(self) -> None:
        # Modifiers wrapped onto their own line above the "function" keyword.
        text = "  public static\n  function bar(): void {"
        lines = _lines(text)
        col = lines[1].index("function")
        assert widen_start_over_php_modifiers(lines, 1, col) == (0, 2)

    def test_does_not_absorb_prior_non_modifier_token(self) -> None:
        # "public_thing" is one token, not the "public" keyword — must stop.
        line = "    return public_thing();"
        col = line.index("public_thing")
        assert widen_start_over_php_modifiers([line], 0, col) == (0, col)

    def test_out_of_range_line_is_safe(self) -> None:
        assert widen_start_over_php_modifiers(["x"], 5, 0) == (5, 0)
