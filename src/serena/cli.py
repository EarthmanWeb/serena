"""Console script target: clean old uv caches (stderr only), then serve the tombstone MCP server."""

import sys

from . import _cleanup, mcp
from .notice import NOTICE


def main(argv: list[str] | None = None) -> int:
    del argv  # any arguments are accepted and ignored
    sys.stderr.write(NOTICE + "\n")
    _cleanup.run()
    return mcp.serve()


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
