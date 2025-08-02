"""
Game file system interface for browsing and reading files.
"""

from typing import List, Tuple, Optional, Union
import io

from .exceptions import FileSystemError


class FileBrowserEntry:
    """
    Represents a file or directory entry in the game file system.
    """

    def __init__(self, name: str, path: str, kind: str):
        """
        Initialize a FileBrowserEntry.

        Args:
            name: Name of the file/directory
            path: Full path in the game file system
            kind: Type of entry ('file' or 'directory')
        """
        self._name = name
        self._path = path
        self._kind = kind

    @property
    def name(self) -> str:
        """Get the entry name."""
        return self._name

    @property
    def path(self) -> str:
        """Get the full path."""
        return self._path

    @property
    def kind(self) -> str:
        """Get the entry type ('file' or 'directory')."""
        return self._kind

    @property
    def is_file(self) -> bool:
        """Check if this entry is a file."""
        return self._kind == "file"

    @property
    def is_directory(self) -> bool:
        """Check if this entry is a directory."""
        return self._kind == "directory"

    def __repr__(self) -> str:
        return f"FileBrowserEntry(name='{self._name}', kind='{self._kind}')"


class GameFileSystem:
    """
    Interface for browsing and reading files from a game file system.
    """

    def __init__(self, fs_internal):
        self._fs = fs_internal
        self._browser = None

    @classmethod
    def from_search_paths(
        cls, name: str, search_paths: List[Tuple[str, str]]
    ) -> "GameFileSystem":
        """
        Create a GameFileSystem from search paths.

        Args:
            name: Name for the file system
            search_paths: List of (kind, path) tuples

        Returns:
            GameFileSystem instance

        Raises:
            FileSystemError: If file system creation fails
        """
        try:
            from ..plumber import FileSystem

            fs_internal = FileSystem(name, search_paths)
            return cls(fs_internal)
        except Exception as e:
            raise FileSystemError(f"Failed to create file system: {e}") from e

    @classmethod
    def empty(cls) -> "GameFileSystem":
        """
        Create an empty game file system for cases where no game files are needed.

        Returns:
            Empty GameFileSystem instance
        """
        try:
            from ..plumber import FileSystem

            fs_internal = FileSystem.empty()
            return cls(fs_internal)
        except Exception as e:
            raise FileSystemError(f"Failed to create empty file system: {e}") from e

    @classmethod
    def from_gameinfo(cls, gameinfo_path: str) -> "GameFileSystem":
        """
        Create a GameFileSystem from a gameinfo.txt file.

        Args:
            gameinfo_path: Path to gameinfo.txt file

        Returns:
            GameFileSystem instance

        Raises:
            FileSystemError: If file system creation fails
        """
        try:
            from ..plumber import filesystem_from_gameinfo

            fs_internal = filesystem_from_gameinfo(gameinfo_path)
            return cls(fs_internal)
        except Exception as e:
            raise FileSystemError(
                f"Failed to create file system from gameinfo: {e}"
            ) from e

    @property
    def name(self) -> str:
        """Get the file system name."""
        return self._fs.name()

    @property
    def search_paths(self) -> List[Tuple[str, str]]:
        """Get the search paths as (kind, path) tuples."""
        return self._fs.search_paths()

    def browse_directory(self, directory: str = "") -> List[FileBrowserEntry]:
        """
        Browse a directory in the game file system.

        Args:
            directory: Directory path to browse (empty for root)

        Returns:
            List of FileBrowserEntry objects

        Raises:
            FileSystemError: If directory browsing fails
        """
        try:
            if self._browser is None:
                self._browser = self._fs.browse()

            entries_internal = self._browser.read_dir(directory)
            entries = []

            for entry in entries_internal:
                entries.append(
                    FileBrowserEntry(entry.name(), entry.path(), entry.kind())
                )

            return entries
        except Exception as e:
            raise FileSystemError(
                f"Failed to browse directory '{directory}': {e}"
            ) from e

    def read_file_text(self, filepath: str) -> str:
        """
        Read a file as text from the game file system.

        Args:
            filepath: Path to the file to read

        Returns:
            File contents as string

        Raises:
            FileSystemError: If file reading fails
        """
        try:
            return self._fs.read_file_text(filepath)
        except Exception as e:
            raise FileSystemError(f"Failed to read file '{filepath}': {e}") from e

    def read_file_bytes(self, filepath: str) -> bytes:
        """
        Read a file as bytes from the game file system.

        Args:
            filepath: Path to the file to read

        Returns:
            File contents as bytes

        Raises:
            FileSystemError: If file reading fails
        """
        try:
            return self._fs.read_file_bytes(filepath)
        except Exception as e:
            raise FileSystemError(f"Failed to read file '{filepath}': {e}") from e

    def file_exists(self, filepath: str) -> bool:
        """
        Check if a file exists in the game file system.

        Args:
            filepath: Path to check

        Returns:
            True if file exists, False otherwise
        """
        try:
            return self._fs.file_exists(filepath)
        except FileSystemError:
            return False

    def __repr__(self) -> str:
        return (
            f"GameFileSystem(name='{self.name}', search_paths={len(self.search_paths)})"
        )
