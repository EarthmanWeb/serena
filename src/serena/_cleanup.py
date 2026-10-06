"""Remove only this retired fork's own uv-cached copies. Pure helpers take paths; run() resolves them."""

import json
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

OLD_FORK = "github.com/earthmanweb/serena"
_ANSI = re.compile(r"\x1b\[[0-9;]*[A-Za-z]")
_URL = re.compile(r"^\s*url\s*=\s*(\S+)\s*$", re.IGNORECASE | re.MULTILINE)


def _log(msg: str) -> None:
    sys.stderr.write(f"serena-tombstone: {msg}\n")


def normalize_url(url: str) -> str:
    u = url.strip().lower()
    u = re.sub(r"^[a-z][a-z0-9+.-]*://", "", u)
    u = re.sub(r"^git@([^:/]+):", r"\1/", u)
    u = re.sub(r"^[^/@]+@", "", u)
    u = u.rstrip("/")
    if u.endswith(".git"):
        u = u[:-4]
    return u.rstrip("/")


def is_old_fork_url(url: str) -> bool:
    return normalize_url(url) == OLD_FORK


def config_urls(config_text: str) -> list[str]:
    return _URL.findall(config_text)


def has_old_fork_url(text: str) -> bool:
    return any(is_old_fork_url(u) for u in config_urls(text))


def _uv_output(args: list[str]) -> str | None:
    uv = shutil.which("uv")
    if uv is None:
        return None
    try:
        r = subprocess.run([uv, "--color", "never", *args], capture_output=True, text=True, timeout=20)
    except (OSError, subprocess.SubprocessError) as e:
        _log(f"uv {' '.join(args)} failed: {e}")
        return None
    if r.returncode != 0:
        _log(f"uv {' '.join(args)} exit {r.returncode}: {r.stderr.strip()}")
        return None
    out = _ANSI.sub("", r.stdout).strip()
    return out or None


def _home_default(*parts: str) -> Path | None:
    try:
        return Path.home().joinpath(*parts)
    except RuntimeError:
        return None


def _resolve(env_name: str, uv_args: list[str], default: Path | None) -> Path | None:
    val = os.environ.get(env_name) or _uv_output(uv_args)
    if not val:
        return default
    return Path(val).expanduser()


def resolve_cache_dir() -> Path | None:
    return _resolve("UV_CACHE_DIR", ["cache", "dir"], _home_default(".cache", "uv"))


def resolve_tool_dir() -> Path | None:
    return _resolve("UV_TOOL_DIR", ["tool", "dir"], _home_default(".local", "share", "uv", "tools"))


def resolve_bin_dir() -> Path | None:
    for name in ("UV_TOOL_BIN_DIR", "XDG_BIN_HOME"):
        if os.environ.get(name):
            return Path(os.environ[name]).expanduser()
    return _resolve("UV_TOOL_BIN_DIR", ["tool", "dir", "--bin"], _home_default(".local", "bin"))


def is_contained(path: Path, root: Path) -> bool:
    """True when realpath(path) is strictly inside realpath(root)."""
    try:
        rp, rr = Path(os.path.realpath(path)), Path(os.path.realpath(root))
    except OSError:
        return False
    return rp != rr and rr in rp.parents


def safe_rmtree(path: Path, root: Path) -> bool:
    if not is_contained(path, root):
        _log(f"refusing to remove {path}: outside {root}")
        return False
    try:
        shutil.rmtree(os.path.realpath(path))
        return True
    except OSError as e:
        _log(f"remove {path} failed: {e}")
        return False


def fetch_head_urls(text: str) -> list[str]:
    """URL = text after the last ' of ' on each FETCH_HEAD line."""
    urls = []
    for line in text.splitlines():
        if " of " in line:
            urls.append(line.rsplit(" of ", 1)[1].strip())
    return urls


def _read(path: Path) -> str:
    try:
        return path.read_text(errors="ignore")
    except OSError:
        return ""


