from typing import Set

from bpy.types import Context, Panel
from bpy.props import StringProperty

from . import (
    GameFileImporterOperator,
    GameFileImporterOperatorProps,
    ImporterOperatorProps,
    MaterialImporterOperatorProps,
)
from ..asset import AssetCallbacks
from ..plumber import Importer


class ImportVmt(
    GameFileImporterOperator,
    ImporterOperatorProps,
    GameFileImporterOperatorProps,
    MaterialImporterOperatorProps,
):
    """Import Source Engine VMT material"""

    bl_idname = "import_scene.plumber_vmt"
    bl_label = "Import VMT"
    bl_options = {"REGISTER", "UNDO", "PRESET"}

    filename_ext = ".vmt"

    filter_glob: StringProperty(
        default="*.vmt",
        options={"HIDDEN"},
        maxlen=255,
    )

    def execute(self, context: Context) -> Set[str]:
        fs = self.get_game_fs(context)

        try:
            importer = Importer(
                fs,
                AssetCallbacks(context),
                self.get_threads_suggestion(context),
                simple_materials=self.simple_materials,
                allow_culling=self.allow_culling,
                editor_materials=self.editor_materials,
                texture_interpolation=self.texture_interpolation,
            )
        except OSError as err:
            self.report({"ERROR"}, f"could not open file system: {err}")
            return {"CANCELLED"}

        try:
            importer.import_vmt(self.filepath, self.from_game_fs)
        except OSError as err:
            self.report({"ERROR"}, f"could not import vmt: {err}")
            return {"CANCELLED"}

        return {"FINISHED"}

    def draw(self, context: Context):
        if self.from_game_fs:
            MaterialImporterOperatorProps.draw_props(self.layout, self, context)


class PLUMBER_PT_vmt_main(Panel):
    bl_space_type = "FILE_BROWSER"
    bl_region_type = "TOOL_PROPS"
    bl_label = ""
    bl_parent_id = "FILE_PT_operator"
    bl_options = {"HIDE_HEADER"}

    @classmethod
    def poll(cls, context: Context) -> bool:
        operator = context.space_data.active_operator
        return operator.bl_idname == "IMPORT_SCENE_OT_plumber_vmt"

    def draw(self, context: Context) -> None:
        MaterialImporterOperatorProps.draw_props(
            self.layout, context.space_data.active_operator, context
        )
