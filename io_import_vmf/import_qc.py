from io_scene_valvesource import import_smd, utils
from vmfpy.fs import VMFFileSystem, vmf_path
from vmfpy.vmt import VMT
import re
from typing import Dict, Any, Tuple, Set, Optional, TYPE_CHECKING
import bpy
import os
from os.path import splitext, basename, dirname, isfile, join
import subprocess
import copy


_CROWBARCMD_PATH = join(dirname(__file__), "bin/CrowbarCommandLineDecomp.exe")
_CDMATERIALS_REGEX = re.compile(r'\$CDMaterials[ \t]+"([^"\n]+)"', re.IGNORECASE)


if TYPE_CHECKING:
    from . import import_vmt  # noqa: F401


class SmdImporterWrapper(import_smd.SmdImporter):
    bl_idname = "import_scene._io_import_vmf_smd_wrapper"

    filepath: bpy.props.StringProperty()  # type: ignore
    append: bpy.props.StringProperty(default='APPEND')  # type: ignore
    boneMode: bpy.props.StringProperty(default='NONE')  # type: ignore
    createCollections: bpy.props.BoolProperty(default=False)  # type: ignore

    vmt_importer: Optional['import_vmt.VMTImporter']
    vmf_fs: VMFFileSystem
    collection: bpy.types.Collection

    def execute(self, context: bpy.types.Context) -> set:
        self.existingBones = []  # type: ignore
        self.num_files_imported = 0
        self._missing_materials: Set[str] = set()
        self._cdmaterials = [vmf_path("")]
        SmdImporterWrapper.smd = None
        # figure what the material dir should be for the qc
        with open(self.filepath, 'r') as fp:
            for match in _CDMATERIALS_REGEX.finditer(fp.read()):
                self._cdmaterials.append(vmf_path(match.group(1)))
        self.readQC(self.filepath, False, True, False, 'XYZ', outer_qc=True)
        return {'FINISHED'}

    def readSMD(self, filepath: str, upAxis: str, rotMode: str,
                newscene: bool = False, smd_type: Any = None, target_layer: int = 0) -> int:
        if smd_type == utils.PHYS:  # skip collision meshes
            return 0
        if splitext(basename(filepath))[0].rstrip("123456789").endswith("_lod"):  # skip lod meshes
            return 0
        result = super().readSMD(filepath, upAxis, rotMode, newscene, smd_type, target_layer)
        if self.smd.g:
            smd_collection: bpy.types.Collection = self.smd.g
            while smd_collection.objects:
                self.collection.objects.link(smd_collection.objects[0])
                smd_collection.objects.unlink(smd_collection.objects[0])
            bpy.data.collections.remove(smd_collection)
        if result != 0:
            SmdImporterWrapper.smd = self.smd
        return result

    # properly import materials if they exist
    def getMeshMaterial(self, mat_name: str) -> Tuple[bpy.types.Material, int]:
        mat_name = mat_name.lower().lstrip()
        if self.vmt_importer is None or not mat_name or mat_name == "phy":
            return super().getMeshMaterial(mat_name)
        smd = self.smd
        md: bpy.types.Mesh = smd.m.data
        # search for material file
        mat_name_path = vmf_path(mat_name + ".vmt")
        for mat_dir in self._cdmaterials:
            mat_path = "materials" / mat_dir / mat_name_path
            if mat_path in self.vmf_fs:
                break
        else:
            if mat_name not in self._missing_materials:
                print(f"WARNING: MISSING MATERIAL: {mat_path}")
                self._missing_materials.add(mat_name)
            return super().getMeshMaterial(mat_name)
        data = self.vmt_importer.load(
            mat_name,
            lambda: VMT(
                self.vmf_fs.open_file_utf8(mat_path),
                self.vmf_fs,
                allow_patch=True,
            )
        )
        mat_ind = md.materials.find(data.material.name)
        if mat_ind == -1:
            mat_ind = len(md.materials)
            md.materials.append(data.material)
        return data.material, mat_ind


class QCImporter():
    def __init__(self, dec_models_path: str, vmf_fs: VMFFileSystem = VMFFileSystem(),
                 vmt_importer: Optional['import_vmt.VMTImporter'] = None, verbose: bool = False):
        self._cache: Dict[str, bpy.types.Object] = {}
        self.verbose = verbose
        self.dec_models_path = dec_models_path
        self.vmf_fs = vmf_fs
        SmdImporterWrapper.vmt_importer = vmt_importer
        SmdImporterWrapper.vmf_fs = vmf_fs

    def __enter__(self) -> 'QCImporter':
        bpy.utils.register_class(SmdImporterWrapper)
        return self

    def __exit__(self, exc_type: Any, exc_value: Any, traceback: Any) -> None:
        bpy.utils.unregister_class(SmdImporterWrapper)

    def load_return_smd(self, name: str, collection: bpy.types.Collection) -> Any:
        name = name.lower()
        if name in self._cache:
            if self.verbose:
                print(f"Model {name} already imported, copying...")
            smd = copy.copy(self._cache[name])
            original_arm = smd.a
            copy_arm = original_arm.copy()
            collection.objects.link(copy_arm)
            for child in original_arm.children:
                twin = child.copy()
                twin.parent = copy_arm
                if "Armature" in twin.modifiers:
                    twin.modifiers["Armature"].object = copy_arm
                collection.objects.link(twin)
            smd.a = copy_arm
            return smd
        SmdImporterWrapper.collection = collection
        path = join(self.dec_models_path, name + ".qc")
        if not isfile(path):
            mdl_path = vmf_path(name)
            mdl_dir = mdl_path.parent
            mdl_name = mdl_path.stem
            # decompiled model doesn't exist, decompile it
            # save required files
            try:
                for filename in self.vmf_fs.tree[mdl_dir].files:
                    if not filename.startswith(mdl_name):
                        continue
                    file_out_path = join(self.dec_models_path, mdl_dir, filename)
                    os.makedirs(dirname(file_out_path), exist_ok=True)
                    with self.vmf_fs[mdl_dir / filename] as in_f:
                        with open(file_out_path, 'wb') as out_f:
                            for line in in_f:
                                out_f.write(line)
            except KeyError:
                print(f"ERROR: MODEL {mdl_path} NOT FOUND")
                raise FileNotFoundError(mdl_path)
            else:
                # call the decompiler
                subprocess.run(
                    (
                        _CROWBARCMD_PATH,
                        "-p", str(self.dec_models_path / mdl_path.with_suffix(".mdl")),
                        "-o", str(self.dec_models_path / mdl_dir)
                    ),
                    check=True
                )
        bpy.ops.import_scene._io_import_vmf_smd_wrapper(filepath=path)
        smd = SmdImporterWrapper.smd
        if smd is None:
            raise Exception(f"Error importing {name}: nothing was imported by Blender Source Tools")
        self._cache[name] = smd
        if smd.a.name not in collection.objects:
            collection.objects.link(smd.a)
        if smd.a.name in bpy.context.scene.collection.objects:
            bpy.context.scene.collection.objects.unlink(smd.a)
        return smd

    def load(self, name: str, collection: bpy.types.Collection) -> bpy.types.Object:
        return self.load_return_smd(name, collection).a
