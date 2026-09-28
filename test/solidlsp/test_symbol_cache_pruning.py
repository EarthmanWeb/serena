"""
Symbol caches must not grow unboundedly.

Evidence (convenely project, 2026-09-28): entries are never evicted, so the on-disk caches, which are fully loaded
into the Serena process when a language server starts, accumulated stale entries: php 2147 of 3333 entries
for files that no longer exist; typescript 131 missing + 170 ignored + 20 outside all workspace folders of 698;
markdown 177 missing + 1343 ignored (vendor/) of 1599. Stale entries are pruned when the server is started.
"""

from pathlib import Path

from solidlsp.language_servers.typescript_language_server import TypeScriptLanguageServer
from solidlsp.ls import DocumentSymbols
from solidlsp.ls_config import Language, LanguageServerConfig
from solidlsp.settings import SolidLSPSettings


def test_stale_symbol_cache_entries_are_pruned(tmp_path: Path) -> None:
    root = tmp_path / "repo"
    (root / "src").mkdir(parents=True)
    (root / "src" / "live.ts").write_text("export const a = 1;\n")
    (root / "gen").mkdir()
    (root / "gen" / "ignored.ts").write_text("export const b = 1;\n")
    sibling = tmp_path / "sibling"
    sibling.mkdir()
    (sibling / "s.ts").write_text("export const s = 1;\n")
    removed_sibling = tmp_path / "removed_sibling"
    removed_sibling.mkdir()
    (removed_sibling / "r.ts").write_text("export const r = 1;\n")

    ls = TypeScriptLanguageServer(
        LanguageServerConfig(code_language=Language.TYPESCRIPT, ignored_paths=["/gen"], additional_workspace_folders=["../sibling"]),
        str(root),
        SolidLSPSettings(solidlsp_dir=str(tmp_path / "solidlsp"), project_data_path=str(tmp_path / "data")),
    )
    keys = ["src/live.ts", "src/deleted.ts", "gen/ignored.ts", "../sibling/s.ts", "../removed_sibling/r.ts"]
    for key in keys:
        ls._raw_document_symbols_cache[key] = ("hash", [])
        ls._document_symbols_cache[key] = ("hash", DocumentSymbols([]))

    ls._prune_symbol_caches()

    assert sorted(ls._raw_document_symbols_cache) == ["../sibling/s.ts", "src/live.ts"]
    assert sorted(ls._document_symbols_cache) == ["../sibling/s.ts", "src/live.ts"]
    assert ls._raw_document_symbols_cache_is_modified
    assert ls._document_symbols_cache_is_modified


def test_pruning_without_stale_entries_does_not_mark_caches_modified(tmp_path: Path) -> None:
    root = tmp_path / "repo"
    (root / "src").mkdir(parents=True)
    (root / "src" / "live.ts").write_text("export const a = 1;\n")
    ls = TypeScriptLanguageServer(
        LanguageServerConfig(code_language=Language.TYPESCRIPT),
        str(root),
        SolidLSPSettings(solidlsp_dir=str(tmp_path / "solidlsp"), project_data_path=str(tmp_path / "data")),
    )
    ls._raw_document_symbols_cache["src/live.ts"] = ("hash", [])
    ls._document_symbols_cache["src/live.ts"] = ("hash", DocumentSymbols([]))
    ls._prune_symbol_caches()
    assert not ls._raw_document_symbols_cache_is_modified
    assert not ls._document_symbols_cache_is_modified
