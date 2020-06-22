from SourceIO import byte_io_mdl
try:
    from SourceIO import mdl2model
except ImportError:
    raise Exception("Incompatible SourceIO version. Only versions up to 3.7.0 are supported.")
from vmfpy.fs import VMFFileSystem, vmf_path, AnyBinaryIO
from vmfpy.vmt import VMT
import os
from typing import Optional, Dict, Set, Any, TYPE_CHECKING
import bpy


if TYPE_CHECKING:
    from . import import_vmt  # noqa: F401


class ByteIOWrapper(byte_io_mdl.ByteIO):
    def __init__(self, file: AnyBinaryIO = None):
        self.file = file


class SourceModelWrapper(mdl2model.SourceModel):
    def __init__(self, path: str, fp: AnyBinaryIO, vmffs: VMFFileSystem):
        self.filepath = vmf_path(path)
        self.mdl_reader = ByteIOWrapper(file=fp)
        self.vvd_reader: byte_io_mdl.ByteIO = None
        self.vtx_reader: byte_io_mdl.ByteIO = None
        magic, self.version = self.mdl_reader.peek_fmt('II')
        if self.version in self.mdl_version_list:
            self.mdl_version = self.mdl_version_list[self.version]
        else:
            raise NotImplementedError(f"Unsupported mdl v{self.version} version")
        self.vvd = None
        self.vtx = None
        self.mdl: Any = None
        self.vmffs = vmffs

    def find_vtx_vvd(self) -> None:
        vvd_path = self.filepath.with_suffix(".vvd")
        fp = open(vvd_path, 'rb') if os.path.isabs(vvd_path) else self.vmffs.open_file(vvd_path)
        self.vvd_reader = ByteIOWrapper(file=fp)
        vvd_magic, vvd_version = self.vvd_reader.peek_fmt('II')
        if vvd_magic != 1448297545:
            raise TypeError("Not a VVD file")
        if vvd_version in self.vvd_version_list:
            self.vvd = self.vvd_version_list[vvd_version](self.vvd_reader)
        else:
            raise NotImplementedError(f"Unsupported vvd v{vvd_version} version")
        vtx_path = self.filepath.with_suffix(".dx90.vtx")
        fp = open(vtx_path, 'rb') if os.path.isabs(vtx_path) else self.vmffs.open_file(vtx_path)
        self.vtx_reader = ByteIOWrapper(file=fp)
        vtx_version = self.vtx_reader.peek_int32()
        if vtx_version in self.vtx_version_list:
            self.vtx = self.vtx_version_list[vtx_version](self.vtx_reader)
        else:
            raise NotImplementedError(f"Unsupported vtx v{vtx_version} version")


class Source2BlenderWrapper(mdl2model.Source2Blender):
    def __init__(self, name: str, path: str,
                 vmffs: Optional[VMFFileSystem], vmt_importer: Optional['import_vmt.VMTImporter']):
        self.vmt_importer = vmt_importer
        self.import_textures = True
        self.main_collection: bpy.types.Collection = None
        self.current_collection = None
        self.join_clamped = False
        self.normal_bones = False
        self.custom_name = None
        self.name = name
        self.vertex_offset = 0
        self.sort_bodygroups = True
        if vmffs is None or os.path.isabs(path):
            fp = open(path, 'rb')
        else:
            fp = vmffs.open_file(path)
        self.model = SourceModelWrapper(path, fp, vmffs)
        self.mdl: Any = None
        self.vvd = None
        self.vtx = None
        self.mesh_obj = None
        self.armature_obj: bpy.types.Object = None
        self.armature = None
        self.mesh_data = None
        self.vmffs = vmffs
        self._missing_materials: Set[str] = set()

    def load(self, dont_build_mesh: bool = False, collection: bpy.types.Collection = bpy.context.collection) -> None:
        self.model.read()
        self.mdl = self.model.mdl
        self.vvd = self.model.vvd
        self.vtx = self.model.vtx
        if self.import_textures:
            self.load_textures()
        if not dont_build_mesh:
            print("Building mesh")
            self.main_collection = bpy.data.collections.new(os.path.basename(self.mdl.file_data.name))
            collection.children.link(self.main_collection)
            self.armature_obj = None
            self.armature = None
            self.create_skeleton(self.normal_bones)
            if self.armature_obj.name in bpy.context.collection.objects:  # type: ignore
                bpy.context.collection.objects.unlink(self.armature_obj)
            if self.custom_name:
                self.armature_obj.name = self.custom_name
            self.mesh_obj = None
            self.mesh_data = None
            self.create_models()
            self.create_attachments()
            bpy.ops.object.mode_set(mode='OBJECT')

    def load_textures(self) -> None:
        if self.vmt_importer is None:
            return
        if self.vmffs is None:
            raise Exception("cannot import materials: file system not defined")
        self.material_openers = {}
        for texture in self.mdl.file_data.textures:
            try:
                fp = self.vmffs.open_file_utf8(
                    "materials" / vmf_path(texture.path_file_name + ".vmt")
                )
            except FileNotFoundError:
                pass
            else:
                self.material_openers[texture.path_file_name.lower()] = fp
            for tex_path in self.mdl.file_data.texture_paths:
                if tex_path != "" and (tex_path[0] == '/' or tex_path[0] == '\\'):
                    tex_path = tex_path[1:]
                try:
                    fp = self.vmffs.open_file_utf8(
                        "materials" / vmf_path(tex_path) / (texture.path_file_name.lower() + ".vmt")
                    )
                except FileNotFoundError:
                    pass
                else:
                    self.material_openers[texture.path_file_name.lower()] = fp

    def get_material(self, mat_name: str, model_ob: bpy.types.Object) -> int:
        mat_name = mat_name.lower()
        if self.vmt_importer is None or not mat_name:
            return super().get_material(mat_name, model_ob)
        md = model_ob.data
        try:
            data = self.vmt_importer.load(
                mat_name,
                lambda: VMT(
                    self.material_openers[mat_name],
                    self.vmffs,
                    allow_patch=True,
                )
            )
        except KeyError:
            if mat_name not in self._missing_materials:
                print(f"WARNING: MISSING MATERIAL: {mat_name}")
                self._missing_materials.add(mat_name)
        else:
            mat_ind = md.materials.find(data.material.name)
            if mat_ind == -1:
                mat_ind = len(md.materials)
                md.materials.append(data.material)
            return mat_ind
        return super().get_material(mat_name, model_ob)


class MDLImporter():
    def __init__(self, vmf_fs: Optional[VMFFileSystem], vmt_importer: Optional['import_vmt.VMTImporter'],
                 verbose: bool = False):
        self._cache: Dict[str, bpy.types.Object] = {}
        self.verbose = verbose
        self.vmf_fs = vmf_fs
        self.vmt_importer = vmt_importer

    def load(self, name: str, path: str, collection: bpy.types.Collection) -> bpy.types.Object:
        name = name.lower()
        if name in self._cache:
            if self.verbose:
                print(f"Model {name} already imported, copying...")
            original = self._cache[name]
            copy = original.copy()
            collection.objects.link(copy)
            for child in original.children:
                twin = child.copy()
                twin.parent = copy
                if "Armature" in twin.modifiers:
                    twin.modifiers["Armature"].object = copy
                collection.objects.link(twin)
            return copy
        importer = Source2BlenderWrapper(name + ".mdl", path, self.vmf_fs, self.vmt_importer)
        importer.load(collection=collection)
        self._cache[name] = importer.armature_obj
        return importer.armature_obj
