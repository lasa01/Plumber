from typing import Set

from bpy.types import Context
from bpy.props import StringProperty

from . import (
    GameFileImporterOperator,
    GameFileImporterOperatorProps,
    ImporterOperatorProps,
)
from ..asset import AssetCallbacks
from ..plumber import Importer


class ImportVtf(
    GameFileImporterOperator,
    ImporterOperatorProps,
    GameFileImporterOperatorProps,
):
    """Import Source Engine VTF texture"""

    bl_idname = "import_scene.plumber_vtf"
    bl_label = "Import VTF"
    bl_options = {"REGISTER", "UNDO"}

    filename_ext = ".vtf"

    filter_glob: StringProperty(
        default="*.vtf",
        options={"HIDDEN"},
        maxlen=255,
    )

    def execute(self, context: Context) -> Set[str]:
        fs = self.get_game_fs(context)

        file_paths = self.get_file_paths()
        is_batch = self.is_batch_import()

        try:
            importer = Importer(
                fs,
                AssetCallbacks(context),
                self.get_threads_suggestion(context),
            )
        except OSError as err:
            self.report({"ERROR"}, f"could not open file system: {err}")
            return {"CANCELLED"}

        try:
            if is_batch:
                importer.import_vtf_batch(file_paths, self.from_game_fs)
            else:
                importer.import_vtf(self.filepath, self.from_game_fs)
        except OSError as err:
            self.report({"ERROR"}, f"could not import vtf: {err}")
            return {"CANCELLED"}

        return {"FINISHED"}
