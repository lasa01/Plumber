import bpy
import sys
import os
from os.path import join, abspath, dirname, basename, splitext, isdir, isfile, expanduser
from pathlib import PurePosixPath
from typing import Set, Optional, Tuple
sys.path.append(join(dirname(abspath(__file__)), "deps"))


bl_info = {
    "name": "io_import_vmf",
    "author": "Lassi Säike",
    "description": "Import Valve Map Format (VMF) and Valve Material Type (VMT) files into Blender",
    "blender": (2, 82, 0),
    "version": (0, 0, 1),
    "location": "File > Import > Valve Map Format (.vmf)",
    "warning": "",
    "tracker_url": "https://github.com/lasa01/io_import_vmf",
    "category": "Import-Export"
}


_PAKFILE_WIN = r"C:\Program Files (x86)\Steam\steamapps\common\Counter-Strike Global Offensive\csgo\pak01_dir.vpk"
_PAKFILE_LINUX = "~/.steam/steam/SteamApps/common/Counter-Strike Global Offensive/csgo/pak01_dir.vpk"


class _ValveGameOperatorProps():
    pakfile_path: bpy.props.StringProperty(name="Game VPK path",  # type: ignore
                                           default=_PAKFILE_WIN if os.name == 'nt' else expanduser(_PAKFILE_LINUX))


class _ValveGameOperator(bpy.types.Operator, _ValveGameOperatorProps):
    data_dirs: Tuple[str, ...] = ()
    data_paks: Tuple[str, ...]

    def invoke(self, context: bpy.types.Context, event: bpy.types.Event) -> set:
        context.window_manager.fileselect_add(self)
        return {'RUNNING_MODAL'}

    def _check_valve_props(self) -> Optional[set]:
        if not isfile(self.pakfile_path):
            self.report({'ERROR_INVALID_INPUT'}, "Game VPK file doesn't exist")
            return {'CANCELLED'}
        self.data_paks = (self.pakfile_path,)
        return None


class _VMFOperatorProps(_ValveGameOperatorProps):
    filepath: bpy.props.StringProperty(subtype='FILE_PATH', options={'HIDDEN'})  # type: ignore
    filter_glob: bpy.props.StringProperty(default="*.vmf", options={'HIDDEN'})  # type: ignore

    map_data_path_prop: bpy.props.StringProperty(name="Map data directory path", default="",  # type: ignore
                                                 description="Leave empty to auto-detect")


class _VMFOperator(_ValveGameOperator, _VMFOperatorProps):
    map_data_path: Optional[str]

    def _check_vmf_props(self) -> None:
        self.map_data_path = self.map_data_path_prop
        if self.map_data_path == "":
            filename = splitext(self.filepath)[0]
            # if map is decompiled, strip the suffix
            if filename.endswith("_d"):
                self.map_data_path = filename[:-2]
            else:
                self.map_data_path = filename
        if not isdir(self.map_data_path):  # type: ignore
            self.map_data_path = None


class ExportVMFMDLs(_VMFOperator, _VMFOperatorProps):
    """Export required MDL files for a VMF."""
    bl_idname = "export.vmf_mdls"
    bl_label = "Export VMF MDLs for decompilation"
    bl_options = {'UNDO'}

    out_path: bpy.props.StringProperty(name="Output directory", default="",  # type: ignore
                                       description="Leave empty to use a directory next to current blend file")

    def execute(self, context: bpy.types.Context) -> set:
        result = self._check_valve_props()
        if result is not None:
            return result
        self._check_vmf_props()
        if self.out_path == "":
            if bpy.data.filepath == "":
                self.report({'ERROR_INVALID_INPUT'}, "Output directory not specified and no current blend file")
                return {'CANCELLED'}
            self.out_path = join(dirname(bpy.data.filepath), "vmf_out")
        os.makedirs(self.out_path, exist_ok=True)
        print(f"Output path: {self.out_path}")
        print(f"Map data path: {self.map_data_path}")
        print("Loading VMF...")
        import vmfpy
        print("Indexing game files...")
        vmf_fs = vmfpy.VMFFileSystem(self.data_dirs, self.data_paks, index_files=True)
        vmf = vmfpy.VMF(open(self.filepath, encoding="utf-8"), vmf_fs)
        print("Saving model files...")
        saved: Set[PurePosixPath] = set()
        not_found: Set[PurePosixPath] = set()
        for prop in vmf.prop_entities:
            model = PurePosixPath(prop.model.lower())
            if model in saved or model in not_found:
                continue
            if model not in vmf.fs:
                print(f"Not found: {model}")
                not_found.add(model)
                continue
            saved.add(model)
            match = model.stem
            dirn = model.parent
            content = vmf.fs.tree[dirn]
            for file_name in content.files:
                if not file_name.startswith(match):
                    continue
                file_out_path = join(self.out_path, dirn, file_name)
                print(f"Saving: {dirn / file_name}")
                os.makedirs(dirname(file_out_path), exist_ok=True)
                with vmf.fs[dirn / file_name] as in_f:
                    with open(file_out_path, 'wb') as out_f:
                        for line in in_f:
                            out_f.write(line)
        print("Done!")
        print(f"Saved models: {len(saved)}")
        print(f"Not found: {len(not_found)}")
        return {'FINISHED'}


