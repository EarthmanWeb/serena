import logging
import os.path
import threading
from collections.abc import Iterator

from sensai.util.logging import LogTime

from serena.config.serena_config import ProjectConfig, SerenaPaths
from solidlsp import SolidLanguageServer
from solidlsp.ls_config import Language, LanguageServerConfig
from solidlsp.settings import SolidLSPSettings

log = logging.getLogger(__name__)


class LanguageServerManagerInitialisationError(Exception):
    def __init__(self, message: str):
        super().__init__(message)


class LanguageServerFactory:
    def __init__(
        self,
        project_root: str,
        project_config: ProjectConfig,
        project_data_path: str,
        encoding: str,
        ignored_patterns: list[str],
        ls_timeout: float | None = None,
        ls_specific_settings: dict | None = None,
        trace_lsp_communication: bool = False,
        ignore_all_dot_files: bool = True,
    ):
        self.project_root = project_root
        self.project_config = project_config
        self.project_data_path = project_data_path
        self.encoding = encoding
        self.ignored_patterns = ignored_patterns
        self.ls_timeout = ls_timeout
        self.ls_specific_settings = ls_specific_settings
        self.trace_lsp_communication = trace_lsp_communication
        self.ignore_all_dot_files = ignore_all_dot_files

    def create_language_server(self, language: Language) -> SolidLanguageServer:
        ls_config = LanguageServerConfig(
            workspace_folders=self.project_config.ls_workspace_folders,
            additional_workspace_folders=self.project_config.ls_additional_workspace_folders,
            code_language=language,
            ignored_paths=self.ignored_patterns,
            trace_lsp_communication=self.trace_lsp_communication,
            encoding=self.encoding,
            ignore_all_dot_files=self.ignore_all_dot_files,
        )

        log.info(f"Creating language server instance for {self.project_root}, language={language}.")
        return SolidLanguageServer.create(
            ls_config,
            self.project_root,
            timeout=self.ls_timeout,
            solidlsp_settings=SolidLSPSettings(
                solidlsp_dir=SerenaPaths().serena_user_home_dir,
                project_data_path=self.project_data_path,
                ls_specific_settings=self.ls_specific_settings or {},
            ),
        )


