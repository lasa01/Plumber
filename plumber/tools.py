from typing import Collection, Optional, Set

from bpy.types import Operator, Context, UIList, UILayout, PropertyGroup, Menu, Panel
from bpy.props import (
    BoolProperty,
    StringProperty,
    IntProperty,
    EnumProperty,
    CollectionProperty,
    PointerProperty,
)
import bpy

from .plumber import FileBrowser
from .preferences import Game, AddonPreferences


class ObjectTransform3DSky(Operator):
    """Transform the selected 3D sky objects, based on the active empty object"""

    bl_idname = "object.plumber_transform_3d_sky"
    bl_label = "Transform VMF 3D sky"
    bl_options = {"REGISTER", "UNDO"}

    @classmethod
    def poll(cls, context: Context) -> bool:
        return (
            context.active_object and context.active_object.type == "EMPTY"
        ) and context.selected_objects

    def execute(self, context: Context) -> Set[str]:
        target = context.active_object
        for obj in context.selected_objects:
            if obj != target and obj.parent is None:
                obj.parent = target
                obj.location -= target.location
        target.location = (0, 0, 0)
        return {"FINISHED"}


def object_menu_func(self: bpy.types.Menu, context: bpy.types.Context) -> None:
    self.layout.separator()
    self.layout.operator(ObjectTransform3DSky.bl_idname)


FILE_IMPORTERS = {
    "mdl": "import_scene.plumber_mdl",
    "vmt": "import_scene.plumber_vmt",
    "vmf": "import_scene.plumber_vmf",
}


def get_extension(filename: str) -> str:
    parts = filename.rsplit(".", 1)
    if len(parts) < 2:
        return ""
    else:
        return parts[1]


class DirEntry(PropertyGroup):
    name: StringProperty(subtype="FILE_NAME")
    path: StringProperty()
    kind: EnumProperty(
        items=(
            ("DIR", "Directory", "", "FILE_FOLDER", 0),
            ("FILE", "File", "", "FILE", 1),
        ),
        name="Type",
    )

    def navigate(self, operator: "GameFileBrowserOperator") -> bool:
        if self.kind == "DIR":
            if operator.path:
                operator.path += f"/{self.name}"
            else:
                operator.path = self.name
        else:
            return False
        return True


class DirEntryList(UIList):
    bl_idname = "PLUMBER_UL_dir_entry_list"

    use_filter_supported: BoolProperty(
        name="Filter supported",
        default=True,
        options=set(),
        description="Whether to only show files that can be imported",
    )

    def draw_item(
        self,
        context: Context,
        layout: UILayout,
        data: "GameFileBrowser",
        item: DirEntry,
        icon: int,
        active_data: int,
        active_propname: str,
        index: int,
    ) -> None:
        icon_value = layout.enum_item_icon(item, "kind", item.kind)

        if self.layout_type in {"DEFAULT", "COMPACT"}:
            layout.label(
                text=item.name,
                icon_value=icon_value,
            )

            if index == getattr(active_data, active_propname) and item.kind == "FILE":
                extension = get_extension(item.name)
                importer = FILE_IMPORTERS.get(extension)

                if importer is not None:
                    operator = layout.operator(importer, text="Import")
                    operator.from_game_fs = True
                    operator.filepath = item.path
                    operator.game = str(data.game_id)

        elif self.layout_type in {"GRID"}:
            layout.alignment = "CENTER"
            layout.label(text=item.name, icon_value=icon_value)

    def draw_filter(self, context: Context, layout: UILayout):
        layout.prop(self, "use_filter_supported")

    def filter_items(self, context: Context, data: "GameFileBrowser", property: str):
        entries: Collection[DirEntry] = getattr(data, property)

        flt_flags = []
        flt_neworder = []

        if self.use_filter_supported:
            flt_flags = [
                self.bitflag_filter_item
                if entry.kind != "FILE" or get_extension(entry.name) in FILE_IMPORTERS
                else 0
                for entry in entries
            ]

        return flt_flags, flt_neworder


class GameFileBrowser:
    browser: Optional[FileBrowser] = None
    path: str

    def __init_subclass__(cls) -> None:
        # unfortunately the self passed to property updates
        # is not a proper class instance of operators,
        # so we need to make update_path browser reading
        # not dependent on self

        def update_path(self: GameFileBrowser, context: Context):
            entries = cls.browser.read_dir(self.path)
            self.entries.clear()

            for entry in entries:
                bl_entry: DirEntry = self.entries.add()
                bl_entry.name = entry.name()
                bl_entry.kind = entry.kind()
                bl_entry.path = f"{self.path}/{bl_entry.name}"

            self.entry_index = -1

        cls.update_path = update_path
        cls.__annotations__["path"] = StringProperty(name="Path", update=update_path)

    game_id: IntProperty(default=-1)

    entries: CollectionProperty(type=DirEntry)

    def update_entry_index(self, context: Context):
        if self.entry_index != -1:
            entry: DirEntry = self.entries[self.entry_index]
            if entry.navigate(self):
                self.entry_index = -1

    entry_index: IntProperty(
        default=-1,
        name="Directory entry",
        update=update_entry_index,
    )

    def update_browse_parent(self, context: Context):
        if self.browse_parent:
            path = self.path
            parts = path.rsplit("/", 1)
            if len(parts) < 2:
                self.path = ""
            else:
                self.path = parts[0]

            self.browse_parent = False

    browse_parent: BoolProperty(
        default=False,
        name="Parent",
        update=update_browse_parent,
    )

    def open_game(self, context: Context):
        preferences: AddonPreferences = context.preferences.addons[
            __package__
        ].preferences

        game: Game = preferences.games[self.game_id]
        type(self).browser = game.get_file_system().browse()

        self.update_path(context)

    def draw_browser(self, layout: UILayout):
        layout.label(text="Files:")
        row = layout.row()

        button_layout = row.column()
        button_layout.enabled = bool(self.path)
        button_layout.prop(self, "browse_parent", icon="FILE_PARENT", icon_only=True)

        row.prop(self, "path", text="")

        layout.template_list(
            DirEntryList.bl_idname,
            "",
            self,
            "entries",
            self,
            "entry_index",
            maxrows=20,
        )

        if self.entry_index == -1:
            layout.label(text="(select a file to import)")
        else:
            layout.label(text="")


