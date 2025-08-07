"""
Game definitions and access to Plumber preferences.
"""

from typing import List, Tuple

from .exceptions import GameNotFoundError
from .filesystem import GameFileSystem


class Game:
    """
    Wrapper for a game definition from Plumber preferences.

    Provides read-only access to game name and file system configuration.
    """

    def __init__(self, name: str, search_paths: List[Tuple[str, str]]):
        """
        Initialize a Game instance.

        Args:
            name: Name of the game
            search_paths: List of (kind, path) tuples for search paths
        """
        self._name = name
        self._search_paths = search_paths

    @property
    def name(self) -> str:
        """Get the game name."""
        return self._name

    @property
    def search_paths(self) -> List[Tuple[str, str]]:
        """Get the game's search paths as (kind, path) tuples."""
        return self._search_paths.copy()

    def get_file_system(self) -> GameFileSystem:
        """
        Create a GameFileSystem for this game.

        Returns:
            GameFileSystem instance for browsing and reading game files
        """
        return GameFileSystem.from_search_paths(self._name, self._search_paths)

    def __repr__(self) -> str:
        return f"Game(name='{self._name}', search_paths={len(self._search_paths)})"


class Games:
    """
    Access to game definitions from Plumber preferences.

    Provides read-only access to configured games.
    """

    @staticmethod
    def get_all() -> List[Game]:
        """
        Get all configured games from Plumber preferences.

        Returns:
            List of Game instances

        Raises:
            RuntimeError: If Plumber addon is not loaded or preferences not accessible
        """
        try:
            import bpy
            from .. import __package__ as ADDON_NAME

            preferences = bpy.context.preferences.addons[ADDON_NAME].preferences

            games = []
            for game in preferences.games:
                search_paths = [(path.kind, path.path) for path in game.search_paths]
                games.append(Game(game.name, search_paths))

            return games
        except (KeyError, AttributeError) as e:
            raise RuntimeError(
                "Unable to access Plumber preferences. Is the addon loaded?"
            ) from e

    @staticmethod
    def find_by_name(name: str) -> Game:
        """
        Find a game by name.

        Args:
            name: Name of the game to find

        Returns:
            Game instance

        Raises:
            GameNotFoundError: If no game with the given name is found
        """
        games = Games.get_all()
        for game in games:
            if game.name == name:
                return game

        raise GameNotFoundError(f"No game found with name '{name}'")

    @staticmethod
    def find_by_pattern(pattern: str) -> List[Game]:
        """
        Find games with names matching a pattern (case-insensitive).

        Args:
            pattern: Pattern to match against game names

        Returns:
            List of matching Game instances
        """
        games = Games.get_all()
        pattern_lower = pattern.lower()

        return [game for game in games if pattern_lower in game.name.lower()]
