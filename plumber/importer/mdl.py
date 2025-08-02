from typing import Set

from bpy.types import Context, Panel
from bpy.props import StringProperty, FloatProperty

from . import (
    GameFileImporterOperator,
    GameFileImporterOperatorProps,
    ImporterOperatorProps,
    MaterialToggleOperatorProps,
    ModelImporterOperatorProps,
)
from ..asset import AssetCallbacks
from ..plumber import Importer


class ImportMdl(
    GameFileImporterOperator,
    ImporterOperatorProps,
    GameFileImporterOperatorProps,
    ModelImporterOperatorProps,
    MaterialToggleOperatorProps,
):
    """Import Source Engine MDL model"""

    bl_idname = "import_scene.plumber_mdl"
    bl_label = "Import MDL"
    bl_options = {"REGISTER", "UNDO", "PRESET"}

    filename_ext = ".mdl"

    filter_glob: StringProperty(
        default="*.mdl",
        options={"HIDDEN"},
        maxlen=255,
    )

    scale: FloatProperty(
        name="Scale",
        default=0.01,
        min=1e-6,
        max=1e6,
        soft_min=0.001,
        soft_max=1.0,
    )

    def execute(self, context: Context) -> Set[str]:
        fs = self.get_game_fs(context)
        asset_callbacks = AssetCallbacks(context)

        file_paths = self.get_file_paths()
        is_batch = self.is_batch_import()

        try:
            # For batch imports, determine the root search path from the first file
            root_search = None
            if not self.from_game_fs:
                first_path = file_paths[0] if file_paths else self.filepath
                root_search = (first_path, "models")

            importer = Importer(
                fs,
                asset_callbacks,
                self.get_threads_suggestion(context),
                import_materials=self.import_materials,
                target_fps=self.get_target_fps(context),
                simple_materials=self.simple_materials,
                allow_culling=self.allow_culling,
                editor_materials=self.editor_materials,
                texture_format=self.texture_format,
                texture_interpolation=self.texture_interpolation,
                root_search=root_search,
            )
        except OSError as err:
            self.report({"ERROR"}, f"could not open file system: {err}")
            return {"CANCELLED"}

        try:
            if is_batch and not self.from_game_fs:
                # Start batch tracking for scale application
                asset_callbacks.model_tracker.start_batch()

                importer.import_mdl_batch(
                    file_paths,
                    self.from_game_fs,
                    import_animations=self.import_animations,
                )

                # Apply scale to all models in the batch
                asset_callbacks.model_tracker.apply_scale_to_batch(self.scale)
            else:
                importer.import_mdl(
                    self.filepath,
                    self.from_game_fs,
                    import_animations=self.import_animations,
                )

                # Apply scale to the single imported model
                imported_obj = asset_callbacks.model_tracker.get_last_imported()
                if imported_obj is not None:
                    imported_obj.scale = (self.scale, self.scale, self.scale)

        except OSError as err:
            self.report({"ERROR"}, f"could not import mdl: {err}")
            return {"CANCELLED"}

        return {"FINISHED"}

    def draw(self, context: Context):
        if self.from_game_fs:
            ModelImporterOperatorProps.draw_props(self.layout, self, context)
            MaterialToggleOperatorProps.draw_props(self.layout, self, context)

            self.layout.prop(self, "scale")


class PLUMBER_PT_mdl_main(Panel):
    bl_space_type = "FILE_BROWSER"
    bl_region_type = "TOOL_PROPS"
    bl_label = ""
    bl_parent_id = "FILE_PT_operator"
    bl_options = {"HIDE_HEADER"}

    @classmethod
    def poll(cls, context: Context) -> bool:
        operator = context.space_data.active_operator
        return operator.bl_idname == "IMPORT_SCENE_OT_plumber_mdl"

    def draw(self, context: Context) -> None:
        operator = context.space_data.active_operator
        ModelImporterOperatorProps.draw_props(self.layout, operator, context)

        self.layout.prop(operator, "scale")
