from typing import Set, List
from os.path import basename, dirname
import os

import bpy
from bpy.props import EnumProperty, BoolProperty, StringProperty, CollectionProperty
from bpy.types import Context, Operator, Panel, UILayout, PropertyGroup

from ..plumber import FileSystem
from ..preferences import AddonPreferences

from .. import __package__ as ADDON_NAME


class SelectedFile(PropertyGroup):
    """Property group for selected files in batch import"""

    name: StringProperty(name="File Name")


class ImporterOperatorProps:
    game: EnumProperty(
        items=AddonPreferences.game_enum_items,
        name="Game",
        description="Used for opening required assets",
        options={"HIDDEN"},
    )

    filepath: StringProperty(
        name="Path",
        maxlen=1024,
        subtype="FILE_PATH",
        options={"HIDDEN"},
    )

    directory: StringProperty(
        name="Directory",
        maxlen=1024,
        subtype="DIR_PATH",
        options={"HIDDEN"},
    )

    files: CollectionProperty(
        type=SelectedFile,
        options={"HIDDEN"},
    )


class ImporterOperator(Operator, ImporterOperatorProps):
    def get_game_fs(self, context: Context):
        if self.game == "NONE":
            return FileSystem.empty()
        else:
            preferences = context.preferences.addons[ADDON_NAME].preferences
            game = preferences.games[int(self.game)]
            return game.get_file_system()

    def get_threads_suggestion(self, context: Context) -> int:
        preferences = context.preferences.addons[ADDON_NAME].preferences
        # leave room for blender's thread
        return preferences.threads - 1

    def get_target_fps(self, context: Context) -> float:
        scene = context.scene
        return scene.render.fps / scene.render.fps_base

    def is_batch_import(self) -> bool:
        """Check if this is a batch import (multiple files selected)"""
        return len(self.files) > 0

    def get_file_paths(self) -> List[str]:
        """Get list of file paths to import"""
        if self.is_batch_import():
            return [os.path.join(self.directory, file.name) for file in self.files]
        else:
            return [self.filepath]

    def invoke(self, context: Context, event) -> Set[str]:
        context.window_manager.fileselect_add(self)
        return {"RUNNING_MODAL"}

    def draw(self, context: Context):
        pass


def update_recent_entries(context: Context, game: str, path: str):
    if game == "NONE":
        return

    recent_entries = context.scene.plumber_recent_entries.get(game)

    if recent_entries is None:
        recent_entries = context.scene.plumber_recent_entries.add()
        recent_entries.name = game

    for recent_entry in recent_entries.recent_entries:
        if recent_entry.path == path:
            return

    add_recent_entry(path, recent_entries.recent_entries)

    scene_browser = context.scene.plumber_browser
    if scene_browser.game == game:
        add_recent_entry(path, scene_browser.recent_entries_temp)

    if update_recent_entries.browser_operator_entries is not None:
        add_recent_entry(path, update_recent_entries.browser_operator_entries)


update_recent_entries.browser_operator_entries = None


def add_recent_entry(path: str, recent_entries):
    while len(recent_entries) >= 10:
        recent_entries.remove(0)

    recent_entry = recent_entries.add()
    recent_entry.name = basename(path)
    recent_entry.path = path


class GameFileImporterOperatorProps:
    from_game_fs: BoolProperty(options={"HIDDEN"})


class GameFileImporterOperator(
    ImporterOperator, ImporterOperatorProps, GameFileImporterOperatorProps
):
    def invoke(self, context: Context, event) -> Set[str]:
        if self.from_game_fs:
            update_recent_entries(context, self.game, dirname(self.filepath))
            return context.window_manager.invoke_props_dialog(self)
        else:
            context.window_manager.fileselect_add(self)
            return {"RUNNING_MODAL"}


class DisableCommonPanel:
    pass


class PLUMBER_PT_importer_common(Panel):
    bl_space_type = "FILE_BROWSER"
    bl_region_type = "TOOL_PROPS"
    bl_label = ""
    bl_parent_id = "FILE_PT_operator"
    bl_options = {"HIDE_HEADER"}

    @classmethod
    def poll(cls, context: Context) -> bool:
        operator = context.space_data.active_operator
        return isinstance(operator, ImporterOperatorProps) and not isinstance(
            operator, DisableCommonPanel
        )

    def draw(self, context: Context) -> None:
        layout: UILayout = self.layout
        layout.use_property_split = True
        layout.use_property_decorate = False
        operator = context.space_data.active_operator
        layout.prop(operator, "game")