def db_names_old_fork(db: Path) -> bool:
    for fh in (db / ".git" / "FETCH_HEAD", db / "FETCH_HEAD"):
        if any(is_old_fork_url(u) for u in fetch_head_urls(_read(fh))):
            return True
    return any(has_old_fork_url(_read(cfg)) for cfg in (db / ".git" / "config", db / "config"))


def direct_urls(prefix: Path) -> list[str]:
    urls: list[str] = []
    for f in prefix.glob("lib*/python*/site-packages/*.dist-info/direct_url.json"):
        urls.extend(_json_urls(f))
    for f in prefix.glob("Lib/site-packages/*.dist-info/direct_url.json"):
        urls.extend(_json_urls(f))
    return urls


def _json_urls(f: Path) -> list[str]:
    try:
        u = json.loads(f.read_text()).get("url")
    except (OSError, ValueError, AttributeError) as e:
        _log(f"unreadable {f}: {e}")
        return []
    return [u] if isinstance(u, str) else []


NEW_FORK = "github.com/earthmanweb/em-serena"


def clean_git_cache(cache: Path) -> list[Path]:
    removed: list[Path] = []
    db_root = cache / "git-v0" / "db"
    if not db_root.is_dir():
        return removed
    for db in sorted(db_root.iterdir()):
        if not db.is_dir():
            continue
        if not db_names_old_fork(db):
            continue
        checkout = cache / "git-v0" / "checkouts" / db.name
        if checkout.exists() and safe_rmtree(checkout, cache):
            removed.append(checkout)
        if safe_rmtree(db, cache):
            removed.append(db)
    return removed


def clean_running_env(cache: Path, prefix: str | None = None) -> Path | None:
    p = Path(prefix if prefix is not None else sys.prefix)
    norm = [normalize_url(u) for u in direct_urls(p)]
    if NEW_FORK in norm or OLD_FORK not in norm:
        return None
    return p if safe_rmtree(p, cache) else None


def clean_tool_env(tool_dir: Path, bin_dir: Path | None) -> list[Path]:
    removed: list[Path] = []
    env = tool_dir / "serena-agent"
    try:
        receipt = (env / "uv-receipt.toml").read_text(errors="ignore")
    except OSError:
        return removed
    if not any(is_old_fork_url(u) for u in re.findall(r"""["']([^"'\\]*)["']""", receipt)):
        return removed
    env_real = Path(os.path.realpath(env))
    if bin_dir is not None and bin_dir.is_dir():
        for shim in sorted(bin_dir.iterdir()):
            if shim.is_symlink() and env_real in Path(os.path.realpath(shim)).parents:
                try:
                    shim.unlink()
                    removed.append(shim)
                except OSError as e:
                    _log(f"unlink {shim} failed: {e}")
    if safe_rmtree(env, tool_dir):
        removed.append(env)
    return removed


_SHA = re.compile(r"[0-9a-f]{7,40}")


def _fetched_shas(db: Path, checkouts: Path) -> set[str]:
    """Commits a git-v0 db fetched: FETCH_HEAD shas plus checkout dir names (lowercase hex)."""
    shas: set[str] = set()
    for fh in (db / ".git" / "FETCH_HEAD", db / "FETCH_HEAD"):
        for line in _read(fh).splitlines():
            first = line.strip().split(maxsplit=1)[:1]
            if first and _SHA.fullmatch(first[0].lower()):
                shas.add(first[0].lower())
    if checkouts.is_dir():
        shas.update(d.name.lower() for d in checkouts.iterdir() if _SHA.fullmatch(d.name.lower()))
    return shas


def collect_fork_shas(cache: Path) -> tuple[set[str], set[str]]:
    """(old-fork shas, shas fetched by any other git url). Call BEFORE clean_git_cache."""
    old: set[str] = set()
    other: set[str] = set()
    db_root = cache / "git-v0" / "db"
    if not db_root.is_dir():
        return old, other
    for db in sorted(db_root.iterdir()):
        if db.is_dir():
            shas = _fetched_shas(db, cache / "git-v0" / "checkouts" / db.name)
            (old if db_names_old_fork(db) else other).update(shas)
    return old, other