class LanguageServerManager:
    """
    Manages the language servers for a project.

    Language servers are started lazily: a server is only created and started when a tool first requires
    the respective language (e.g. a symbol operation on a file of that language). Merely activating a project
    (and using non-symbolic tools such as the memory tools) thus never spawns a language server process nor
    loads its (potentially large) symbol caches.
    """

    def __init__(self, languages: list[Language], language_server_factory: LanguageServerFactory) -> None:
        """
        :param languages: the languages to manage; the first language's server is the default server, which is used
            for files that no language claims
        :param language_server_factory: the factory with which language servers are created (on demand)
        """
        if len(languages) == 0:
            raise ValueError("No languages given; at least one language is required")
        self._languages = list(languages)
        self._language_server_factory = language_server_factory
        self._language_servers: dict[Language, SolidLanguageServer] = {}
        self._start_locks: dict[Language, threading.Lock] = {language: threading.Lock() for language in self._languages}
        self._start_locks_lock = threading.Lock()

    def _get_start_lock(self, language: Language) -> threading.Lock:
        with self._start_locks_lock:
            return self._start_locks.setdefault(language, threading.Lock())

    def _get_or_start_language_server(self, language: Language) -> SolidLanguageServer:
        """
        Returns the running language server for the given language, creating and starting it if necessary
        (also if a previously started server is no longer running).
        Concurrent calls for the same language result in a single startup.
        """
        with self._get_start_lock(language):
            ls = self._language_servers.get(language)
            if ls is not None and ls.is_running():
                return ls
            if ls is not None:
                log.warning(f"Language server for language {language.value} is not running; restarting ...")
            with LogTime(f"Language server startup (language={language.value})"):
                ls = self._language_server_factory.create_language_server(language)
                ls.start()
            if not ls.is_running():
                raise RuntimeError(f"Failed to start the language server for language {language.value}")
            self._language_servers[language] = ls
            return ls

    def _start_language_servers_in_parallel(self, languages: list[Language]) -> None:
        """
        Ensures that the language servers for the given languages are running, starting missing ones in parallel.

        :raises LanguageServerManagerInitialisationError: if any of the servers could not be started
        """
        exceptions: dict[Language, Exception] = {}

        def start(language: Language) -> None:
            try:
                self._get_or_start_language_server(language)
            except Exception as e:
                log.error(f"Error starting language server for language {language.value}: {e}", exc_info=e)
                exceptions[language] = e

        threads = [threading.Thread(target=start, args=(language,), name="StartLS:" + language.value) for language in languages]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join()
        if exceptions:
            raise LanguageServerManagerInitialisationError(
                "Language servers failed to start:\n" + "\n".join([f"{lang.value}: {e}" for lang, e in exceptions.items()])
            )

    def _get_suitable_language(self, relative_path: str) -> Language | None:
        """:param relative_path: relative path to a file"""
        for language in self._languages:
            if language.get_source_fn_matcher().is_relevant_filename(relative_path):
                return language
        return None

    def get_language_server(self, relative_path: str) -> SolidLanguageServer:
        """Routes a file to the appropriate language server based on file extension, starting the server if necessary.

        When multiple languages are configured, finds the first one whose language supports the given file's extension.
        Falls back to the default (first) language if no match is found.
        """
        language: Language | None = None
        if len(self._languages) > 1:
            if os.path.isdir(relative_path):
                raise ValueError(f"Expected a file path, but got a directory: {relative_path}")
            language = self._get_suitable_language(relative_path)
        if language is None:
            language = self._languages[0]
        return self._get_or_start_language_server(language)

    def restart_language_server(self, language: Language) -> SolidLanguageServer:
        """
        Forces recreation and restart of the language server for the given language.
        It is assumed that the language server for the given language is no longer running.

        :param language: the language
        :return: the newly created language server
        """
        if language not in self._languages:
            raise ValueError(f"No language server for language {language.value} present; cannot restart")
        with self._get_start_lock(language):
            self._language_servers.pop(language, None)
        return self._get_or_start_language_server(language)

    def add_language(self, language: Language) -> None:
        """
        Adds the given language to the managed languages; its language server is started on first use.

        :param language: the language
        """
        if language in self._languages:
            raise ValueError(f"Language {language.value} already present")
        self._languages.append(language)

    def remove_language(self, language: Language, save_cache: bool = False) -> None:
        """
        Removes the given language, stopping its language server if it was started.

        :param language: the language
        """
        if language not in self._languages:
            raise ValueError(f"Language {language.value} not present; cannot remove")
        self._languages.remove(language)
        with self._get_start_lock(language):
            ls = self._language_servers.pop(language, None)
        if ls is not None:
            self._stop_language_server(ls, save_cache=save_cache)

    def get_active_languages(self) -> list[Language]:
        """
        Returns the list of languages managed by this manager (whose language servers may or may not have been started yet).

        :return: list of languages
        """
        return list(self._languages)

    def get_started_languages(self) -> list[Language]:
        """
        :return: the list of languages whose language servers have been started
        """
        return [language for language in self._languages if language in self._language_servers]

    @staticmethod
    def _stop_language_server(ls: SolidLanguageServer, save_cache: bool = False, timeout: float = 2.0) -> None:
        if ls.is_running():
            if save_cache:
                ls.save_cache()
            log.info(f"Stopping language server for language {ls.language} ...")
            ls.stop(shutdown_timeout=timeout)

    def iter_language_servers(self) -> Iterator[SolidLanguageServer]:
        """
        Iterates over the language servers of all managed languages, starting (in parallel) those not yet running.
        """
        self._start_language_servers_in_parallel(list(self._languages))
        for language in self._languages:
            yield self._get_or_start_language_server(language)

    def _iter_started_language_servers(self) -> list[SolidLanguageServer]:
        return list(self._language_servers.values())

    def stop_all(self, save_cache: bool = False, timeout: float = 2.0) -> None:
        """
        Stops all started language servers (servers that were never started are not started).

        :param save_cache: whether to save the cache before stopping
        :param timeout: timeout for shutdown of each language server
        """
        for ls in self._iter_started_language_servers():
            self._stop_language_server(ls, save_cache=save_cache, timeout=timeout)
        self._language_servers.clear()

    def save_all_caches(self) -> None:
        """
        Saves the caches of all started and running language servers.
        """
        for ls in self._iter_started_language_servers():
            if ls.is_running():
                ls.save_cache()

    def has_suitable_ls_for_file(self, relative_file_path: str) -> bool:
        return self._get_suitable_language(relative_file_path) is not None
