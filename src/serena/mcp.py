"""Minimal stdlib-only MCP server: newline-delimited JSON-RPC 2.0 over stdin/stdout. Logs go to stderr."""

import json
import sys
from typing import IO, Any

from . import __version__
from .notice import NOTICE

DEFAULT_PROTOCOL = "2025-06-18"


def _error(req_id: Any, code: int, message: str) -> dict:
    return {"jsonrpc": "2.0", "id": req_id, "error": {"code": code, "message": message}}


def handle(msg: Any) -> dict | None:
    """Return the response for one decoded message, or None when no reply is due."""
    if not isinstance(msg, dict):
        return _error(None, -32600, "Invalid Request")
    if "id" not in msg:
        return None  # notification
    req_id, method = msg["id"], msg.get("method")
    if method == "initialize":
        params = msg.get("params")
        want = params.get("protocolVersion") if isinstance(params, dict) else None
        result = {
            "protocolVersion": want if isinstance(want, str) and want else DEFAULT_PROTOCOL,
            "capabilities": {"tools": {}},
            "serverInfo": {"name": "serena-tombstone", "version": __version__},
            "instructions": NOTICE,
        }
    elif method == "ping":
        result = {}
    elif method == "tools/list":
        result = {"tools": []}
    else:
        return _error(req_id, -32601, f"Method not found: {method}")
    return {"jsonrpc": "2.0", "id": req_id, "result": result}


def serve(stdin: IO[str] | None = None, stdout: IO[str] | None = None) -> int:
    stdin = stdin or sys.stdin
    stdout = stdout or sys.stdout
    for line in stdin:
        line = line.strip()
        if not line:
            continue
        try:
            msg = json.loads(line)
        except ValueError:
            resp: dict | None = _error(None, -32700, "Parse error")
        else:
            resp = handle(msg)
        if resp is not None:
            stdout.write(json.dumps(resp, separators=(",", ":")) + "\n")
            stdout.flush()
    return 0
