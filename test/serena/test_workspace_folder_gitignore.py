"""
The .gitignore files of additional (sibling) workspace folders must be honoured just like the project's own.

Evidence (convenely project): the symbol caches contained 1510 markdown and 182 TypeScript entries from
gitignored ``vendor/`` dirs of the sibling plugin repo, because only the project root's .gitignore files
were parsed.
"""

from pathlib import Path

import pytest

from serena.config.serena_config import ProjectConfig, SerenaConfig
from serena.project import Project
from solidlsp.ls_config import Language


@pytest.fixture()
def multi_repo(tmp_path: Path) -> tuple[Project, Path]:
    base_repo = tmp_path / "base_repo"
    (base_repo / "src").mkdir(parents=True)
    (base_repo / "src" / "own.md").write_text("# own\n")
    (base_repo / ".gitignore").write_text("/local-only/\n")

    plugin_repo = tmp_path / "plugin_repo"
    (plugin_repo / "em-a" / "vendor" / "lib").mkdir(parents=True)
    (plugin_repo / "em-a" / "vendor" / "lib" / "README.md").write_text("# vendored\n")
    (plugin_repo / "em-a" / "docs").mkdir(parents=True)
    (plugin_repo / "em-a" / "docs" / "guide.md").write_text("# guide\n")
    (plugin_repo / "public_html" / "wp-includes").mkdir(parents=True)
    (plugin_repo / "public_html" / "wp-includes" / "x.md").write_text("# core\n")
    (plugin_repo / "public_html" / "keep").mkdir(parents=True)
    (plugin_repo / "public_html" / "keep" / "k.md").write_text("# keep\n")
    (plugin_repo / ".gitignore").write_text("vendor/\n/public_html/*\n!/public_html/keep/\n")
    (plugin_repo / "em-a" / ".gitignore").write_text("/docs/\n")

    project = Project(
        project_root=str(base_repo),
        project_config=ProjectConfig(
            project_name="test-sibling-gitignore",
            languages=[Language.MARKDOWN],
            ls_additional_workspace_folders=["../plugin_repo"],
            ignore_all_files_in_gitignore=True,
        ),
        serena_config=SerenaConfig(gui_log_window=False, web_dashboard=False, trusted_project_path_patterns=["**"]),
    )
    return project, base_repo


def test_sibling_gitignore_patterns_are_honoured(multi_repo: tuple[Project, Path]) -> None:
    project, _ = multi_repo
    assert project.is_ignored_path("../plugin_repo/em-a/vendor/lib/README.md")
    assert project.is_ignored_path("../plugin_repo/em-a/vendor")
    assert project.is_ignored_path("../plugin_repo/em-a/docs/guide.md")  # nested, anchored .gitignore
    assert project.is_ignored_path("../plugin_repo/public_html/wp-includes/x.md")
    assert not project.is_ignored_path("../plugin_repo/public_html/keep/k.md")  # negation


def test_sibling_patterns_do_not_leak_into_project_root(multi_repo: tuple[Project, Path]) -> None:
    project, base_repo = multi_repo
    (base_repo / "public_html").mkdir()
    (base_repo / "public_html" / "a.md").write_text("# a\n")
    assert not project.is_ignored_path("public_html/a.md")
    assert not project.is_ignored_path("src/own.md")
