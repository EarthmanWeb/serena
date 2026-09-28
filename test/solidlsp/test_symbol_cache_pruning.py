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


def test_persisted_document_symbols_exclude_links_into_the_full_symbol_tree() -> None:
    """
    Evidence: request_full_symbol_tree sets ``parent`` of each file's root symbols to a File symbol, whose Package
    parents link the whole tree (including other files' symbols and their full source lines). Pickling any single
    cached DocumentSymbols entry of the convenely php cache produced ~165 MB (the whole graph, including superseded
    versions of files), so the persisted cache retained everything ever linked. The persisted state keeps the
    document's own symbol hierarchy only.
    """
    import pickle

    child = {"name": "method", "kind": 6, "children": []}
    root = {"name": "Cls", "kind": 5, "children": [child]}
    child["parent"] = root
    big_other_file = {"name": "other", "kind": 1, "children": [], "payload": "x" * 1_000_000}
    package = {"name": "pkg", "kind": 4, "children": [big_other_file]}
    file_symbol = {"name": "file", "kind": 1, "children": [root], "parent": package}
    root["parent"] = file_symbol

    data = pickle.dumps(DocumentSymbols([root]))  # type: ignore[list-item]
    assert len(data) < 10_000

    restored: DocumentSymbols = pickle.loads(data)
    restored_root = restored.root_symbols[0]
    assert "parent" not in restored_root
    restored_child = restored_root["children"][0]
    assert restored_child["parent"] is restored_root
    # the in-memory instance is left untouched
    assert root["parent"] is file_symbol
