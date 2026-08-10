"""Tests for cross-repo (sibling workspace folder) relative-path resolution on Project.

These are pure-Python unit tests: no language server is started. They cover the path-resolution
layer that lets bare, plugin-rooted paths resolve into a configured additional workspace folder
(multi-repo layout), and that the project-membership guard accepts such paths.
"""

from pathlib import Path

import pytest

from serena.config.serena_config import ProjectConfig, SerenaConfig
from serena.project import Project
from solidlsp.ls_config import Language


def _make_project(project_root: Path, additional_workspace_folders: list[str]) -> Project:
    serena_config = SerenaConfig(
        gui_log_window=False,
        web_dashboard=False,
        trusted_project_path_patterns=["**"],
    )
    project_config = ProjectConfig(
        project_name="test-workspace-resolution",
        languages=[Language.PYTHON],
        ls_additional_workspace_folders=list(additional_workspace_folders),
    )
    return Project(
        project_root=str(project_root),
        project_config=project_config,
        serena_config=serena_config,
    )


@pytest.fixture()
def multi_repo(tmp_path: Path):
    """Lay out a base repo plus a sibling repo, mirroring the convenely multi-repo layout.

    base_repo/               <- project root
    plugin_repo/             <- additional workspace folder ("../plugin_repo")
        em-training/includes/rest/class-rest-base.php
    """
    base_repo = tmp_path / "base_repo"
    base_repo.mkdir()
    (base_repo / "src").mkdir()
    (base_repo / "src" / "own.py").write_text("x = 1\n")

    plugin_repo = tmp_path / "plugin_repo"
    target = plugin_repo / "em-training" / "includes" / "rest"
    target.mkdir(parents=True)
    (target / "class-rest-base.php").write_text("<?php\nabstract class EMTR_REST_Base {}\n")
    # a source file in the project's language (Python) so source-file gathering picks it up
    (plugin_repo / "em-training" / "helper.py").write_text("def helper():\n    return 1\n")

    project = _make_project(base_repo, additional_workspace_folders=["../plugin_repo"])
    return project, base_repo, plugin_repo


class TestResolveRelativePath:
    def test_bare_plugin_rooted_path_resolves_into_sibling(self, multi_repo) -> None:
        """A bare path that exists only in a sibling workspace folder resolves to the
        '..'-traversing path, with zero prefix required from the caller.
        """
        project, base_repo, plugin_repo = multi_repo
        resolved = project.resolve_relative_path("em-training/includes/rest/class-rest-base.php")
        assert resolved.startswith(".."), resolved
        assert (base_repo / resolved).resolve() == (
            plugin_repo / "em-training" / "includes" / "rest" / "class-rest-base.php"
        ).resolve()

    def test_bare_plugin_dir_resolves_into_sibling(self, multi_repo) -> None:
        """Directory-scoped bare paths resolve too (dir-scoped find_symbol / search)."""
        project, base_repo, plugin_repo = multi_repo
        resolved = project.resolve_relative_path("em-training/includes/rest")
        assert (base_repo / resolved).resolve() == (plugin_repo / "em-training" / "includes" / "rest").resolve()

    def test_in_project_path_is_returned_unchanged(self, multi_repo) -> None:
        project, _base_repo, _plugin_repo = multi_repo
        assert project.resolve_relative_path("src/own.py") == "src/own.py"

    def test_absolute_path_is_returned_unchanged(self, multi_repo) -> None:
        project, _base_repo, plugin_repo = multi_repo
        abs_path = str(plugin_repo / "em-training")
        assert project.resolve_relative_path(abs_path) == abs_path

    def test_nonexistent_path_is_returned_unchanged(self, multi_repo) -> None:
        """Unknown paths pass through so the caller raises the normal FileNotFoundError."""
        project, _base_repo, _plugin_repo = multi_repo
        assert project.resolve_relative_path("does/not/exist.php") == "does/not/exist.php"

    def test_ambiguous_path_raises(self, tmp_path: Path) -> None:
        """A relative path present in two workspace folders is ambiguous and must raise."""
        base_repo = tmp_path / "base"
        base_repo.mkdir()
        for name in ("repo_a", "repo_b"):
            d = tmp_path / name / "shared" / "thing"
            d.mkdir(parents=True)
            (d / "file.php").write_text("<?php\n")
        project = _make_project(base_repo, additional_workspace_folders=["../repo_a", "../repo_b"])
        with pytest.raises(ValueError, match="Ambiguous"):
            project.resolve_relative_path("shared/thing/file.php")


class TestIsPathInProject:
    def test_sibling_workspace_path_is_in_project(self, multi_repo) -> None:
        """A '..'-traversing path into a configured workspace folder counts as in-project,
        so search_for_pattern / file-collection tools accept it.
        """
        project, _base_repo, _plugin_repo = multi_repo
        assert project.is_path_in_project("../plugin_repo/em-training/includes/rest/class-rest-base.php")

    def test_own_path_is_in_project(self, multi_repo) -> None:
        project, _base_repo, _plugin_repo = multi_repo
        assert project.is_path_in_project("src/own.py")

    def test_unconfigured_sibling_is_not_in_project(self, multi_repo) -> None:
        """A '..' path that escapes into a folder NOT configured as a workspace is rejected."""
        project, _base_repo, _plugin_repo = multi_repo
        assert not project.is_path_in_project("../some_other_repo/secret.php")


class TestIsIgnoredPathSibling:
    """is_ignored_path must NOT auto-ignore a file merely because its absolute path is outside the
    project root: files inside a configured sibling workspace folder are searchable. Without this,
    search_for_pattern / file-gathering silently returns nothing for sibling directories.
    """

    def test_absolute_sibling_file_not_ignored(self, multi_repo) -> None:
        project, _base_repo, plugin_repo = multi_repo
        abs_file = str(plugin_repo / "em-training" / "helper.py")
        assert not project.is_ignored_path(abs_file)

    def test_absolute_path_outside_all_workspaces_is_ignored(self, multi_repo, tmp_path) -> None:
        project, _base_repo, _plugin_repo = multi_repo
        outside = str(tmp_path / "not_a_workspace" / "file.py")
        assert project.is_ignored_path(outside)

    def test_gather_source_files_includes_sibling(self, multi_repo) -> None:
        """The source-file walk (used by search_for_pattern) collects files under a sibling dir."""
        project, _base_repo, _plugin_repo = multi_repo
        collected = project.gather_source_files("../plugin_repo/em-training")
        assert any(p.endswith("helper.py") for p in collected), collected
