from io_scene_valvesource import import_smd, utils
from .utils import truncate_name
from vmfpy.fs import VMFFileSystem, vmf_path
from vmfpy.vmt import VMT
import re
from collections import defaultdict
from typing import DefaultDict, Dict, Any, NamedTuple, Tuple, Set, Optional, Callable, TYPE_CHECKING
import bpy
import os
from os.path import splitext, basename, dirname, isfile, isdir, isabs, join, relpath
from shutil import move, Error as ShError
import subprocess
import sys
from contextlib import redirect_stdout
from io import StringIO
import time
import traceback


_CROWBARCMD_PATH = join(dirname(__file__), "bin", "CrowbarCommandLineDecomp.exe")
_CDMATERIALS_REGEX = re.compile(r'\$CDMaterials[ \t]+"([^"\n]+)"', re.IGNORECASE)
_IS_LINUX = sys.platform.startswith("linux")


if TYPE_CHECKING:
    from . import import_vmt  # noqa: F401


class FakeSmd():
    def __init__(self, armature: bpy.types.Object, bone_id_map: Dict[int, str]):
        self.a = armature
        self.boneIDs = bone_id_map

    def copy(self) -> 'FakeSmd':
        return FakeSmd(self.a, self.boneIDs)

    @staticmethod
    def from_bst(smd: Any) -> 'FakeSmd':
        if smd is None:
            raise Exception("nothing was imported by Blender Source Tools")
        if not isinstance(smd.a, bpy.types.Object) or not isinstance(smd.boneIDs, dict):
            raise Exception("unexpected Blender Source Tools data format (unsupported version?)")
        return FakeSmd(smd.a, smd.boneIDs)


class SmdImporterWrapper(import_smd.SmdImporter):
    bl_idname = "import_scene._io_import_vmf_smd_wrapper"

    filepath: bpy.props.StringProperty()  # type: ignore
    append: bpy.props.StringProperty(default='APPEND')  # type: ignore
    boneMode: bpy.props.StringProperty(default='NONE')  # type: ignore
    createCollections: bpy.props.BoolProperty(default=False)  # type: ignore

    skip_collision: bpy.props.BoolProperty(default=True)  # type: ignore
    skip_lod: bpy.props.BoolProperty(default=True)  # type: ignore
    skip_anim: bpy.props.BoolProperty(default=False)  # type: ignore

    vmt_importer: Optional['import_vmt.VMTImporter']
    vmf_fs: VMFFileSystem
    collection: bpy.types.Collection
    root: str
    name: str
    full_name: str

    def execute(self, context: bpy.types.Context) -> set:
        self.existingBones = []  # type: ignore
        self.num_files_imported = 0
        self._missing_materials: Set[str] = set()
        self._cdmaterials = [vmf_path("")]
        SmdImporterWrapper.smd = None
        # figure what the material dir should be for the qc
        with open(self.filepath, 'r') as fp:
            content = fp.read()
            for match in _CDMATERIALS_REGEX.finditer(content):
                self._cdmaterials.append(vmf_path(match.group(1)))
            animations = False if self.skip_anim else "$staticprop" not in content.lower()
        self.readQC(self.filepath, False, animations, False, 'QUATERNION', outer_qc=True)
        return {'FINISHED'}

    def readQC(self, filepath: str, newscene: bool, doAnim: bool,
               makeCamera: bool, rotMode: str, outer_qc: bool = False) -> int:
        if outer_qc:
            self.qc = utils.QcInfo()
            self.qc.startTime = time.time()
            self.qc.jobName = SmdImporterWrapper.name
            self.qc.root_filedir = dirname(filepath)
            self.qc.makeCamera = makeCamera
            self.qc.animation_names = []
        return super().readQC(filepath, newscene, doAnim, makeCamera, rotMode, False)

    def createArmature(self, armature_name: str) -> bpy.types.Object:
        if armature_name.endswith("_skeleton"):
            armature_name = armature_name[:-9]
        return super().createArmature(armature_name)

    def initSMD(self, filepath: str, smd_type: str, upAxis: str, rotMode: str, target_layer: int) -> Any:
        smd = super().initSMD(filepath, smd_type, upAxis, rotMode, target_layer)
        smd.jobName = truncate_name(splitext(relpath(filepath, SmdImporterWrapper.root))[0])
        return smd

    def readSMD(self, filepath: str, upAxis: str, rotMode: str,
                newscene: bool = False, smd_type: Any = None, target_layer: int = 0) -> int:
        if self.skip_collision and smd_type == utils.PHYS:  # skip collision meshes
            return 0
        filepath_without_ext = splitext(filepath)[0].replace("\\", "/")
        if self.skip_lod and (filepath_without_ext.rstrip("123456789").endswith("_lod")
                              and not filepath_without_ext.endswith(SmdImporterWrapper.full_name)):  # skip lod meshes
            return 0
        result = super().readSMD(filepath, upAxis, rotMode, newscene, smd_type, target_layer)
        if self.smd.g and self.smd.g != self.collection:
            smd_collection: bpy.types.Collection = self.smd.g
            while smd_collection.objects:
                if smd_collection.objects[0].name not in self.collection.objects:
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
                mat_name = splitext(mat_path)[0]
                break
        else:
            if mat_name not in self._missing_materials:
                sys.__stdout__.write(f"WARNING: MISSING MATERIAL: {mat_name}\n")
                self._missing_materials.add(mat_name)
            return super().getMeshMaterial(mat_name)
        staged = self.vmt_importer.stage(
            mat_name,
            lambda: VMT(
                self.vmf_fs.open_file_utf8(mat_path),
                self.vmf_fs,
                allow_patch=True,
            )
        )
        material = staged.get_material()
        mat_ind = md.materials.find(material.name)
        if mat_ind == -1:
            mat_ind = len(md.materials)
            md.materials.append(material)
        return material, mat_ind