class ImportSceneVMF(_VMFOperator, _VMFOperatorProps):
    bl_idname = "import_scene.vmf"
    bl_label = "Import VMF"
    bl_options = {'UNDO', 'PRESET'}

    import_solids: bpy.props.BoolProperty(  # type: ignore
        name="Import brushes",
        default=True,
    )

    epsilon: bpy.props.FloatProperty(  # type: ignore
        name="Brush epsilon",
        description="Error threshold for slicing brushes",
        min=0, max=1.0,
        soft_min=0.0001, soft_max=0.1,
        default=0.001, precision=4,
    )

    import_overlays: bpy.props.BoolProperty(  # type: ignore
        name="Import overlays",
        default=True,
    )

    import_props: bpy.props.BoolProperty(  # type: ignore
        name="Import props",
        default=True,
    )

    dec_models_path: bpy.props.StringProperty(  # type: ignore
        name="Models directory",
        default="",
        description="Path to the directory for decompiled models (leave empty to use map data directory)"
    )

    import_materials: bpy.props.BoolProperty(  # type: ignore
        name="Import materials",
        default=True,
    )

    import_lights: bpy.props.BoolProperty(  # type: ignore
        name="Import lights",
        default=True,
    )

    light_factor: bpy.props.FloatProperty(  # type: ignore
        name="Light brightness factor",
        description="Factor for converting light brightness into Blender",
        min=0, max=100.0,
        soft_min=0.0001, soft_max=1.0,
        default=0.1, precision=4,
    )

    sun_factor: bpy.props.FloatProperty(  # type: ignore
        name="Sun brightness factor",
        description="Factor for converting sun brightness into Blender",
        min=0, max=100.0,
        soft_min=0.0001, soft_max=1.0,
        default=0.01, precision=4,
    )

    ambient_factor: bpy.props.FloatProperty(  # type: ignore
        name="Ambient brightness factor",
        description="Factor for converting ambient brightness into Blender",
        min=0, max=100.0,
        soft_min=0.0001, soft_max=1.0,
        default=0.001, precision=4,
    )

    global_scale: bpy.props.FloatProperty(  # type: ignore
        name="Scale",
        description="Scale everything by this value",
        min=0.000001, max=1000000.0,
        soft_min=0.001, soft_max=1.0,
        default=0.01,
    )

    verbose: bpy.props.BoolProperty(  # type: ignore
        name="Verbose",
        description="Enable to print more info into Blender console",
        default=False,
    )

    skip_tools: bpy.props.BoolProperty(  # type: ignore
        name="Skip tools",
        description="Skip importing brushes containing only tool textures",
        default=False,
    )

    def execute(self, context: bpy.types.Context) -> set:
        result = self._check_valve_props()
        if result is not None:
            return result
        self._check_vmf_props()
        dec_models_path = self.dec_models_path
        if dec_models_path == "":
            dec_models_path = None
            if self.import_props:
                self.report({'ERROR_INVALID_INPUT'}, "Decompiled models path must be specified when importing props")
                return {'CANCELLED'}
        from . import import_vmf
        importer = import_vmf.VMFImporter(self.data_dirs, self.data_paks,
                                          import_solids=self.import_solids, import_overlays=self.import_overlays,
                                          import_props=self.import_props,
                                          import_materials=self.import_materials, import_lights=self.import_lights,
                                          scale=self.global_scale, epsilon=self.epsilon,
                                          light_factor=self.light_factor, sun_factor=self.sun_factor,
                                          ambient_factor=self.ambient_factor,
                                          verbose=self.verbose, skip_tools=self.skip_tools)
        with importer:
            importer.load(self.filepath, self.map_data_path, dec_models_path)
        return {'FINISHED'}


