from .plumber import discover_filesystems, FileSystem, filesystem_from_gameinfo

from typing import List, Set, Tuple
from os.path import isdir
import os

from bpy.types import (
    Context,
    Operator,
    PropertyGroup,
    UILayout,
    UIList,
    AddonPreferences,
)
from bpy.props import (
    CollectionProperty,
    EnumProperty,
    IntProperty,
    StringProperty,
    BoolProperty,
)
import bpy


class GameSearchPath(PropertyGroup):
    def get_path(self) -> str:
        return self.get("path", "")

    def set_path(self, value: str) -> None:
        value = bpy.path.abspath(value)
        self["path"] = value
        if isdir(value) and self.kind != "WILDCARD":
            self.kind = "DIR"
        elif value.lower().endswith(".vpk"):
            self.kind = "VPK"

    path: StringProperty(
        subtype="FILE_PATH",
        default="",
        get=get_path,
        set=set_path,
    )

    kind: EnumProperty(
        items=(
            ("DIR", "Directory", "", "FILE_FOLDER", 0),
            ("VPK", "VPK Archive", "", "PACKAGE", 1),
            ("WILDCARD", "Wildcard Directory", "", "FOLDER_REDIRECT", 2),
        ),
        name="Type",
    )


class GameSearchPathList(UIList):
    bl_idname = "PLUMBER_UL_game_search_path_list"

    def draw_item(
        self,
        context: Context,
        layout: UILayout,
        data: "Game",
        item: GameSearchPath,
        icon: int,
        active_data: int,
        active_propname: str,
    ) -> None:
        if self.layout_type in {"DEFAULT", "COMPACT"}:
            layout.prop(item, "kind", icon_only=True, emboss=False, icon_value=icon)
            layout.prop(item, "path", icon_only=True, emboss=False)
        elif self.layout_type in {"GRID"}:
            layout.alignment = "CENTER"
            layout.label(text=item.path, icon_value=icon)


class AddGameSearchPathOperator(Operator):
    """Add a new empty game search path to the selected game"""

    bl_idname = "plumber.game_search_path_add"
    bl_label = "Add a game search path"
    bl_options = {"REGISTER"}

    @classmethod
    def poll(cls, context: Context) -> bool:
        return bool(context.preferences.addons[__package__].preferences.games)

    def execute(self, context: Context) -> Set[str]:
        preferences: AddonPreferences = context.preferences.addons[
            __package__
        ].preferences
        game: Game = preferences.games[preferences.game_index]
        game.search_paths.add()
        game.search_path_index = len(game.search_paths) - 1
        return {"FINISHED"}


class RemoveGameSearchPathOperator(Operator):
    """Remove the selected game search path from the selected game"""

    bl_idname = "plumber.game_search_path_remove"
    bl_label = "Remove a game search path"
    bl_options = {"REGISTER"}

    @classmethod
    def poll(cls, context: Context) -> bool:
        preferences: AddonPreferences = context.preferences.addons[
            __package__
        ].preferences
        return bool(preferences.games) and bool(
            preferences.games[preferences.game_index].search_paths
        )

    def execute(self, context: Context) -> Set[str]:
        preferences: AddonPreferences = context.preferences.addons[
            __package__
        ].preferences
        game: Game = preferences.games[preferences.game_index]
        game.search_paths.remove(game.search_path_index)
        game.search_path_index = min(
            max(0, game.search_path_index - 1), len(game.search_paths) - 1
        )
        return {"FINISHED"}


class MoveGameSearchPathOperator(Operator):
    """Move the selected game search path"""

    bl_idname = "plumber.game_search_path_move"
    bl_label = "Move a game search path"
    bl_options = {"REGISTER"}

    direction: EnumProperty(items=(("UP", "Up", ""), ("DOWN", "Down", "")))

    @classmethod
    def poll(cls, context: Context) -> bool:
        preferences: AddonPreferences = context.preferences.addons[
            __package__
        ].preferences
        return bool(preferences.games) and bool(
            preferences.games[preferences.game_index].search_paths
        )

    def execute(self, context: Context) -> Set[str]:
        preferences: AddonPreferences = context.preferences.addons[
            __package__
        ].preferences
        game: Game = preferences.games[preferences.game_index]

        list_len = len(game.search_paths) - 1
        index = game.search_path_index
        new_index = index + (-1 if self.direction == "UP" else 1)

        game.search_paths.move(new_index, index)
        game.search_path_index = max(0, min(new_index, list_len))

        return {"FINISHED"}


