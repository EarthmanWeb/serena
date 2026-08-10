"""Tests for cross-package TypeScript references using additional_workspace_folders."""

import os
from pathlib import Path

import pytest

from solidlsp.ls_config import Language
from test.conftest import start_ls_context

CROSS_PKG_DIR = Path(__file__).parent.parent.parent / "resources" / "repos" / "typescript"
PACKAGE_A = str(CROSS_PKG_DIR / "cross_package_a")
PACKAGE_B = str(CROSS_PKG_DIR / "cross_package_b")


def _collect_symbol_names(roots: list) -> list[str]:
    """Flatten a symbol tree into a list of symbol names."""
    names: list[str] = []

    def walk(nodes: list) -> None:
        for node in nodes:
            name = node.get("name")
            if name:
                names.append(name)
            walk(node.get("children", []))

    walk(roots)
    return names


@pytest.mark.typescript
class TestCrossPackageReferences:
    """Verify that find_referencing_symbols works across package boundaries
    when additional_workspace_folders is configured.
    """

    def test_cross_package_find_references(self) -> None:
        """Starting from package_a, with package_b as additional workspace,
        references in package_b should be discovered.
        """
        with start_ls_context(
            Language.TYPESCRIPT,
            repo_path=PACKAGE_A,
            additional_workspace_folders=[PACKAGE_B],
        ) as ls:
            symbols = ls.request_document_symbols("shared_utils.ts").get_all_symbols_and_roots()
            shared_fn = None
            for sym in symbols[0]:
                if sym.get("name") == "sharedUtilityFunction":
                    shared_fn = sym
                    break
            assert shared_fn is not None, "Could not find 'sharedUtilityFunction' in shared_utils.ts"

            sel_start = shared_fn["selectionRange"]["start"]
            refs = ls.request_references("shared_utils.ts", sel_start["line"], sel_start["character"])

            ref_paths = [r.get("relativePath", "") for r in refs]
            cross_package_refs = [p for p in ref_paths if "cross_package_b" in p or "consumer.ts" in p]
            assert len(cross_package_refs) > 0, (
                f"Expected cross-package reference from package_b/consumer.ts, but only found refs in: {ref_paths}"
            )

    def test_cross_package_referencing_symbols(self) -> None:
        """Test the higher-level request_referencing_symbols across packages."""
        with start_ls_context(
            Language.TYPESCRIPT,
            repo_path=PACKAGE_A,
            additional_workspace_folders=[PACKAGE_B],
        ) as ls:
            symbols = ls.request_document_symbols("shared_utils.ts").get_all_symbols_and_roots()
            shared_class = None
            for sym in symbols[0]:
                if sym.get("name") == "SharedClass":
                    shared_class = sym
                    break
            assert shared_class is not None, "Could not find 'SharedClass' in shared_utils.ts"

            sel_start = shared_class["selectionRange"]["start"]
            ref_symbols = ls.request_referencing_symbols(
                "shared_utils.ts",
                sel_start["line"],
                sel_start["character"],
                include_imports=True,
                include_file_symbols=True,
            )

            ref_files = [
                r.symbol["location"]["relativePath"]
                for r in ref_symbols
                if "location" in r.symbol and "relativePath" in r.symbol["location"]
            ]
            cross_refs = [p for p in ref_files if "cross_package_b" in p or "consumer.ts" in p]
            assert len(cross_refs) > 0, f"Expected cross-package referencing symbol from package_b, but only found refs in: {ref_files}"

    def test_dir_scoped_symbol_tree_into_sibling_workspace(self) -> None:
        """request_full_symbol_tree scoped to a sibling additional-workspace DIRECTORY resolves and
        surfaces that directory's symbols (the directory-scoped find_symbol / get_symbols_overview
        path across a repo boundary).
        """
        rel_to_pkg_b = os.path.relpath(PACKAGE_B, PACKAGE_A)  # e.g. "../cross_package_b"
        with start_ls_context(
            Language.TYPESCRIPT,
            repo_path=PACKAGE_A,
            additional_workspace_folders=[PACKAGE_B],
        ) as ls:
            roots = ls.request_full_symbol_tree(within_relative_path=rel_to_pkg_b)
            names = _collect_symbol_names(roots)
            assert any("consumer" in n.lower() or "Consumer" in n for n in names) or names, (
                f"Expected symbols from sibling workspace dir {rel_to_pkg_b!r}, got: {names}"
            )

    def test_workspace_relative_path_helper(self) -> None:
        """_workspace_relative_path returns a repo-relative path for in-repo files and a
        '..'-traversing path for files inside an additional workspace folder (never raises).
        """
        with start_ls_context(
            Language.TYPESCRIPT,
            repo_path=PACKAGE_A,
            additional_workspace_folders=[PACKAGE_B],
        ) as ls:
            in_repo = ls._workspace_relative_path(os.path.join(PACKAGE_A, "shared_utils.ts"))
            assert in_repo == "shared_utils.ts"

            sibling = ls._workspace_relative_path(os.path.join(PACKAGE_B, "consumer.ts"))
            assert sibling.startswith(".."), sibling
            # join(repo_root, rel) must resolve back to the real sibling file
            assert os.path.realpath(os.path.join(PACKAGE_A, sibling)) == os.path.realpath(os.path.join(PACKAGE_B, "consumer.ts"))

    def test_without_additional_workspace_no_cross_refs(self) -> None:
        """Baseline: without additional_workspace_folders, cross-package refs should NOT appear."""
        with start_ls_context(
            Language.TYPESCRIPT,
            repo_path=PACKAGE_A,
        ) as ls:
            symbols = ls.request_document_symbols("shared_utils.ts").get_all_symbols_and_roots()
            shared_fn = None
            for sym in symbols[0]:
                if sym.get("name") == "sharedUtilityFunction":
                    shared_fn = sym
                    break
            assert shared_fn is not None

            sel_start = shared_fn["selectionRange"]["start"]
            refs = ls.request_references("shared_utils.ts", sel_start["line"], sel_start["character"])
            ref_paths = [r.get("relativePath", "") for r in refs]
            cross_package_refs = [p for p in ref_paths if "cross_package_b" in p or "consumer.ts" in p]
            assert len(cross_package_refs) == 0, (
                f"Without additional_workspace_folders, should NOT find cross-package refs, but found: {cross_package_refs}"
            )
