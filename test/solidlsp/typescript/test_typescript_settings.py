"""
TypeScript resource settings (no language server process is started).

typescript-language-server (5.1.3) reads the tsserver heap limit (MB) from the top-level initialization option
``maxTsServerMemory``; it is exposed as ``ls_specific_settings.typescript.maxTsServerMemory``.
"""

from pathlib import Path

from solidlsp.language_servers.typescript_language_server import TypeScriptLanguageServer
from solidlsp.ls_config import Language, LanguageServerConfig
from solidlsp.settings import SolidLSPSettings


def _create_ls(tmp_path: Path, ts_settings: dict) -> TypeScriptLanguageServer:
    root = tmp_path / "repo"
    root.mkdir()
    settings = SolidLSPSettings(
        solidlsp_dir=str(tmp_path / "solidlsp"),
        project_data_path=str(tmp_path / "data"),
        ls_specific_settings={Language.TYPESCRIPT: ts_settings},
    )
    return TypeScriptLanguageServer(LanguageServerConfig(code_language=Language.TYPESCRIPT), str(root), settings)


def test_max_ts_server_memory_is_passed_as_initialization_option(tmp_path: Path) -> None:
    ls = _create_ls(tmp_path, {"maxTsServerMemory": 1024})
    assert ls._create_initialize_params()["initializationOptions"]["maxTsServerMemory"] == 1024


def test_max_ts_server_memory_is_omitted_by_default(tmp_path: Path) -> None:
    ls = _create_ls(tmp_path, {})
    assert "maxTsServerMemory" not in ls._create_initialize_params()["initializationOptions"]
