"""
Intelephense resource settings (no language server process is started).

Evidence (intelephense 1.14.4 bundle): the server reads only storagePath/globalStoragePath/licenceKey/clearCache
from initializationOptions; ``files.exclude``/``files.maxSize`` are read from the client configuration
(``workspace/configuration``, requested only if the client advertises that capability), and ``maxMemory`` is not
a server setting at all (the VS Code client passes it as node's ``--max-old-space-size``). Intelephense walks all
workspace folders itself, so without excludes it indexes gitignored trees such as WP core under public_html/.
"""

import os
from pathlib import Path

import pytest

from solidlsp.language_servers.intelephense import DEFAULT_INTELEPHENSE_EXCLUDE, Intelephense
from solidlsp.ls_config import Language, LanguageServerConfig
from solidlsp.settings import SolidLSPSettings


def _create_ls(tmp_path: Path, root: Path, php_settings: dict, ignored_paths: list[str], additional: list[str]) -> Intelephense:
    config = LanguageServerConfig(
        code_language=Language.PHP,
        ignored_paths=ignored_paths,
        additional_workspace_folders=additional,
    )
    settings = SolidLSPSettings(
        solidlsp_dir=str(tmp_path / "solidlsp"),
        project_data_path=str(tmp_path / "data"),
        ls_specific_settings={Language.PHP: php_settings},
    )
    return Intelephense(config, str(root), settings)


@pytest.fixture()
def repos(tmp_path: Path) -> tuple[Path, Path]:
    root = tmp_path / "base"
    (root / "src").mkdir(parents=True)
    (root / "src" / "a.php").write_text("<?php\n")
    (root / "build").mkdir()
    sibling = tmp_path / "site"
    (sibling / "public_html" / "wp-includes").mkdir(parents=True)
    (sibling / "wp-content" / "plugins" / "em-x" / "vendor" / "pkg").mkdir(parents=True)
    (sibling / "wp-content" / "plugins" / "em-x" / "includes").mkdir(parents=True)
    (sibling / "node_modules" / "lib").mkdir(parents=True)
    return root, sibling


def _exclude(ls: Intelephense) -> list[str]:
    config = ls._create_workspace_configuration()
    return config["files"]["exclude"]


def test_workspace_configuration_excludes_ignored_dirs_of_every_folder(tmp_path: Path, repos: tuple[Path, Path]) -> None:
    root, _ = repos
    ls = _create_ls(tmp_path, root, {}, ignored_paths=["/build", "/../site/public_html"], additional=["../site"])
    exclude = _exclude(ls)
    # defaults are kept (a configured exclude list replaces intelephense's defaults)
    for pattern in DEFAULT_INTELEPHENSE_EXCLUDE:
        assert pattern in exclude
    assert "build/**" in exclude  # ignored via project ignore pattern (primary folder)
    assert "public_html/**" in exclude  # ignored via project ignore pattern (sibling folder)
    assert "wp-content/plugins/em-x/vendor/**" in exclude  # vendor dir (ignore_vendor default)
    assert "node_modules/**" in exclude
    assert not any(p.startswith("src") or "includes" in p for p in exclude)


def test_vendor_is_indexed_when_ignore_vendor_is_disabled(tmp_path: Path, repos: tuple[Path, Path]) -> None:
    root, _ = repos
    ls = _create_ls(tmp_path, root, {"ignore_vendor": False}, ignored_paths=[], additional=["../site"])
    assert "wp-content/plugins/em-x/vendor/**" not in _exclude(ls)


def test_max_file_size_is_passed_via_workspace_configuration(tmp_path: Path, repos: tuple[Path, Path]) -> None:
    root, _ = repos
    ls = _create_ls(tmp_path, root, {"maxFileSize": 500000}, ignored_paths=[], additional=[])
    assert ls._create_workspace_configuration()["files"]["maxSize"] == 500000


def test_workspace_configuration_capability_is_advertised(tmp_path: Path, repos: tuple[Path, Path]) -> None:
    root, _ = repos
    ls = _create_ls(tmp_path, root, {}, ignored_paths=[], additional=[])
    params = ls._create_initialize_params()
    assert params["capabilities"]["workspace"]["configuration"] is True


def test_max_memory_sets_node_heap_limit(tmp_path: Path) -> None:
    lib = tmp_path / "node_modules" / "intelephense" / "lib"
    lib.mkdir(parents=True)
    (lib / "intelephense.js").write_text("")
    bin_dir = tmp_path / "node_modules" / ".bin"
    bin_dir.mkdir()
    os.symlink("../intelephense/lib/intelephense.js", bin_dir / "intelephense")
    core_path = str(bin_dir / "intelephense")

    with_limit = Intelephense.DependencyProvider(SolidLSPSettings.CustomLSSettings({"maxMemory": 1024}), str(tmp_path))
    cmd = with_limit._create_launch_command(core_path)
    assert cmd[1:] == ["--max-old-space-size=1024", str((lib / "intelephense.js").resolve()), "--stdio"]
    assert os.path.basename(cmd[0]).startswith("node")

    without_limit = Intelephense.DependencyProvider(SolidLSPSettings.CustomLSSettings({}), str(tmp_path))
    assert without_limit._create_launch_command(core_path) == [core_path, "--stdio"]
