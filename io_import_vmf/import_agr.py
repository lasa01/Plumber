from advancedfx import import_agr
from . import import_qc
from vmfpy.fs import VMFFileSystem
from typing import Any, Set, Optional
from os.path import splitext
import time
import bpy


class AgrImporterWrapper(import_agr.AgrImporter):
    bl_idname = "import_scene._io_import_vmf_agr_wrapper"

    filepath: bpy.props.StringProperty()  # type: ignore
    interKey: bpy.props.BoolProperty(default=False)  # type: ignore
    global_scale: bpy.props.FloatProperty(default=0.01)  # type: ignore
    scaleInvisibleZero: bpy.props.BoolProperty(default=False)  # type: ignore
    keyframeInterpolation: bpy.props.StringProperty(default='BEZIER')  # type: ignore
    skipDuplicateKeyframes: bpy.props.BoolProperty(default=True)  # type: ignore

    qc_importer: import_qc.QCImporter
    collection: bpy.types.Collection

    def execute(self, context: bpy.types.Context) -> Set[str]:
        time_start = time.time()
        result = self.readAgr(context)
        self.errorReport("Error report")
        if result is not None:
            if result['frameBegin'] is not None:
                context.scene.frame_start = result['frameBegin']
            if result['frameEnd'] is not None:
                context.scene.frame_end = result['frameEnd']
        print("AGR import finished in %.4f sec." % (time.time() - time_start))
        return {'FINISHED'}

    # import models with materials straight from game files
    def importModel(self, context: bpy.types.Context, modelHandle: Any) -> Any:
        name = splitext(modelHandle.modelName)[0]
        if name == "?":
            return None
        try:
            self.qc_importer.stage(name, name + ".mdl", context)
            self.qc_importer.load_all()
            smd = self.qc_importer.get_unique_smd(name, self.collection, context)
        except Exception:
            self.error(f"Failed to import \"{name}\"")
            return None
        modelData = import_agr.ModelData(smd=smd)
        armature = modelData.smd.a
        armature.animation_data_clear()
        # Fix rotation:
        if armature.rotation_mode != 'QUATERNION':
            armature.rotation_mode = 'QUATERNION'
        for bone in armature.pose.bones:
            if bone.rotation_mode != 'QUATERNION':
                bone.rotation_mode = 'QUATERNION'
        # Scale:
        armature.scale = (self.global_scale, self.global_scale, self.global_scale)

        arm_name = modelHandle.modelName.rsplit('/', 1)[-1]
        if len(arm_name) > 30:
            arm_name = (arm_name[:30] + '..')
        arm_name = f"afx.{modelHandle.objNr} {arm_name}"
        armature.name = arm_name

        modelData = self.addCurvesToModel(context, modelData)
        return modelData


class AgrImporter():
    def __init__(self, dec_models_path: str, vmf_fs: VMFFileSystem = VMFFileSystem(),
                 import_materials: bool = True, simple_materials: bool = False,
                 texture_interpolation: str = 'Linear', cull_materials: bool = False,
                 reuse_old_materials: bool = True, reuse_old_models: bool = True,
                 inter_key: bool = False, global_scale: float = 0.01, scale_invisible_zero: bool = False,
                 verbose: bool = False):
        self.verbose = verbose
        self.dec_models_path = dec_models_path
        self.vmf_fs = vmf_fs
        if import_materials:
            from . import import_vmt
            self.vmt_importer: Optional[import_vmt.VMTImporter] = import_vmt.VMTImporter(
                verbose, simple_materials, texture_interpolation, cull_materials,
                reuse_old=reuse_old_materials, reuse_old_images=reuse_old_materials,
            )
        else:
            self.vmt_importer = None
        AgrImporterWrapper.qc_importer = import_qc.QCImporter(
            dec_models_path, vmf_fs, self.vmt_importer,
            reuse_old=reuse_old_models, verbose=verbose,
        )
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
        if self.vmt_importer is not None:
            reusable_t, importable_t = self.vmt_importer.texture_amounts()
            print(f"Importing {importable_t} textures (reusing {reusable_t} existing) " +
                  f"and {self.vmt_importer.importable_amount} materials " +
                  f"(reusing {self.vmt_importer.reusable_amount} existing, " +
                  f"{self.vmt_importer.invalid_amount} cannot be imported)...")
            self.vmt_importer.texture_progress_callback = lambda c, t: print(
                f"Importing textures... {c / t * 100:.4f} %"
            )
            self.vmt_importer.progress_callback = lambda c, t: print(
                f"Importing materials... {c / t * 100:.4f} %"
            )
            self.vmt_importer.load_all()
