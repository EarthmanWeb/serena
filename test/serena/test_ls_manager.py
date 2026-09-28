"""
Tests for the lazy language server startup of :class:`LanguageServerManager`.

Language servers must only be started when a tool first needs the respective language;
constructing the manager (project activation) must not start any server.
"""

import threading
import time
from typing import cast

import pytest

from serena.ls_manager import LanguageServerFactory, LanguageServerManager, LanguageServerManagerInitialisationError
from solidlsp import SolidLanguageServer
from solidlsp.ls_config import Language


class FakeLanguageServer:
    def __init__(self, language: Language, start_delay: float = 0.0, fail: bool = False):
        self.language = language
        self._start_delay = start_delay
        self._fail = fail
        self._running = False
        self.start_count = 0
        self.stop_count = 0
        self.save_cache_count = 0

    def start(self) -> None:
        self.start_count += 1
        time.sleep(self._start_delay)
        if self._fail:
            raise RuntimeError(f"cannot start {self.language.value}")
        self._running = True

    def is_running(self) -> bool:
        return self._running

    def stop(self, shutdown_timeout: float = 2.0) -> None:
        self.stop_count += 1
        self._running = False

    def save_cache(self) -> None:
        self.save_cache_count += 1


class FakeFactory:
    def __init__(self, start_delay: float = 0.0, failing: set[Language] | None = None):
        self.created: list[FakeLanguageServer] = []
        self._start_delay = start_delay
        self._failing = failing or set()
        self._lock = threading.Lock()

    def create_language_server(self, language: Language) -> SolidLanguageServer:
        ls = FakeLanguageServer(language, start_delay=self._start_delay, fail=language in self._failing)
        with self._lock:
            self.created.append(ls)
        return cast(SolidLanguageServer, ls)

    def created_languages(self) -> list[Language]:
        return [ls.language for ls in self.created]


LANGUAGES = [Language.MARKDOWN, Language.TYPESCRIPT, Language.PHP, Language.PYTHON]


def create_manager(factory: FakeFactory, languages: list[Language] | None = None) -> LanguageServerManager:
    return LanguageServerManager(list(languages or LANGUAGES), cast(LanguageServerFactory, factory))


def test_construction_starts_no_language_server() -> None:
    factory = FakeFactory()
    manager = create_manager(factory)
    assert factory.created == []
    assert manager.get_started_languages() == []
    assert manager.get_active_languages() == LANGUAGES


def test_file_access_starts_only_the_matching_language_server() -> None:
    factory = FakeFactory()
    manager = create_manager(factory)
    ls = manager.get_language_server("src/foo.php")
    assert ls.language == Language.PHP
    assert factory.created_languages() == [Language.PHP]
    # second access reuses the running server
    assert manager.get_language_server("src/bar.php") is ls
    assert factory.created_languages() == [Language.PHP]
    assert manager.get_started_languages() == [Language.PHP]


def test_suitability_check_does_not_start_servers() -> None:
    factory = FakeFactory()
    manager = create_manager(factory)
    assert manager.has_suitable_ls_for_file("a.ts")
    assert not manager.has_suitable_ls_for_file("a.rb")
    assert factory.created == []


def test_save_and_stop_do_not_start_servers() -> None:
    factory = FakeFactory()
    manager = create_manager(factory)
    manager.save_all_caches()
    manager.stop_all(save_cache=True)
    assert factory.created == []


def test_stop_all_stops_started_servers_without_restarting_dead_ones() -> None:
    factory = FakeFactory()
    manager = create_manager(factory)
    php = cast(FakeLanguageServer, manager.get_language_server("a.php"))
    ts = cast(FakeLanguageServer, manager.get_language_server("a.ts"))
    ts.stop()  # simulate a crashed server
    manager.stop_all(save_cache=True)
    assert php.stop_count == 1
    assert php.save_cache_count == 1
    assert factory.created_languages() == [Language.PHP, Language.TYPESCRIPT]


def test_iter_language_servers_starts_all_configured_languages_in_parallel() -> None:
    factory = FakeFactory(start_delay=0.3)
    manager = create_manager(factory)
    t0 = time.monotonic()
    servers = list(manager.iter_language_servers())
    elapsed = time.monotonic() - t0
    assert [ls.language for ls in servers] == LANGUAGES
    assert elapsed < 0.9, "servers must be started in parallel"


def test_concurrent_access_starts_a_language_server_only_once() -> None:
    factory = FakeFactory(start_delay=0.2)
    manager = create_manager(factory)
    results: list[SolidLanguageServer] = []
    threads = [threading.Thread(target=lambda: results.append(manager.get_language_server("x.py"))) for _ in range(5)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert factory.created_languages() == [Language.PYTHON]
    assert len(results) == 5
    assert all(r is results[0] for r in results)


def test_start_failure_raises() -> None:
    factory = FakeFactory(failing={Language.PHP})
    manager = create_manager(factory)
    with pytest.raises(RuntimeError, match="cannot start php"):
        manager.get_language_server("a.php")
    with pytest.raises(LanguageServerManagerInitialisationError, match="php"):
        list(manager.iter_language_servers())


def test_dead_server_is_restarted_on_access() -> None:
    factory = FakeFactory()
    manager = create_manager(factory)
    first = cast(FakeLanguageServer, manager.get_language_server("a.php"))
    first.stop()
    second = manager.get_language_server("a.php")
    assert second is not first
    assert second.is_running()


def test_add_and_remove_language_are_lazy() -> None:
    factory = FakeFactory()
    manager = create_manager(factory, [Language.PYTHON])
    manager.add_language(Language.PHP)
    assert factory.created == []
    assert manager.get_active_languages() == [Language.PYTHON, Language.PHP]
    php = cast(FakeLanguageServer, manager.get_language_server("a.php"))
    manager.remove_language(Language.PHP)
    assert php.stop_count == 1
    assert manager.get_active_languages() == [Language.PYTHON]
