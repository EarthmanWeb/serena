import importlib.util
import json
import os
import tempfile
import unittest
from pathlib import Path

SPEC = importlib.util.spec_from_file_location(
    "tomb_cleanup", Path(__file__).resolve().parent.parent / "src" / "serena" / "_cleanup.py"
)
c = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(c)

OLD = "https://github.com/EarthmanWeb/serena"
NEW = "https://github.com/EarthmanWeb/" + "em-" + "serena"


def mk_db(cache: Path, name: str, url: str) -> tuple[Path, Path]:
    db = cache / "git-v0" / "db" / name
    co = cache / "git-v0" / "checkouts" / name / "abc1234"
    (db / ".git").mkdir(parents=True)
    co.mkdir(parents=True)
    (db / ".git" / "config").write_text("[core]\n\trepositoryformatversion = 0\n")
    sha = "0123456789abcdef0123456789abcdef01234567"
    (db / ".git" / "FETCH_HEAD").write_text(f"{sha}\t\t'{sha}' of {url}\n")
    return db, co.parent


class CleanupTest(unittest.TestCase):
    def setUp(self) -> None:
        self._t = tempfile.TemporaryDirectory()
        self.tmp = Path(self._t.name).resolve()
        self.cache = self.tmp / "cache"
        self.cache.mkdir()
        self.addCleanup(self._t.cleanup)

    def test_old_url_removed_with_checkouts(self) -> None:
        db, co = mk_db(self.cache, "h1", OLD)
        c.clean_git_cache(self.cache)
        self.assertFalse(db.exists())
        self.assertFalse(co.exists())

    def test_new_fork_kept(self) -> None:
        db, co = mk_db(self.cache, "h2", NEW)
        c.clean_git_cache(self.cache)
        self.assertTrue(db.exists())
        self.assertTrue(co.exists())

    def test_url_variants_removed(self) -> None:
        urls = [
            "https://github.com/EarthmanWeb/serena.git",
            "HTTPS://GITHUB.COM/EARTHMANWEB/SERENA/",
            "git@github.com:EarthmanWeb/serena.git",
        ]
        for i, u in enumerate(urls):
            db, _ = mk_db(self.cache, f"v{i}", u)
            c.clean_git_cache(self.cache)
            self.assertFalse(db.exists(), u)

    def test_non_matching_kept(self) -> None:
        kept = [
            mk_db(self.cache, "k1", "https://github.com/EarthmanWeb/serena-workflow-engine")[0],
            mk_db(self.cache, "k2", "https://github.com/oraios/serena")[0],
            mk_db(self.cache, "k3", "https://github.com/EarthmanWeb/serena-extra.git")[0],
        ]
        nocfg = self.cache / "git-v0" / "db" / "k4"
        (nocfg / ".git").mkdir(parents=True)
        c.clean_git_cache(self.cache)
        for k in kept + [nocfg]:
            self.assertTrue(k.exists(), k)

    def test_fetch_head_forms_and_bare_layout(self) -> None:
        self.assertEqual(c.fetch_head_urls("s\t\tbranch 'x' of https://h/a of b\n"), ["b"])
        db = self.cache / "git-v0" / "db" / "bare1"
        db.mkdir(parents=True)
        (db / "FETCH_HEAD").write_text(f"s\t\ttag 'v1' of {OLD}\n")
        c.clean_git_cache(self.cache)
        self.assertFalse(db.exists())

    def _env(self, name: str, url: str | None) -> Path:
        env = self.cache / "archive-v0" / name
        sp = env / "lib" / "python3.12" / "site-packages" / "serena_agent-99.dist-info"
        sp.mkdir(parents=True)
        if url is not None:
            (sp / "direct_url.json").write_text(json.dumps({"url": url, "vcs_info": {"vcs": "git"}}))
        return env

    def test_running_env_new_fork_or_unknown_kept(self) -> None:
        for i, u in enumerate([NEW, None, "https://github.com/oraios/serena"]):
            env = self._env(f"k{i}", u)
            self.assertIsNone(c.clean_running_env(self.cache, str(env)))
            self.assertTrue(env.exists())

    def test_running_env_inside_cache_removed(self) -> None:
        env = self._env("abc", OLD + ".git")
        self.assertEqual(c.clean_running_env(self.cache, str(env)), env)
        self.assertFalse(env.exists())
        self.assertTrue(env.parent.exists())

    def test_running_env_outside_cache_kept(self) -> None:
        env = self.tmp / "venv"
        sp = env / "lib" / "python3.12" / "site-packages" / "x.dist-info"
        sp.mkdir(parents=True)
        (sp / "direct_url.json").write_text(json.dumps({"url": OLD}))
        self.assertIsNone(c.clean_running_env(self.cache, str(env)))
        self.assertTrue(env.exists())

    def _tool(self, url: str) -> tuple[Path, Path, Path, Path]:
        tools, bin_ = self.tmp / "tools", self.tmp / "bin"
        env = tools / "serena-agent"
        (env / "bin").mkdir(parents=True)
        (env / "bin" / "serena").write_text("")
        bin_.mkdir()
        shim = bin_ / "serena"
        shim.symlink_to(env / "bin" / "serena")
        (bin_ / "other").symlink_to(self.tmp / "elsewhere")
        (env / "uv-receipt.toml").write_text(f'[tool]\nrequirements = [{{ name = "serena-agent", git = "{url}" }}]\n')
        return tools, bin_, env, shim

    def test_tool_old_removed(self) -> None:
        tools, bin_, env, shim = self._tool(OLD + ".git")
        c.clean_tool_env(tools, bin_)
        self.assertFalse(env.exists())
        self.assertFalse(shim.is_symlink())
        self.assertTrue((bin_ / "other").is_symlink())

    def test_tool_new_kept(self) -> None:
        tools, bin_, env, shim = self._tool(NEW)
        c.clean_tool_env(tools, bin_)
        self.assertTrue(env.exists())
        self.assertTrue(shim.is_symlink())

    def test_containment_refusal(self) -> None:
        outside = self.tmp / "outside"
        outside.mkdir()
        (self.cache / "link").symlink_to(outside)
        self.assertFalse(c.safe_rmtree(outside, self.cache))
        self.assertFalse(c.safe_rmtree(self.cache / "link", self.cache))
        self.assertFalse(c.safe_rmtree(self.cache, self.cache))
        self.assertFalse(c.safe_rmtree(self.cache / ".." / "outside", self.cache))
        self.assertTrue(outside.exists())

    def test_env_var_resolution(self) -> None:
        old = os.environ.get("UV_CACHE_DIR")
        os.environ["UV_CACHE_DIR"] = str(self.cache)
        try:
            self.assertEqual(c.resolve_cache_dir(), self.cache)
        finally:
            if old is None:
                del os.environ["UV_CACHE_DIR"]
            else:
                os.environ["UV_CACHE_DIR"] = old

    def test_url_slug_exact_match(self) -> None:
        for u in (
            "github.com/EarthmanWeb/serena",
            "https://github.com/EarthmanWeb/serena.git",
            "ssh://git@github.com/earthmanweb/serena.git/",
            "git@github.com:EarthmanWeb/serena.git",
        ):
            self.assertTrue(c.is_old_fork_url(u), u)
        for slug in ("serena-workflow-engine", "em-serena", "serena-tombstone-e2e"):
            self.assertFalse(c.is_old_fork_url(f"https://github.com/earthmanweb/{slug}"), slug)

    # --- build cache (layout mirrors uv 0.9: sdists-v9/git/<urlhash>/<sha16>, archive-v0, environments-v2)

    def _venv_archive(self, aid: str, url: str | None) -> Path:
        a = self.cache / "archive-v0" / aid
        di = a / "lib" / "python3.14" / "site-packages" / "serena_agent-0.0.1.dist-info"
        di.mkdir(parents=True)
        if url is not None:
            (di / "direct_url.json").write_text(json.dumps({"url": url}))
        return a

    def _build(self, tag: str, url: str, sha: str) -> dict[str, Path]:
        db, co = mk_db(self.cache, "db" + tag, url)
        (db / ".git" / "FETCH_HEAD").write_text(f"{sha}\t\tbranch 'swe' of {url}\n")
        self.assertTrue(co.exists())
        wheel = self.cache / "archive-v0" / ("w" + tag)
        wheel.mkdir(parents=True)
        (wheel / "pkg.py").write_text("")
        sd = self.cache / "sdists-v9" / "git" / ("u" + tag) / sha[:16]
        sd.mkdir(parents=True)
        (sd / ".lock").write_text("")
        (sd / "pkg-0.1-py3-none-any").symlink_to(wheel)
        (self.cache / "sdists-v9" / "git" / ("e" + tag) / sha[:16]).mkdir(parents=True)
        (self.cache / "sdists-v9" / "git" / ("e" + tag) / sha[:16] / ".lock").write_text("")
        venv = self._venv_archive("v" + tag, url)
        env = self.cache / "environments-v2" / ("h" + tag) / "h2"
        env.parent.mkdir(parents=True)
        env.symlink_to(venv)
        return {"db": db, "sdist": sd, "wheel": wheel, "venv": venv, "env": env, "sd_parent": sd.parent}

    def test_build_cache_old_removed_others_kept(self) -> None:
        sha_o, sha_n, sha_g = "a" * 40, "b" * 40, "c" * 40
        old = self._build("o", OLD + ".git", sha_o)
        new = self._build("n", NEW, sha_n)
        git = self._build("g", "https://github.com/oraios/serena", sha_g)
        pypi = self.cache / "archive-v0" / "pypi1"
        pypi.mkdir()
        self._venv_archive("pypivenv", None)
        (self.cache / "wheels-v5" / "pypi" / "setuptools").mkdir(parents=True)
        old_shas, other_shas = c.collect_fork_shas(self.cache)
        c.clean_git_cache(self.cache)  # git-v0 gone first; shas were collected earlier
        removed = c.clean_build_cache(self.cache, old_shas, other_shas)
        self.assertTrue(removed)
        for k in ("sdist", "wheel", "venv"):
            self.assertFalse(old[k].exists(), k)
        self.assertFalse(old["env"].is_symlink())
        self.assertFalse(old["sd_parent"].exists())
        for entry in (new, git):
            for k in ("sdist", "wheel", "venv"):
                self.assertTrue(entry[k].exists(), k)
            self.assertTrue(entry["env"].is_symlink())
        self.assertTrue(pypi.exists())
        self.assertTrue((self.cache / "archive-v0" / "pypivenv").exists())
        self.assertTrue((self.cache / "wheels-v5" / "pypi" / "setuptools").exists())
        self.assertEqual(c.clean_build_cache(self.cache, old_shas, other_shas), [])

    def test_build_cache_env_traced_by_direct_url_after_git_cleaned(self) -> None:
        venv = self._venv_archive("zz", OLD)
        env = self.cache / "environments-v7" / "h" / "h2"
        env.parent.mkdir(parents=True)
        env.symlink_to(venv)
        c.clean_build_cache(self.cache, set(), set())
        self.assertFalse(venv.exists())
        self.assertFalse(env.is_symlink())

    def test_build_cache_shared_sha_kept(self) -> None:
        sha = "d" * 40
        old = self._build("o", OLD, sha)
        other = self._build("n", NEW, sha)
        c.clean_build_cache(self.cache)
        self.assertTrue(old["sdist"].exists())
        self.assertTrue(other["sdist"].exists())
        self.assertFalse(old["env"].is_symlink())
        self.assertTrue(other["env"].is_symlink())

    def test_build_cache_symlink_outside_refused(self) -> None:
        outside = self.tmp / "outside"
        di = outside / "lib" / "python3.14" / "site-packages" / "x.dist-info"
        di.mkdir(parents=True)
        (di / "direct_url.json").write_text(json.dumps({"url": OLD}))
        env = self.cache / "environments-v2" / "h" / "h2"
        env.parent.mkdir(parents=True)
        env.symlink_to(outside)
        c.clean_build_cache(self.cache, set(), set())
        self.assertTrue(env.is_symlink())
        self.assertTrue(outside.exists())

    def test_build_cache_sdist_wheel_link_outside_kept(self) -> None:
        outside = self.tmp / "outside"
        outside.mkdir()
        sha = "e" * 40
        sd = self.cache / "sdists-v9" / "git" / "u" / sha[:16]
        sd.mkdir(parents=True)
        (sd / "w").symlink_to(outside)
        c.clean_build_cache(self.cache, {sha}, set())
        self.assertFalse(sd.exists())
        self.assertTrue(outside.exists())


if __name__ == "__main__":
    unittest.main()
