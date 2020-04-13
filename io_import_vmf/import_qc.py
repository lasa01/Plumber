from io_scene_valvesource import import_smd, utils
from vmfpy.fs import VMFFileSystem, vmf_path
from vmfpy.vmt import VMT, VMTParseException
import re
from typing import Dict, Any, Tuple, Set, Optional, TYPE_CHECKING
import bpy
from os.path import splitext, basename


_CDMATERIALS_REGEX = re.compile(r'\$CDMaterials[ \t]+"([^"\n]+)"', re.IGNORECASE)


if TYPE_CHECKING:
    from . import import_vmt  # noqa: F401


class SmdImporterWrapper(import_smd.SmdImporter):
    bl_idname = "import_scene._io_import_vmf_smd_wrapper"

    filepath: bpy.props.StringProperty()  # type: ignore
    doAnim: bpy.props.BoolProperty(default=False)  # type: ignore
    makeCamera: bpy.props.BoolProperty(default=False)  # type: ignore
    append: bpy.props.StringProperty(default='APPEND')  # type: ignore
    upAxis: bpy.props.StringProperty(default='Z')  # type: ignore
    rotMode: bpy.props.StringProperty(default='XYZ')  # type: ignore
    boneMode: bpy.props.StringProperty(default='NONE')  # type: ignore

    vmt_importer: Optional['import_vmt.VMTImporter']
    vmf_fs: VMFFileSystem
    collection: bpy.types.Collection

    def execute(self, context: bpy.types.Context) -> set:
        self.existingBones = []  # type: ignore
        self.num_files_imported = 0
        self._missing_materials: Set[str] = set()
        # figure what the material dir should be for the qc
        with open(self.filepath, 'r') as fp:
            match = _CDMATERIALS_REGEX.search(fp.read())
            if match is not None:
                self._cdmaterials = vmf_path(match.group(1))
            else:
                self._cdmaterials = vmf_path("")
        self.readQC(self.filepath, False, False, False, 'XYZ', outer_qc=True)
        SmdImporterWrapper.smd = self.smd
        return {'FINISHED'}

    def readSMD(self, filepath: str, upAxis: str, rotMode: str,
                newscene: bool = False, smd_type: Any = None, target_layer: int = 0) -> int:
        if smd_type == utils.PHYS:  # skip collision meshes
            return 0
        if splitext(basename(filepath))[0].rstrip("1234567890").endswith("_lod"):  # skip lod meshes
            return 0
        result = super().readSMD(filepath, upAxis, rotMode, newscene, smd_type, target_layer)
        if self.smd.g:
            smd_collection: bpy.types.Collection = self.smd.g
            while smd_collection.objects:
                self.collection.objects.link(smd_collection.objects[0])
                smd_collection.objects.unlink(smd_collection.objects[0])
            bpy.data.collections.remove(smd_collection)
        return result

    # properly import materials if they exist
    def getMeshMaterial(self, mat_name: str) -> Tuple[bpy.types.Material, int]:
        mat_name = mat_name.lower().lstrip()
        if self.vmt_importer is None or not mat_name or mat_name == "phy":
            return super().getMeshMaterial(mat_name)
        smd = self.smd
        md: bpy.types.Mesh = smd.m.data
        mat_path = "materials" / self._cdmaterials / vmf_path(mat_name + ".vmt")
        try:
            data = self.vmt_importer.load(
                mat_name,
                lambda: VMT(
                    self.vmf_fs.open_file_utf8(mat_path),
                    self.vmf_fs
                )
            )
        except FileNotFoundError:
            if mat_name not in self._missing_materials:
                print(f"WARNING: MISSING MATERIAL: {mat_path}")
                self._missing_materials.add(mat_name)
        except VMTParseException:
            if mat_name not in self._missing_materials:
                print(f"WARNING: INVALID MATERIAL: {mat_path}")
                self._missing_materials.add(mat_name)
        else:
            mat_ind = md.materials.find(data.material.name)
            if mat_ind == -1:
                mat_ind = len(md.materials)
                md.materials.append(data.material)
            return data.material, mat_ind
        return super().getMeshMaterial(mat_name)


class QCImporter():
    def __init__(self, vmf_fs: Optional[VMFFileSystem], vmt_importer: Optional['import_vmt.VMTImporter'],
                 verbose: bool = False):
        self._cache: Dict[str, bpy.types.Object] = {}
        self.verbose = verbose
        SmdImporterWrapper.vmt_importer = vmt_importer
        SmdImporterWrapper.vmf_fs = vmf_fs

    def __enter__(self) -> 'QCImporter':
        bpy.utils.register_class(SmdImporterWrapper)
        return self

    def __exit__(self, exc_type: Any, exc_value: Any, traceback: Any) -> None:
        bpy.utils.unregister_class(SmdImporterWrapper)

    def load(self, name: str, path: str, collection: bpy.types.Collection = bpy.context.collection) -> bpy.types.Object:
        if name in self._cache:
            if self.verbose:
                print(f"Prop {name} already imported, copying...")
            original = self._cache[name]
            copy = original.copy()
            collection.objects.link(copy)
            for child in original.children:
                twin = child.copy()
                twin.parent = copy
                collection.objects.link(twin)
            return copy
        SmdImporterWrapper.collection = collection
        bpy.ops.import_scene._io_import_vmf_smd_wrapper(filepath=path)
        smd = SmdImporterWrapper.smd
        self._cache[name] = smd.a
        if smd.a.name not in collection.objects:
            collection.objects.link(smd.a)
        bpy.context.scene.collection.objects.unlink(smd.a)
        return smd.a
