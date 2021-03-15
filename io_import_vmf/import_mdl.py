from io_import_vmf.utils import find_armature_modifier, truncate_name
from SourceIO.source1.mdl.import_mdl import import_model
from vmfpy.fs import VMFFileSystem, vmf_path, AnyBinaryIO
from vmfpy.vmt import VMT
import os
from os.path import splitext
from pathlib import PurePosixPath
from typing import Optional, Dict, Set, TYPE_CHECKING
import bpy


if TYPE_CHECKING:
    from . import import_vmt  # noqa: F401
    from SourceIO.source_shared.model_container import Source1ModelContainer


class MDLImporter():
    def __init__(self, vmf_fs: Optional[VMFFileSystem], vmt_importer: Optional['import_vmt.VMTImporter'],
                 verbose: bool = False):
        self._cache: Dict[str, bpy.types.Object] = {}
        self._missing_materials: Set[str] = set()
        self.verbose = verbose
        self.vmf_fs = vmf_fs
        self.vmt_importer = vmt_importer

    def _open_path(self, path: PurePosixPath) -> AnyBinaryIO:
        if not self.vmf_fs or os.path.isabs(path):
            return open(path, 'rb')
        else:
            return self.vmf_fs.open_file(path)

    def _find_vtx(self, mdl_path: PurePosixPath) -> AnyBinaryIO:
        possible_vtx_vertsion = [70, 80, 90, 11, 12]
        for vtx_version in possible_vtx_vertsion[::-1]:
            path = mdl_path.with_suffix(f".dx{vtx_version}.vtx")
            try:
                return self._open_path(path)
            except FileNotFoundError:
                pass
        raise FileNotFoundError(mdl_path.with_suffix(".dx*.vtx"))

    def load(self, name: str, path: str, collection: bpy.types.Collection) -> bpy.types.Object:
        name = name.lower()
        truncated_name = truncate_name(name)
        if name in self._cache:
            if self.verbose:
                print(f"[VERBOSE] Model {name} already imported, copying...")
            original = self._cache[name]
            copy = original.copy()
            collection.objects.link(copy)
            for child in original.children:
                twin = child.copy()
                twin.parent = copy
                armature_modifier = find_armature_modifier(twin)
                if armature_modifier is not None:
                    armature_modifier.object = copy
                collection.objects.link(twin)
            return copy
        path_obj = vmf_path(path)
        mdl_file = self._open_path(path_obj)
        vvd_file = self._open_path(path_obj.with_suffix(".vvd"))
        vtx_file = self._find_vtx(path_obj)
        container: Source1ModelContainer = import_model(mdl_file, vvd_file, vtx_file)
        for mesh in container.objects:
            mesh.name = truncated_name
            mesh.data.name = truncated_name
            collection.objects.link(mesh)
        if container.armature:
            container.armature.name = truncated_name
            container.armature.data.name = truncated_name
            collection.objects.link(container.armature)
        if container.attachments:
            for attachment in container.attachments:
                collection.objects.link(attachment)
        if self.vmf_fs is not None and self.vmt_importer is not None:
            vmf_fs = self.vmf_fs
            for material in container.mdl.materials:
                material_name = material.name
                material_name_truncated = material_name[-63:]
                material = bpy.data.materials[material_name_truncated]
                mat_name_path = vmf_path(material_name + ".vmt")
                for mat_dir in container.mdl.materials_paths:
                    mat_path = "materials" / vmf_path(mat_dir) / mat_name_path
                    if mat_path in vmf_fs:
                        material_name = splitext(mat_path)[0]
                        break
                else:
                    if material_name not in self._missing_materials:
                        print(f"WARNING: MISSING MATERIAL: {material_name}\n")
                        self._missing_materials.add(material_name)
                staged = self.vmt_importer.stage(
                    material_name,
                    lambda: VMT(
                        vmf_fs.open_file_utf8(mat_path),
                        vmf_fs,
                        allow_patch=True,
                    )
                )
                staged.set_material(material)
        import_result = container.armature or container.objects[0]
        self._cache[name] = import_result
        return import_result