class NewQCInfo(NamedTuple):
    path: str
    root: str


class StagedQC():
    def __init__(self, importer: 'QCImporter', name: str, context: bpy.types.Context,
                 info: Optional[NewQCInfo] = None, reused: Optional[bpy.types.Armature] = None) -> None:
        self.name = name
        self.context = context
        self.info = info
        self.reused = reused
        self._qc_importer = importer

    @staticmethod
    def from_existing(importer: 'QCImporter', armature: bpy.types.Armature, context: bpy.types.Context) -> 'StagedQC':
        return StagedQC(importer, armature.qc_data.full_name, context, reused=armature)


class QCImporter():
    def __init__(self, dec_models_path: str, vmf_fs: VMFFileSystem = VMFFileSystem(),
                 vmt_importer: Optional['import_vmt.VMTImporter'] = None,
                 skip_collision: bool = True, skip_lod: bool = True, skip_anim: bool = False,
                 reuse_old: bool = True, verbose: bool = False):
        self._cache: Dict[str, FakeSmd] = {}
        self._cache_uniqueness: DefaultDict[str, bool] = defaultdict(lambda: True)
        self.verbose = verbose
        self.dec_models_path = dec_models_path
        self.vmf_fs = vmf_fs
        self.reuse_old = reuse_old
        self.skip_collision = skip_collision
        self.skip_lod = skip_lod
        self.skip_anim = skip_anim
        self.progress_callback: Callable[[int, int], None] = lambda current, total: None
        self._staging: Dict[str, StagedQC] = {}
        self._loaded: Dict[str, StagedQC] = {}
        self.reusable_amount = 0
        self.importable_amount = 0
        SmdImporterWrapper.vmt_importer = vmt_importer
        SmdImporterWrapper.vmf_fs = vmf_fs

    def __enter__(self) -> 'QCImporter':
        bpy.utils.register_class(SmdImporterWrapper)
        if _IS_LINUX:
            subprocess.run(("wineserver", "--persistent"), check=True)
        return self

    def __exit__(self, exc_type: Any, exc_value: Any, traceback: Any) -> None:
        bpy.utils.unregister_class(SmdImporterWrapper)
        if _IS_LINUX:
            subprocess.run(("wineserver", "--kill"))

    def stage(self, name: str, path: str, context: bpy.types.Context, root: str = "") -> StagedQC:
        name = name.lower()
        truncated_name = truncate_name(name)
        if name in self._staging:
            return self._staging[name]
        if name in self._loaded:
            return self._loaded[name]
        if self.verbose:
            print(f"[VERBOSE] Staging model {name}")
        if self.reuse_old and truncated_name in bpy.data.armatures:
            meshes = bpy.data.armatures[truncated_name].qc_data.read_meshes()
            # mesh needs to be reimported if some materials failed for now
            if (SmdImporterWrapper.vmt_importer is None or
                all(material.use_nodes and len(material.node_tree.nodes) != 0
                    for mesh in meshes for material in mesh.data.materials)):
                self._staging[name] = StagedQC.from_existing(self, bpy.data.armatures[truncated_name], context)
                self.reusable_amount += 1
                return self._staging[name]
            else:
                # make sure the mesh isn't reimported every time if the materials failed in the first import
                bpy.data.armatures[truncated_name].name = truncated_name + ".001"
        self._staging[name] = StagedQC(self, name, context, info=NewQCInfo(path, root))
        self.importable_amount += 1
        return self._staging[name]

    def load_all(self) -> None:
        if self.verbose:
            print("[VERBOSE] Loading all models...")
        total = len(self._staging)
        current = 0
        for name in self._staging:
            staged = self._staging[name]
            try:
                self._load(name, staged)
            except Exception as err:
                print(f"[ERROR]: MODEL {name} LOADING FAILED: {err}")
                if self.verbose:
                    traceback.print_exception(type(err), err, err.__traceback__)
            else:
                self._loaded[name] = staged
            current += 1
            if current % 5 == 0 or current == total:
                self.progress_callback(current, total)
        self._staging.clear()
        self.reusable_amount = 0
        self.importable_amount = 0

    def _load(self, name: str, staged: StagedQC) -> None:
        name = name.lower()
        truncated_name = truncate_name(name)
        if staged.reused is not None:
            scene_collection = staged.context.scene.collection
            # qc is already imported
            if self.verbose:
                print(f"[VERBOSE] Model {name} previously imported, recreating...")
            armature = staged.reused
            qc_data = armature.qc_data
            armature_obj: bpy.types.Object = bpy.data.objects.new(armature.name, armature)
            scene_collection.objects.link(armature_obj)
            for mesh_obj in qc_data.read_meshes():
                new_obj = mesh_obj.copy()
                new_obj.name = new_obj.data.name
                new_obj.parent = armature_obj
                new_obj.scale = (1, 1, 1)
                new_obj.location = (0, 0, 0)
                new_obj.rotation_euler = (0, 0, 0)
                if "Armature" not in new_obj.modifiers:
                    new_obj.modifiers.new("Armature", 'ARMATURE')
                new_obj.modifiers["Armature"].object = armature_obj
                scene_collection.objects.link(new_obj)
            if qc_data.action is not None:
                anim_data = armature_obj.animation_data_create()
                anim_data.action = qc_data.action
            staged.context.view_layer.update()
            self._cache[name] = FakeSmd(armature_obj, qc_data.read_bone_id_map())
            return
        if staged.info is None:
            raise Exception("required information was not specified for non-reused staged qc")
        path, root = staged.info
        if self.verbose:
            print(f"[VERBOSE] Importing model {name}...")
        SmdImporterWrapper.collection = staged.context.scene.collection
        SmdImporterWrapper.name = truncated_name
        SmdImporterWrapper.full_name = name
        if path.endswith(".mdl"):
            qc_path = join(self.dec_models_path, name + ".qc")
            if not isfile(qc_path):
                # decompiled model doesn't exist, decompile it
                mdl_path = vmf_path(name + ".mdl")
                mdl_dir = mdl_path.parent
                if not isabs(path):
                    mdl_name = mdl_path.stem
                    # save required files
                    saved_files = 0
                    if mdl_dir not in self.vmf_fs.tree:
                        raise FileNotFoundError(mdl_dir)
                    for filename in self.vmf_fs.tree[mdl_dir].files:
                        if not filename.startswith(mdl_name):
                            continue
                        file_out_path = join(self.dec_models_path, mdl_dir, filename)
                        os.makedirs(dirname(file_out_path), exist_ok=True)
                        with self.vmf_fs[mdl_dir / filename] as in_f:
                            with open(file_out_path, 'wb') as out_f:
                                for line in in_f:
                                    out_f.write(line)
                        saved_files += 1
                    if saved_files == 0:
                        print(f"[ERROR] MODEL {mdl_path} NOT FOUND")
                        raise FileNotFoundError(mdl_path)
                    full_mdl_path = str(self.dec_models_path / mdl_path)
                else:
                    full_mdl_path = path
                # call the decompiler
                result = subprocess.run(
                    (
                        (
                            "wine",
                            _CROWBARCMD_PATH,
                        ) if _IS_LINUX else (
                            _CROWBARCMD_PATH,
                        )
                    ) + (
                        "-p", full_mdl_path,
                        "-o", str(self.dec_models_path / mdl_dir)
                    ),
                    text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                )
                alternate_qc_dir = splitext(qc_path)[0]
                alternate_qc_path = join(alternate_qc_dir, basename(name) + ".qc")
                if isdir(alternate_qc_dir) and isfile(alternate_qc_path):
                    # model could be decompiled into different location if user has edited settings in Crowbar
                    qc_dir = dirname(qc_path)
                    for filename in os.listdir(alternate_qc_dir):
                        filepath = join(alternate_qc_dir, filename)
                        try:
                            move(filepath, qc_dir)
                        except (FileExistsError, ShError):
                            os.remove(filepath)
                    os.rmdir(alternate_qc_dir)
                if result.returncode != 0 or not isfile(qc_path):
                    print(result.stdout)
                    raise Exception(f"Decompiling model {mdl_path} failed")
            path = qc_path
            SmdImporterWrapper.root = self.dec_models_path
        else:
            SmdImporterWrapper.root = root
        log_capture = StringIO()
        try:
            with redirect_stdout(log_capture):
                bpy.ops.import_scene._io_import_vmf_smd_wrapper(
                    filepath=path,
                    skip_collision=self.skip_collision,
                    skip_lod=self.skip_lod,
                    skip_anim=self.skip_anim,
                )
        except Exception:
            print(log_capture.getvalue())
            raise
        try:
            fake_smd = FakeSmd.from_bst(SmdImporterWrapper.smd)
        except Exception as err:
            raise Exception(f"Error importing {name}: {err}")
        self._cache[name] = fake_smd
        if fake_smd.a.name in bpy.context.scene.collection.objects:
            bpy.context.scene.collection.objects.unlink(fake_smd.a)
        qc_data = fake_smd.a.data.qc_data
        qc_data.save_meshes(fake_smd.a.children)
        qc_data.save_bone_id_map(fake_smd.boneIDs)
        if fake_smd.a.animation_data is not None:
            qc_data.action = fake_smd.a.animation_data.action
        self._cache[name] = fake_smd

    def get_smd(self, name: str, collection: bpy.types.Collection, context: bpy.types.Context) -> FakeSmd:
        name = name.lower()
        if name not in self._cache:
            raise Exception(f"model {name} hasn't been imported")
        self._cache_uniqueness[name] = False
        smd = self._cache[name]
        scene_collection = context.scene.collection
        if smd.a.name in scene_collection.objects:
            scene_collection.objects.unlink(smd.a)
        collection.objects.link(smd.a)
        for child in smd.a.children:
            if child.name in scene_collection.objects:
                scene_collection.objects.unlink(child)
            collection.objects.link(child)
        return self._cache[name]

    def get(self, name: str, collection: bpy.types.Collection, context: bpy.types.Context) -> bpy.types.Object:
        return self.get_smd(name, collection, context).a

    def get_unique_smd(self, name: str, collection: bpy.types.Collection, context: bpy.types.Context) -> FakeSmd:
        name = name.lower()
        if name not in self._cache:
            raise Exception(f"model {name} hasn't been imported")
        if self._cache_uniqueness[name]:
            return self.get_smd(name, collection, context)
        if self.verbose:
            print(f"[VERBOSE] Copying model {name}...")
        smd = self._cache[name].copy()
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

    def get_unique(self, name: str, collection: bpy.types.Collection, context: bpy.types.Context) -> bpy.types.Object:
        return self.get_unique_smd(name, collection, context).a
