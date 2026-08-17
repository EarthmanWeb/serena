<?php

namespace SerenaTest;

/**
 * Fixture for the modifier-range widening: methods carrying visibility/static/final/abstract
 * modifiers the language server excludes from the symbol range.
 */
class ModifierMethods
{
    public static function publicStatic(): void
    {
        return;
    }

    private static function privateStatic(): int
    {
        return 1;
    }

    final protected function finalProtected(): string
    {
        return "x";
    }

    public function plain(): bool
    {
        return true;
    }
}