class ImportSceneQC(_ValveGameOperator, _ValveGameOperatorProps):
    bl_idname = "import_scene.qc"
    bl_label = "Import QC with materials"
    bl_options = {'UNDO', 'PRESET'}

    filepath: bpy.props.StringProperty(subtype='FILE_PATH', options={'HIDDEN'})  # type: ignore
    filter_glob: bpy.props.StringProperty(default="*.qc", options={'HIDDEN'})  # type: ignore

    import_materials: bpy.props.BoolProperty(  # type: ignore
        name="Import materials",
        default=True,
    )

    verbose: bpy.props.BoolProperty(  # type: ignore
        name="Verbose",
        description="Enable to print more info into console",
        default=False,
    )

    def execute(self, context: bpy.types.Context) -> set:
        result = self._check_valve_props()
        if result is not None:
            return result
        from . import import_qc
        if self.import_materials:
            from . import import_vmt
            from vmfpy.fs import VMFFileSystem
            print("Indexing game files...")
            fs = VMFFileSystem(self.data_dirs, self.data_paks, index_files=True)
        else:
            fs = None
        print("Importing model...")
        importer = import_qc.QCImporter(
            fs,
            import_vmt.VMTImporter(self.verbose) if self.import_materials else None,
            self.verbose,
        )
        with importer:
            importer.load(os.path.basename(self.filepath), self.filepath)
        return {'FINISHED'}


class ImportSceneVMT(_ValveGameOperator, _ValveGameOperatorProps):
    bl_idname = "import_scene.vmt"
    bl_label = "Import VMT"
    bl_options = {'UNDO', 'PRESET'}

    filepath: bpy.props.StringProperty(subtype='FILE_PATH', options={'HIDDEN'})  # type: ignore
    filter_glob: bpy.props.StringProperty(default="*.vmt", options={'HIDDEN'})  # type: ignore

    verbose: bpy.props.BoolProperty(  # type: ignore
        name="Verbose",
        description="Enable to print more info into console",
        default=False,
    )

    def execute(self, context: bpy.types.Context) -> set:
        result = self._check_valve_props()
        if result is not None:
            return result
        from . import import_vmt
        from vmfpy.fs import VMFFileSystem
        from vmfpy.vmt import VMT
        print("Indexing game files...")
        fs = VMFFileSystem(self.data_dirs, self.data_paks, index_files=True)
        print("Loading material...")
        importer = import_vmt.VMTImporter(self.verbose)
        importer.load(splitext(basename(self.filepath))[0], lambda: VMT(open(self.filepath, encoding='utf-8'), fs))
        return {'FINISHED'}


classes = (
    ExportVMFMDLs,
    ImportSceneVMF,
    ImportSceneQC,
    ImportSceneVMT,
)


def import_menu_func(self: bpy.types.Menu, context: bpy.types.Context) -> None:
    self.layout.operator(ImportSceneVMF.bl_idname, text="Valve Map Format (.vmf)")
    self.layout.operator(ImportSceneVMT.bl_idname, text="Valve Material Type (.vmt)")
    self.layout.operator(ImportSceneQC.bl_idname, text="Source Engine Model with materials (.qc)")


def register() -> None:
    for cls in classes:
        bpy.utils.register_class(cls)
    bpy.types.TOPBAR_MT_file_import.append(import_menu_func)


def unregister() -> None:
    for cls in classes:
        bpy.utils.unregister_class(cls)
    bpy.types.TOPBAR_MT_file_import.remove(import_menu_func)