class Game(PropertyGroup):
    def get_name(self) -> str:
        return self.get("name", "")

    def set_name(self, value: str) -> None:
        preferences: "AddonPreferences" = bpy.context.preferences.addons[
            __package__
        ].preferences
        for game in preferences.games:
            if game == self:
                continue
            if game.name == value:
                number = 1
                while any(
                    game.name == f"{value} {number}" for game in preferences.games
                ):
                    number += 1
                value = f"{value} {number}"
                break
        self["name"] = value

    def get_file_system(self) -> FileSystem:
        return FileSystem(
            self.name, [(path.kind, path.path) for path in self.search_paths]
        )

    name: StringProperty(
        name="Name",
        default="New Source Game",
        get=get_name,
        set=set_name,
    )

    search_paths: CollectionProperty(type=GameSearchPath)
    search_path_index: IntProperty(name="Search Path")


class GameList(UIList):
    bl_idname = "PLUMBER_UL_game_list"

    def draw_item(
        self,
        context: Context,
        layout: UILayout,
        data: "AddonPreferences",
        item: Game,
        icon: int,
        active_data: int,
        active_propname: str,
    ) -> None:
        if self.layout_type in {"DEFAULT", "COMPACT"}:
            layout.prop(item, "name", text="", emboss=False, icon_value=icon)
        elif self.layout_type in {"GRID"}:
            layout.alignment = "CENTER"
            layout.label(text=item.name, icon_value=icon)


class AddGameOperator(Operator):
    """Add a new empty game definition"""

    bl_idname = "plumber.game_add"
    bl_label = "Add an empty game definition"
    bl_options = {"REGISTER"}

    def execute(self, context: Context) -> Set[str]:
        preferences: AddonPreferences = context.preferences.addons[
            __package__
        ].preferences
        game: Game = preferences.games.add()
        game.name = "New Source Game"
        preferences.game_index = len(preferences.games) - 1
        return {"FINISHED"}


class RemoveGameOperator(Operator):
    """Remove the selected game definition"""

    bl_idname = "plumber.game_remove"
    bl_label = "Remove a game definition"
    bl_options = {"REGISTER"}

    @classmethod
    def poll(cls, context: Context) -> bool:
        return bool(context.preferences.addons[__package__].preferences.games)

    def execute(self, context: Context) -> Set[str]:
        preferences: AddonPreferences = context.preferences.addons[
            __package__
        ].preferences
        preferences.games.remove(preferences.game_index)
        preferences.game_index = min(
            max(0, preferences.game_index - 1), len(preferences.games) - 1
        )
        return {"FINISHED"}


class MoveGameOperator(Operator):
    """Move the selected game definition"""

    bl_idname = "plumber.game_move"
    bl_label = "Move a game definition"
    bl_options = {"REGISTER"}

    direction: EnumProperty(items=(("UP", "Up", ""), ("DOWN", "Down", "")))

    @classmethod
    def poll(cls, context: Context) -> bool:
        return bool(context.preferences.addons[__package__].preferences.games)

    def execute(self, context: Context) -> Set[str]:
        preferences: AddonPreferences = context.preferences.addons[
            __package__
        ].preferences

        list_len = len(preferences.games) - 1
        index = preferences.game_index
        new_index = index + (-1 if self.direction == "UP" else 1)

        preferences.games.move(new_index, index)
        preferences.game_index = max(0, min(new_index, list_len))

        return {"FINISHED"}


class DetectGamesOperator(Operator):
    """Automatically detects installed Source games"""

    bl_idname = "plumber.detect_games"
    bl_label = "Automatically detects installed Source games"
    bl_options = {"REGISTER"}

    def execute(self, context: Context) -> Set[str]:
        err = detect_games(context)
        if err is not None:
            self.report({"ERROR"}, f"could not detect installed games: {err}")

        return {"FINISHED"}


def detect_games(context: Context):
    preferences: AddonPreferences = context.preferences.addons[__package__].preferences

    filesystems = discover_filesystems()

    for filesystem in filesystems:
        name = filesystem.name()
        if any(name == game.name for game in preferences.games):
            continue
        search_paths = filesystem.search_paths()
        game: Game = preferences.games.add()
        game.name = name
        for (kind, path) in search_paths:
            search_path: GameSearchPath = game.search_paths.add()
            search_path.path = path
            search_path.kind = kind


class DetectGameinfoOperator(Operator):
    """Detect an installed Source game from gameinfo.txt"""

    bl_idname = "plumber.detect_gameinfo"
    bl_label = """Detect an installed Source game from gameinfo.txt"""
    bl_options = {"REGISTER"}

    filepath: StringProperty(
        name="Path",
        maxlen=1024,
        options={"HIDDEN"},
    )

    filename_ext = ".txt"

    filter_glob: StringProperty(
        default="*.txt",
        options={"HIDDEN"},
        maxlen=255,
    )

    def invoke(self, context: Context, event) -> Set[str]:
        context.window_manager.fileselect_add(self)
        return {"RUNNING_MODAL"}

    def execute(self, context: Context) -> Set[str]:
        try:
            detect_gameinfo(self.filepath, context)
        except (ValueError, OSError) as err:
            self.report({"ERROR"}, f"could not detect gameinfo.txt: {err}")

        return {"FINISHED"}


