from advancedfx import import_agr
from . import import_qc
from vmfpy.fs import VMFFileSystem
from typing import Any, Set, Optional
from os.path import splitext
import bpy


class AgrImporterWrapper(import_agr.AgrImporter):
    bl_idname = "import_scene._io_import_vmf_agr_wrapper"

    filepath: bpy.props.StringProperty()  # type: ignore
    interKey: bpy.props.BoolProperty(default=False)  # type: ignore
    global_scale: bpy.props.FloatProperty(default=0.01)  # type: ignore
    scaleInvisibleZero: bpy.props.BoolProperty(default=False)  # type: ignore

    qc_importer: import_qc.QCImporter
    collection: bpy.types.Collection

    def execute(self, context: bpy.types.Context) -> Set[str]:
        self.readAgr(context)
        self.errorReport("Error report")
        return {'FINISHED'}

    # import models with materials straight from game files
    def importModel(self, context: bpy.types.Context, modelHandle: Any) -> Any:
        name = splitext(modelHandle.modelName)[0]
        if name == "?":
            return None
        try:
            smd = self.qc_importer.load_return_smd(name, self.collection)
        except FileNotFoundError:
            self.error(f"Failed to import \"{name}\"")
            return None
        modelData = import_agr.ModelData(smd=smd)
        armature = modelData.smd.a
        # Fix rotation:
        if armature.rotation_mode != 'QUATERNION':
            armature.rotation_mode = 'QUATERNION'
        for bone in armature.pose.bones:
            if bone.rotation_mode != 'QUATERNION':
                bone.rotation_mode = 'QUATERNION'
        # Scale:
        armature.scale = (self.global_scale, self.global_scale, self.global_scale)
        modelData = self.addCurvesToModel(context, modelData)
        return modelData


class AgrImporter():
    def __init__(self, dec_models_path: str, vmf_fs: VMFFileSystem = VMFFileSystem(),
                 import_materials: bool = True, simple_materials: bool = False, texture_interpolation: str = 'Linear',
                 inter_key: bool = False, global_scale: float = 0.01, scale_invisible_zero: bool = False,
                 verbose: bool = False):
        self.verbose = verbose
        self.dec_models_path = dec_models_path
        self.vmf_fs = vmf_fs
        if import_materials:
            from . import import_vmt
            vmt_importer: Optional[import_vmt.VMTImporter] = import_vmt.VMTImporter(
                verbose, simple_materials, texture_interpolation
            )
        else:
            vmt_importer = None
        AgrImporterWrapper.qc_importer = import_qc.QCImporter(dec_models_path, vmf_fs, vmt_importer, verbose)
        AgrImporterWrapper.vmf_fs = vmf_fs
        self.inter_key = inter_key
        self.global_scale = global_scale
        self.scale_invisible_zero = scale_invisible_zero

    def __enter__(self) -> 'AgrImporter':
        bpy.utils.register_class(AgrImporterWrapper)
        AgrImporterWrapper.qc_importer.__enter__()
        return self

    def __exit__(self, exc_type: Any, exc_value: Any, traceback: Any) -> None:
        bpy.utils.unregister_class(AgrImporterWrapper)
        AgrImporterWrapper.qc_importer.__exit__(exc_type, exc_value, traceback)

    def load(self, file_path: str, collection: bpy.types.Collection) -> None:
        AgrImporterWrapper.collection = collection
        bpy.ops.import_scene._io_import_vmf_agr_wrapper(
            filepath=file_path, interKey=self.inter_key,
            global_scale=self.global_scale, scaleInvisibleZero=self.scale_invisible_zero,
        )
