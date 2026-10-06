import io
import json
import os
import shutil
import subprocess
import sys
import tempfile
import tomllib
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SRC = ROOT / "src"
sys.path.insert(0, str(SRC))

from serena import mcp  # noqa: E402
from serena.notice import NOTICE  # noqa: E402

FORK_SCRIPTS = ["serena", "serena-agent", "serena-hooks"]


def isolated_env(tmp: str) -> dict:
    """Env pointing every uv dir at a temp dir so no test touches the real machine."""
    return {
        **os.environ,
        "UV_CACHE_DIR": os.path.join(tmp, "cache"),
        "UV_TOOL_DIR": os.path.join(tmp, "tools"),
        "UV_TOOL_BIN_DIR": os.path.join(tmp, "bin"),
        "XDG_BIN_HOME": os.path.join(tmp, "bin"),
    }


def rpc(**kw) -> dict:
    return {"jsonrpc": "2.0", **kw}


class ProtocolTest(unittest.TestCase):
    def test_initialize_echoes_version(self) -> None:
        r = mcp.handle(rpc(id=1, method="initialize", params={"protocolVersion": "2024-11-05"}))
        self.assertEqual(r["id"], 1)
        res = r["result"]
        self.assertEqual(res["protocolVersion"], "2024-11-05")
        self.assertEqual(res["capabilities"], {"tools": {}})
        self.assertEqual(res["serverInfo"], {"name": "serena-tombstone", "version": "99.0.0"})
        self.assertEqual(res["instructions"], NOTICE)

    def test_initialize_default_version(self) -> None:
        r = mcp.handle(rpc(id=1, method="initialize"))
        self.assertEqual(r["result"]["protocolVersion"], "2025-06-18")

    def test_tools_list_and_ping(self) -> None:
        self.assertEqual(mcp.handle(rpc(id=2, method="tools/list"))["result"], {"tools": []})
        self.assertEqual(mcp.handle(rpc(id="x", method="ping")), rpc(id="x", result={}))

    def test_unknown_method(self) -> None:
        r = mcp.handle(rpc(id=3, method="tools/call"))
        self.assertEqual(r["error"]["code"], -32601)
        self.assertEqual(r["id"], 3)

    def test_notification_no_reply(self) -> None:
        self.assertIsNone(mcp.handle(rpc(method="notifications/initialized")))

    def test_serve_parse_error_then_continues(self) -> None:
        out = io.StringIO()
        code = mcp.serve(io.StringIO("{bad\n" + json.dumps(rpc(id=1, method="ping")) + "\n"), out)
        self.assertEqual(code, 0)
        lines = [json.loads(x) for x in out.getvalue().splitlines()]
        self.assertEqual(lines[0]["error"]["code"], -32700)
        self.assertIsNone(lines[0]["id"])
        self.assertEqual(lines[1]["result"], {})

    def test_serve_eof(self) -> None:
        out = io.StringIO()
        self.assertEqual(mcp.serve(io.StringIO(""), out), 0)
        self.assertEqual(out.getvalue(), "")


class TombstoneTest(unittest.TestCase):
    def test_import_has_no_side_effects(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            env = {**isolated_env(tmp), "PYTHONPATH": str(SRC), "PYTHONDONTWRITEBYTECODE": "1"}
            r = subprocess.run(
                [sys.executable, "-c", "import serena"], cwd=ROOT, env=env, capture_output=True, text=True
            )
        self.assertEqual(r.returncode, 0)
        self.assertEqual(r.stdout + r.stderr, "")

    def test_subprocess_mcp_session(self) -> None:
        reqs = [
            rpc(id=1, method="initialize", params={"protocolVersion": "2025-03-26"}),
            rpc(method="notifications/initialized"),
            rpc(id=2, method="tools/list"),
        ]
        with tempfile.TemporaryDirectory() as tmp:
            env = {**isolated_env(tmp), "PYTHONPATH": str(SRC), "PYTHONDONTWRITEBYTECODE": "1"}
            r = subprocess.run(
                [sys.executable, "-m", "serena.cli", "start-mcp-server", "--context", "x"],
                input="".join(json.dumps(q) + "\n" for q in reqs),
                cwd=ROOT,
                env=env,
                capture_output=True,
                text=True,
                timeout=60,
            )
        self.assertEqual(r.returncode, 0, r.stderr)
        out = [json.loads(x) for x in r.stdout.splitlines()]
        self.assertEqual([o["id"] for o in out], [1, 2])
        self.assertEqual(out[0]["result"]["protocolVersion"], "2025-03-26")
        self.assertEqual(out[1]["result"], {"tools": []})
        self.assertIn(NOTICE, r.stderr)

    def test_pyproject(self) -> None:
        data = tomllib.loads((ROOT / "pyproject.toml").read_text())
        proj = data["project"]
        self.assertEqual(proj["name"], "serena-agent")
        self.assertEqual(proj["version"], "99.0.0")
        self.assertEqual(proj.get("dependencies", []), [])
        self.assertEqual(sorted(proj["scripts"]), sorted(FORK_SCRIPTS))
        self.assertNotIn("authors", proj)

    def test_no_forbidden_strings(self) -> None:
        forbidden = ["claude-" + "workflow-engine", "EM_CWE_" + "TOKEN", "EM_SWE_" + "TOKEN"]
        for p in ROOT.rglob("*"):
            if not p.is_file() or ".git" in p.relative_to(ROOT).parts or "__pycache__" in p.parts:
                continue
            text = p.read_text(errors="ignore")
            for s in forbidden:
                self.assertNotIn(s, text, f"{s} in {p}")

    def test_uv_run_with_tree(self) -> None:
        uv = shutil.which("uv")
        if uv is None:
            self.skipTest("uv missing")
        with tempfile.TemporaryDirectory() as tmp:
            r = subprocess.run(
                [uv, "run", "--no-project", "--with", str(ROOT), "python", "-c", "import serena"],
                capture_output=True,
                text=True,
                cwd="/tmp",
                env=isolated_env(tmp),
            )
        self.assertEqual(r.returncode, 0, r.stderr)


if __name__ == "__main__":
    unittest.main()