def detect_gameinfo(path: str, context: Context):
    preferences: AddonPreferences = context.preferences.addons[__package__].preferences

    filesystem = filesystem_from_gameinfo(path)

    name = filesystem.name()
    search_paths = filesystem.search_paths()
    game: Game = preferences.games.add()
    game.name = name
    for (kind, path) in search_paths:
        search_path: GameSearchPath = game.search_paths.add()
        search_path.path = path
        search_path.kind = kind


class AddonPreferences(AddonPreferences):
    bl_idname = __package__

    games: CollectionProperty(type=Game)
    game_index: IntProperty(name="Game definition")

    threads: IntProperty(
        name="Importer threads",
        description="Total amount of threads to use for importing, the default value is generally the best choice",
        min=0,
        max=64,
        soft_min=1,
        soft_max=os.cpu_count(),
    )

    def update_enable_file_browser_panel(self, context: Context):
        from plumber.tools import GameFileBrowserPanel

        if not self.enable_file_browser_panel:
            bpy.utils.unregister_class(GameFileBrowserPanel)
        else:
            bpy.utils.register_class(GameFileBrowserPanel)

    enable_file_browser_panel: BoolProperty(
        name="Enable file browser panel",
        description="Enable the game file browser panel in 3D view sidebar",
        default=True,
        update=update_enable_file_browser_panel,
    )

    @staticmethod
    def game_enum_items(
        self: EnumProperty, context: Context
    ) -> List[Tuple[str, str, str]]:
        if context is None:
            context = bpy.context
        preferences: AddonPreferences = context.preferences.addons[
            __package__
        ].preferences
        items = [
            (str(i), game.name, "") for i, game in enumerate(preferences.games.values())
        ]
        items.append(("NONE", "None", ""))
        return items

    def draw(self, context: Context) -> None:
        layout: UILayout = self.layout
        layout.prop(self, "enable_file_browser_panel")
        layout.prop(self, "threads")

        layout.separator()
        row = layout.row()
        row.operator(
            DetectGamesOperator.bl_idname,
            text="Redetect installed games",
        )
        row.operator(
            DetectGameinfoOperator.bl_idname,
            text="Detect from gameinfo.txt",
        )

        layout.label(text="Game Definitions:")
        row = layout.row()
        row.template_list(GameList.bl_idname, "", self, "games", self, "game_index")
        col = row.column()
        col.operator(AddGameOperator.bl_idname, text="", icon="ADD")
        col.operator(RemoveGameOperator.bl_idname, text="", icon="REMOVE")
        col.operator(
            MoveGameOperator.bl_idname, text="", icon="TRIA_UP"
        ).direction = "UP"
        col.operator(
            MoveGameOperator.bl_idname, text="", icon="TRIA_DOWN"
        ).direction = "DOWN"
        if self.games:
            game = self.games[self.game_index]
            layout.label(text="Search Paths:")
            row = layout.row()
            row.template_list(
                GameSearchPathList.bl_idname,
                "",
                game,
                "search_paths",
                game,
                "search_path_index",
            )

            col = row.column()
            col.operator(AddGameSearchPathOperator.bl_idname, text="", icon="ADD")
            col.operator(RemoveGameSearchPathOperator.bl_idname, text="", icon="REMOVE")
            col.operator(
                MoveGameSearchPathOperator.bl_idname, text="", icon="TRIA_UP"
            ).direction = "UP"
            col.operator(
                MoveGameSearchPathOperator.bl_idname, text="", icon="TRIA_DOWN"
            ).direction = "DOWN"


class OpenPreferencesOperator(Operator):
    """Open the preferences of the VMF importer"""

    bl_idname = "plumber.open_preferences"
    bl_label = "Open Plumber preferences"
    bl_options = {"INTERNAL"}

    def execute(self, context: Context) -> Set[str]:
        bpy.ops.preferences.addon_show("INVOKE_SCREEN", module=__package__)
        return {"FINISHED"}


classes = (
    GameSearchPath,
    GameSearchPathList,
    AddGameSearchPathOperator,
    RemoveGameSearchPathOperator,
    MoveGameSearchPathOperator,
    Game,
    GameList,
    AddGameOperator,
    RemoveGameOperator,
    MoveGameOperator,
    DetectGamesOperator,
    DetectGameinfoOperator,
    AddonPreferences,
    OpenPreferencesOperator,
)


def register():
    for cls in classes:
        bpy.utils.register_class(cls)

    preferences: AddonPreferences = bpy.context.preferences.addons[
        __package__
    ].preferences

    if preferences.threads == 0:
        preferences.threads = max(2, os.cpu_count() or 0)

    if not preferences.games:
        detect_games(bpy.context)


def unregister():
    for cls in reversed(classes):
        bpy.utils.unregister_class(cls)