def _sha_in(sha16: str, shas: set[str]) -> bool:
    return any(sha16.startswith(s) or s.startswith(sha16) for s in shas)


def _versioned(cache: Path, prefix: str) -> list[Path]:
    return sorted(p for p in cache.glob(f"{prefix}-v*") if p.is_dir())


def _link_targets(d: Path) -> list[Path]:
    return [Path(os.path.realpath(e)) for e in d.iterdir() if e.is_symlink()]


def _sdist_dirs(cache: Path) -> list[Path]:
    return [
        s
        for b in _versioned(cache, "sdists")
        for u in sorted((b / "git").glob("*"))
        for s in sorted(u.glob("*"))
        if s.is_dir() and not s.is_symlink()
    ]


def _live_targets(cache: Path) -> set[Path]:
    """Realpaths still referenced by sdists-v*/git and environments-v* symlinks."""
    live: set[Path] = set()
    for b in _versioned(cache, "environments"):
        for h in b.iterdir():
            if h.is_dir() and not h.is_symlink():
                live.update(_link_targets(h))
    for s in _sdist_dirs(cache):
        live.update(_link_targets(s))
    return live


def _drop_empty(d: Path, cache: Path) -> None:
    """Remove d when only .lock files remain."""
    if d.is_dir() and not d.is_symlink() and all(e.name == ".lock" for e in d.iterdir()):
        safe_rmtree(d, cache)


def clean_build_cache(
    cache: Path, old_shas: set[str] | None = None, other_shas: set[str] | None = None
) -> list[Path]:
    """Remove env/sdist/archive entries traced to OLD_FORK only. Pass shas collected before clean_git_cache."""
    if old_shas is None or other_shas is None:
        old_shas, other_shas = collect_fork_shas(cache)
    removed: list[Path] = []
    archives: list[Path] = []
    # environments-v*/<h>/<h2> -> archive venv; URL from its direct_url.json
    for b in _versioned(cache, "environments"):
        for h in sorted(b.iterdir()):
            if not h.is_dir() or h.is_symlink():
                continue
            for link in sorted(h.iterdir()):
                real = Path(os.path.realpath(link))
                if not real.is_dir() or not any(is_old_fork_url(u) for u in direct_urls(real)):
                    continue
                if not link.is_symlink():
                    if safe_rmtree(link, cache):
                        removed.append(link)
                    continue
                if not is_contained(real, cache):
                    _log(f"refusing to remove {link}: target outside {cache}")
                    continue
                try:
                    link.unlink()
                except OSError as e:
                    _log(f"remove {link} failed: {e}")
                    continue
                removed.append(link)
                archives.append(real)
            _drop_empty(h, cache)
    # sdists-v*/git/<urlhash>/<sha16>: commit fetched only by old-fork dbs
    for s in _sdist_dirs(cache):
        sha16 = s.name.lower()
        if not _sha_in(sha16, old_shas) or _sha_in(sha16, other_shas):
            continue
        archives.extend(_link_targets(s))
        if safe_rmtree(s, cache):
            removed.append(s)
        _drop_empty(s.parent, cache)
    # archive-v*/<id> venvs whose direct_url names the old fork
    for b in _versioned(cache, "archive"):
        for a in sorted(b.iterdir()):
            if a.is_dir() and any(is_old_fork_url(u) for u in direct_urls(a)):
                archives.append(Path(os.path.realpath(a)))
    live = _live_targets(cache)
    for t in dict.fromkeys(archives):
        if t not in live and t.exists() and safe_rmtree(t, cache):
            removed.append(t)
    return removed


def run() -> None:
    try:
        cache = resolve_cache_dir()
        if cache is not None and cache.is_dir():
            old_shas, other_shas = collect_fork_shas(cache)
            clean_build_cache(cache, old_shas, other_shas)
            clean_git_cache(cache)
            clean_running_env(cache)
        tool_dir = resolve_tool_dir()
        if tool_dir is not None and tool_dir.is_dir():
            clean_tool_env(tool_dir, resolve_bin_dir())
    except Exception as e:  # report, never swallow silently
        _log(f"cleanup error: {type(e).__name__}: {e}")
