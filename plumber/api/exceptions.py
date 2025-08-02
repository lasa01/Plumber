"""
Custom exceptions for the Plumber API.
"""


class PlumberAPIError(Exception):
    """Base exception for all Plumber API errors."""

    pass


class GameNotFoundError(PlumberAPIError):
    """Raised when a requested game is not found in preferences."""

    pass


class FileSystemError(PlumberAPIError):
    """Raised when there's an error accessing the game file system."""

    pass


class AssetImportError(PlumberAPIError):
    """Raised when there's an error during asset import."""

    pass
