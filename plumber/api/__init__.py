"""
Plumber Python API for external scripts and addons.

This module provides a clean Python API for accessing Plumber's Source engine
import functionality from external scripts and addons.

Main components:
- Games: Access game definitions from Plumber preferences
- GameFileSystem: Interface for browsing and reading game files
- Import functions: Import individual assets or batches of assets
- ParallelImportBuilder: Build custom parallel import processes
"""

from .games import Games, Game
from .filesystem import GameFileSystem, FileBrowserEntry
from .importer import (
    import_vmf,
    import_mdl,
    import_vmt,
    import_vtf,
    ParallelImportBuilder,
)
from .exceptions import (
    PlumberAPIError,
    GameNotFoundError,
    FileSystemError,
    AssetImportError,
)

__all__ = [
    # Games and file systems
    "Games",
    "Game",
    "GameFileSystem",
    "FileBrowserEntry",
    # Import functions
    "import_vmf",
    "import_mdl",
    "import_vmt",
    "import_vtf",
    "ParallelImportBuilder",
    # Exceptions
    "PlumberAPIError",
    "GameNotFoundError",
    "FileSystemError",
    "AssetImportError",
]