class GameFileBrowserPropertyGroup(PropertyGroup, GameFileBrowser):
    def update_game(self, context: Context):
        if self.game == "NONE":
            GameFileBrowserPropertyGroup.browser = None
        else:
            self.initialize(context)

    game: EnumProperty(
        items=AddonPreferences.game_enum_items,
        name="Game",
        description="Used for opening required assets",
        options={"HIDDEN"},
        update=update_game,
    )

    def initialize(self, context: Context):
        if self.game == "NONE":
            return
        else:
            self.game_id = int(self.game)
            self.open_game(context)

    def draw_browser(self, layout: UILayout):
        layout.prop(self, "game")

        if self.game == "NONE":
            return

        if GameFileBrowserPropertyGroup.browser is None:
            layout.operator(OpenGameFileBrowser.bl_idname)
            return

        super().draw_browser(layout)


class GameFileBrowserPanel(Panel):
    bl_idname = "VIEW3D_PT_plumber_browser"
    bl_category = "Plumber"
    bl_label = "Game file browser"
    bl_space_type = "VIEW_3D"
    bl_region_type = "UI"

    browser: GameFileBrowserPropertyGroup = None

    def draw(self, context: Context):
        if GameFileBrowserPanel.browser != context.scene.plumber_browser:
            # if scene changed, delete the previous browser
            GameFileBrowserPanel.browser = context.scene.plumber_browser
            GameFileBrowserPropertyGroup.browser = None

        GameFileBrowserPanel.browser.draw_browser(self.layout)


class OpenGameFileBrowser(Operator):
    """Open the game file browser"""

    bl_idname = "view3d.plumber_open_file_browser"
    bl_label = "Open"
    bl_options = {"INTERNAL"}

    def execute(self, context: Context) -> Set[str]:
        GameFileBrowserPanel.browser.initialize(context)
        return {"FINISHED"}


class GameFileBrowserOperator(Operator, GameFileBrowser):
    """Browse the files of the selected game"""

    bl_idname = "import_scene.plumber_file_browser"
    bl_label = "Browse game files"
    bl_options = {"INTERNAL"}

    def invoke(self, context: Context, event) -> Set[str]:
        if self.game_id == -1:
            return {"CANCELLED"}

        self.open_game(context)

        return context.window_manager.invoke_props_dialog(self)

    def draw(self, context: Context):
        self.draw_browser(self.layout)

    def execute(self, context: Context) -> Set[str]:
        return {"CANCELLED"}


class IMPORT_MT_plumber_browse(Menu):
    bl_idname = "IMPORT_MT_plumber_browse"
    bl_label = "Browse game files"

    def draw(self, context: Context):
        preferences: AddonPreferences = context.preferences.addons[
            __package__
        ].preferences

        for i, game in enumerate(preferences.games):
            self.layout.operator(
                GameFileBrowserOperator.bl_idname,
                text=game.name,
            ).game_id = i


classes = [
    ObjectTransform3DSky,
    DirEntry,
    DirEntryList,
    GameFileBrowserPropertyGroup,
    OpenGameFileBrowser,
    GameFileBrowserOperator,
    IMPORT_MT_plumber_browse,
]


def register():
    for cls in classes:
        bpy.utils.register_class(cls)

    bpy.types.VIEW3D_MT_object.append(object_menu_func)

    bpy.types.Scene.plumber_browser = PointerProperty(
        type=GameFileBrowserPropertyGroup, options={"SKIP_SAVE"}
    )

    preferences: AddonPreferences = bpy.context.preferences.addons[
        __package__
    ].preferences

    if preferences.enable_file_browser_panel:
        bpy.utils.register_class(GameFileBrowserPanel)


def unregister():
    preferences: AddonPreferences = bpy.context.preferences.addons[
        __package__
    ].preferences

    if preferences.enable_file_browser_panel:
        bpy.utils.unregister_class(GameFileBrowserPanel)

    del bpy.types.Scene.plumber_browser

    bpy.types.VIEW3D_MT_object.remove(object_menu_func)

    for cls in reversed(classes):
        bpy.utils.unregister_class(cls)