class MaterialImporterOperatorProps:
    simple_materials: BoolProperty(
        name="Simple materials",
        description="Import simple, exporter-friendly versions of materials",
        default=False,
    )

    texture_format: EnumProperty(
        name="Texture format",
        description="Format to use for imported image textures",
        items=[
            ("Tga", "TGA", "Truevision TGA"),
            ("Png", "PNG", "Portable Network Graphigs"),
        ],
        default="Png",
    )

    texture_interpolation: EnumProperty(
        name="Texture interpolation",
        description="Interpolation type to use for image textures",
        items=[
            ("Linear", "Linear", "Linear interpolation"),
            ("Closest", "Closest", "No interpolation"),
            ("Cubic", "Cubic", "Cubic interpolation"),
            ("Smart", "Smart", "Bicubic when magnifying, else bilinear"),
        ],
        default="Linear",
    )

    allow_culling: BoolProperty(
        name="Allow backface culling",
        description="Enable backface culling for materials which don't disable it",
        default=False,
    )

    editor_materials: BoolProperty(
        name="Import editor materials",
        description="Import materials visible inside Hammer instead of invisible materials",
        default=False,
    )

    @staticmethod
    def draw_props(
        layout: UILayout, operator: "MaterialImporterOperatorProps", context: Context
    ):
        layout.use_property_split = True
        layout.prop(operator, "simple_materials")
        layout.prop(operator, "texture_format")
        layout.prop(operator, "texture_interpolation")
        layout.prop(operator, "allow_culling")
        layout.prop(operator, "editor_materials")


class MaterialToggleOperatorProps(MaterialImporterOperatorProps):
    import_materials: BoolProperty(
        name="Import materials",
        default=True,
    )

    @staticmethod
    def draw_props(
        layout: UILayout, operator: "MaterialToggleOperatorProps", context: Context
    ):
        layout.prop(operator, "import_materials")
        box = layout.box()
        box.enabled = operator.import_materials
        MaterialImporterOperatorProps.draw_props(box, operator, context)


class PLUMBER_PT_importer_materials(Panel):
    bl_space_type = "FILE_BROWSER"
    bl_region_type = "TOOL_PROPS"
    bl_label = "Materials"
    bl_parent_id = "FILE_PT_operator"
    bl_options = {"DEFAULT_CLOSED"}

    @classmethod
    def poll(cls, context: Context) -> bool:
        operator = context.space_data.active_operator
        return isinstance(operator, MaterialToggleOperatorProps)

    def draw_header(self, context: Context) -> None:
        layout = self.layout
        operator = context.space_data.active_operator
        layout.prop(operator, "import_materials", text="")

    def draw(self, context: Context):
        layout = self.layout
        operator = context.space_data.active_operator

        layout.enabled = operator.import_materials

        MaterialImporterOperatorProps.draw_props(layout, operator, context)


class ModelImporterOperatorProps:
    import_animations: BoolProperty(name="Import animations", default=True)

    @staticmethod
    def draw_props(
        layout: UILayout, operator: "ModelImporterOperatorProps", context: Context
    ):
        layout.prop(operator, "import_animations")


from .vmf import (
    ImportVmf,
    PLUMBER_PT_vmf_geometry,
    PLUMBER_PT_vmf_lights,
    PLUMBER_PT_vmf_main,
    PLUMBER_PT_vmf_map_data,
    PLUMBER_PT_vmf_props,
    PLUMBER_PT_vmf_sky,
)
from .mdl import ImportMdl, PLUMBER_PT_mdl_main
from .vmt import ImportVmt, PLUMBER_PT_vmt_main
from .vtf import ImportVtf


CLASSES = [
    SelectedFile,
    PLUMBER_PT_importer_common,
    PLUMBER_PT_vmf_map_data,
    PLUMBER_PT_vmf_geometry,
    PLUMBER_PT_vmf_lights,
    PLUMBER_PT_vmf_sky,
    PLUMBER_PT_vmf_props,
    PLUMBER_PT_importer_materials,
    PLUMBER_PT_vmf_main,
    PLUMBER_PT_vmt_main,
    PLUMBER_PT_mdl_main,
    ImportVmf,
    ImportMdl,
    ImportVmt,
    ImportVtf,
]


def register():
    for cls in CLASSES:
        bpy.utils.register_class(cls)


def unregister():
    for cls in reversed(CLASSES):
        bpy.utils.unregister_class(cls)
