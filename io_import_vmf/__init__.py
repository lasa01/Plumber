import bpy
import sys
import os
from os.path import join, relpath, abspath, dirname, basename, splitext, isdir
from shutil import rmtree
import glob
from pathlib import PurePosixPath
from typing import Set, Optional, Tuple, List
sys.path.append(join(dirname(abspath(__file__)), "deps"))


bl_info = {
    "name": "Import Valve Map Format / Valve Material Type",
    "author": "Lassi Säike",
    "description": "Import Valve Map Format (VMF) and Valve Material Type (VMT) files.",
    "blender": (2, 82, 0),
    "version": (0, 1, 0),
    "location": "File > Import",
    "warning": "",
    "tracker_url": "https://github.com/lasa01/io_import_vmf",
    "category": "Import-Export"
}


class ValveGameSettings(bpy.types.PropertyGroup):
    name: bpy.props.StringProperty(name="Name", default="Source Game")  # type: ignore

    def get_gamedir_path(self) -> str:
        return self.get("gamedir_path", "")

    def set_gamedir_path(self, value: str) -> None:
        value = value.rstrip("\\/")
        self["gamedir_path"] = value
        pak_candidates = glob.glob(join(value, "*_dir.vpk"))
        if len(pak_candidates) != 0:
            game = basename(value)
            for candidate in pak_candidates:
                candidate_f = basename(candidate)
                if "pak01" in candidate_f or game in candidate_f:
                    self.pakfile_path = candidate
                    break
            else:
                self.pakfile_path = pak_candidates[0]
        self.name = basename(dirname(value))

    gamedir_path: bpy.props.StringProperty(name="Game directory path", subtype='DIR_PATH',  # type: ignore
                                           get=get_gamedir_path, set=set_gamedir_path)
    pakfile_path: bpy.props.StringProperty(name="Game VPK path", subtype='FILE_PATH')  # type: ignore


class ValveGameSettingsList(bpy.types.UIList):
    bl_idname = "IO_IMPORT_VMF_UL_valvegameslist"

    def draw_item(self, context: bpy.types.Context, layout: bpy.types.UILayout,
                  data: 'ValveGameAddonPreferences', item: ValveGameSettings,
                  icon: int, active_data: int, active_propname: str) -> None:
        if self.layout_type in {'DEFAULT', 'COMPACT'}:
            layout.prop(item, "name", text="", emboss=False, icon_value=icon)
        elif self.layout_type in {'GRID'}:
            layout.alignment = 'CENTER'
            layout.label(text=item.name, icon_value=icon)


class AddValveGameOperator(bpy.types.Operator):
    bl_idname = "io_import_vmf.valvegame_add"
    bl_label = "Add a Valve game definition"
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context: bpy.types.Context) -> Set[str]:
        preferences: ValveGameAddonPreferences = context.preferences.addons[__package__].preferences
        preferences.games.add()
        preferences.game_index = len(preferences.games) - 1
        return {'FINISHED'}


class RemoveValveGameOperator(bpy.types.Operator):
    bl_idname = "io_import_vmf.valvegame_remove"
    bl_label = "Remove a Valve game definition"
    bl_options = {'REGISTER', 'UNDO'}

    @classmethod
    def poll(cls, context: bpy.types.Context) -> bool:
        return bool(context.preferences.addons[__package__].preferences.games)

    def execute(self, context: bpy.types.Context) -> Set[str]:
        preferences: ValveGameAddonPreferences = context.preferences.addons[__package__].preferences
        preferences.games.remove(preferences.game_index)
        preferences.game_index = min(max(0, preferences.game_index - 1), len(preferences.games) - 1)
        return {'FINISHED'}


class ValveGameAddonPreferences(bpy.types.AddonPreferences):
    bl_idname = __package__

    games: bpy.props.CollectionProperty(type=ValveGameSettings)  # type: ignore
    game_index: bpy.props.IntProperty(name="Game definition")  # type: ignore

    dec_models_path: bpy.props.StringProperty(  # type: ignore
        name="Models path",
        default="",
        description="Path to the directory for decompiled models.",
        subtype='DIR_PATH'
    )

    @staticmethod
    def game_enum_items(self: bpy.types.EnumProperty, context: bpy.types.Context) -> List[Tuple[str, str, str]]:
        preferences: ValveGameAddonPreferences = context.preferences.addons[__package__].preferences
        items = [(str(i), game.name, "") for i, game in enumerate(preferences.games.values())]
        items.append(('NONE', "None", ""))
        return items

    def draw(self, context: bpy.types.Context) -> None:
        layout: bpy.types.UILayout = self.layout
        layout.label(text="Valve game definitions:")
        row = layout.row()
        row.template_list("IO_IMPORT_VMF_UL_valvegameslist", "", self, "games", self, "game_index")
        col = row.column()
        col.operator("io_import_vmf.valvegame_add", text="", icon='ADD')
        col.operator("io_import_vmf.valvegame_remove", text="", icon='REMOVE')
        if self.games:
            box = layout.box()
            game = self.games[self.game_index]
            box.prop(game, "gamedir_path")
            box.prop(game, "pakfile_path")
        layout.separator_spacer()
        layout.prop(self, "dec_models_path")
        layout.label(text="Specifies a persistent path to save decompiled models to.", icon='INFO')


class ValveGameOpenPreferencesOperator(bpy.types.Operator):
    bl_idname = "io_import_vmf.open_preferences"
    bl_label = "Open Valve game definition preferences"
    bl_options = {'INTERNAL'}

    def execute(self, context: bpy.types.Context) -> Set[str]:
        bpy.ops.preferences.addon_show('INVOKE_SCREEN', module=__package__)
        return {'FINISHED'}


class _ValveGameOperatorProps():
    game: bpy.props.EnumProperty(items=ValveGameAddonPreferences.game_enum_items,  # type: ignore
                                 name="Game definition", description="Used for searching files")


class _ValveGameOperator(bpy.types.Operator, _ValveGameOperatorProps):
    data_dirs: Tuple[str, ...]
    data_paks: Tuple[str, ...]

    def invoke(self, context: bpy.types.Context, event: bpy.types.Event) -> Set[str]:
        context.window_manager.fileselect_add(self)
        return {'RUNNING_MODAL'}

    def draw(self, context: bpy.types.Context) -> None:
        layout: bpy.types.UILayout = self.layout
        layout.alignment = 'RIGHT'
        preferences: ValveGameAddonPreferences = context.preferences.addons[__package__].preferences
        layout.prop(self, "game")
        if not preferences.games:
            box = layout.box()
            row = box.row()
            row.label(text="Open preferences to add game definitions.", icon='INFO')
            row.operator("io_import_vmf.open_preferences", text="", icon='PREFERENCES')

    def _check_valve_props(self, context: bpy.types.Context) -> Optional[Set[str]]:
        if self.game != 'NONE':
            preferences: ValveGameAddonPreferences = context.preferences.addons[__package__].preferences
            game_def: ValveGameSettings = preferences.games[int(self.game)]
            self.data_paks = (game_def.pakfile_path,)
            self.data_dirs = (game_def.gamedir_path,)
        else:
            self.data_paks = ()
            self.data_dirs = ()
        return None


class _VMFOperatorProps(_ValveGameOperatorProps):
    filepath: bpy.props.StringProperty(subtype='FILE_PATH', options={'HIDDEN'})  # type: ignore
    filter_glob: bpy.props.StringProperty(default="*.vmf", options={'HIDDEN'})  # type: ignore

    map_data_path_prop: bpy.props.StringProperty(name="Embedded files path", default="",  # type: ignore
                                                 description="Leave empty to auto-detect")


class _VMFOperator(_ValveGameOperator, _VMFOperatorProps):
    map_data_path: Optional[str]

    def draw(self, context: bpy.types.Context) -> None:
        layout: bpy.types.UILayout = self.layout
        super().draw(context)
        layout.prop(self, "map_data_path_prop", icon='FILE_FOLDER')

    def _check_vmf_props(self) -> None:
        self.map_data_path = self.map_data_path_prop
        if self.map_data_path == "":
            self.map_data_path = splitext(self.filepath)[0]
        if not isdir(self.map_data_path):  # type: ignore
            self.map_data_path = None


class ExportVMFMDLs(_VMFOperator, _VMFOperatorProps):
    """Export required MDL files for a VMF."""
    bl_idname = "export.vmf_mdls"
    bl_label = "Export VMF MDLs for decompilation"
    bl_options: Set[str] = set()

    out_path: bpy.props.StringProperty(name="Output directory", default="",  # type: ignore
                                       description="Leave empty to use a directory next to input file")

    def execute(self, context: bpy.types.Context) -> Set[str]:
        result = self._check_valve_props(context)
        if result is not None:
            return result
        self._check_vmf_props()
        if self.out_path == "":
            self.out_path = join(dirname(self.filepath), f"{splitext(basename(self.filepath))[0]}_models")
        os.makedirs(self.out_path, exist_ok=True)
        print(f"Output path: {self.out_path}")
        print(f"Map data path: {self.map_data_path}")
        print("Loading VMF...")
        import vmfpy
        print("Indexing game files...")
        vmf_fs = vmfpy.VMFFileSystem(self.data_dirs + (self.map_data_path,), self.data_paks, index_files=True)
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

    def draw(self, context: bpy.types.Context) -> None:
        layout: bpy.types.UILayout = self.layout
        super().draw(context)
        layout.prop(self, "out_path", icon='FILE_FOLDER')


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

    skip_tools: bpy.props.BoolProperty(  # type: ignore
        name="Skip tools (invisible brushes)",
        description="Skip importing brushes containing only tool textures",
        default=True,
    )

    import_overlays: bpy.props.BoolProperty(  # type: ignore
        name="Import overlays",
        default=True,
    )

    import_props: bpy.props.BoolProperty(  # type: ignore
        name="Import props",
        default=True,
        description="SourceIO or Blender Source Tools must be installed for this to work.",
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

    import_materials: bpy.props.BoolProperty(  # type: ignore
        name="Import materials",
        default=True,
    )

    simple_materials: bpy.props.BoolProperty(  # type: ignore
        name="Simple materials",
        description="Import simple, exporter-friendly versions of materials.",
        default=False,
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

    # mdl_available = False
    qc_available = False

    def invoke(self, context: bpy.types.Context, event: bpy.types.Event) -> Set[str]:
        # try:
        #     from . import import_mdl  # noqa: F401
        # except ImportError:
        #     self.mdl_available = False
        # else:
        #     self.mdl_available = True
        try:
            from . import import_qc  # noqa: F401
        except ImportError:
            self.qc_available = False
        else:
            self.qc_available = True
        return super().invoke(context, event)

    def execute(self, context: bpy.types.Context) -> Set[str]:
        result = self._check_valve_props(context)
        if result is not None:
            return result
        self._check_vmf_props()
        preferences: ValveGameAddonPreferences = context.preferences.addons[__package__].preferences
        dec_models_path = preferences.dec_models_path
        delete_files = False
        if dec_models_path == "":
            delete_files = True
            dec_models_path = join(context.preferences.filepaths.temporary_directory, "blender_io_import_vmf_models")
        from . import import_vmf
        importer = import_vmf.VMFImporter(self.data_dirs, self.data_paks, dec_models_path,
                                          import_solids=self.import_solids, import_overlays=self.import_overlays,
                                          import_props=self.import_props,
                                          import_materials=self.import_materials,
                                          simple_materials=self.simple_materials,
                                          import_lights=self.import_lights,
                                          scale=self.global_scale, epsilon=self.epsilon,
                                          light_factor=self.light_factor, sun_factor=self.sun_factor,
                                          ambient_factor=self.ambient_factor,
                                          verbose=self.verbose, skip_tools=self.skip_tools)
        with importer:
            importer.load(self.filepath, context, self.map_data_path)
        if delete_files:
            rmtree(dec_models_path, ignore_errors=True)
        return {'FINISHED'}

    def draw(self, context: bpy.types.Context) -> None:
        layout: bpy.types.UILayout = self.layout
        super().draw(context)
        layout.separator_spacer()
        layout.prop(self, "import_solids")
        if self.import_solids:
            box = layout.box()
            box.prop(self, "epsilon")
            box.prop(self, "skip_tools")
            box.prop(self, "import_overlays")
        col = layout.column()
        col.prop(self, "import_props")
        if self.import_props:
            box = col.box()
            # if self.mdl_available:
            #     box.label(text="Models will be imported using SourceIO.")
            if self.qc_available:
                box.label(text="Models will be imported using Blender Source Tools.")
                preferences: ValveGameAddonPreferences = context.preferences.addons[__package__].preferences
                if not preferences.dec_models_path:
                    box.label(text="They will be decompiled into a temp directory and deleted.")
                    row = box.row()
                    row.label(text="You can specify a persistent path for decompiled models.", icon='INFO')
                    row.operator("io_import_vmf.open_preferences", text="", icon='PREFERENCES')
                else:
                    box.label(text="Missing models will be decompiled.")
        if not self.qc_available:
            self.import_props = False
            col.enabled = False
            col.label(text="Blender Source tools must be installed to import props.")
        if self.import_solids or self.import_props:
            layout.prop(self, "import_materials")
            if self.import_materials:
                box = layout.box()
                box.prop(self, "simple_materials")
        layout.prop(self, "import_lights")
        if self.import_lights:
            box = layout.box()
            box.prop(self, "light_factor")
            box.prop(self, "sun_factor")
            box.prop(self, "ambient_factor")
        layout.separator_spacer()
        layout.prop(self, "global_scale")
        layout.prop(self, "verbose")


def _get_source_path_root(path: str) -> str:
    fallback_dirname = dirname(path)
    while True:
        new_path = dirname(path)
        if new_path == path:
            return fallback_dirname
        path = new_path
        if basename(path) == "models":
            break
    return dirname(path)


class ImportSceneQC(_ValveGameOperator, _ValveGameOperatorProps):
    bl_idname = "import_scene.qc_enhanced"
    bl_label = "Import QC (enhanced)"
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

    def execute(self, context: bpy.types.Context) -> Set[str]:
        try:
            from . import import_qc
        except ImportError:
            self.report({'ERROR'}, "Blender Source Tools must be installed for importing QC files")
            return {'CANCELLED'}
        result = self._check_valve_props(context)
        if result is not None:
            return result
        if self.import_materials:
            from . import import_vmt
            from vmfpy.fs import VMFFileSystem
            print("Indexing game files...")
            fs = VMFFileSystem(self.data_dirs, self.data_paks, index_files=True)
        else:
            fs = None
        print("Importing model...")
        root = _get_source_path_root(self.filepath)
        importer = import_qc.QCImporter(
            root,
            fs,
            import_vmt.VMTImporter(self.verbose) if self.import_materials else None,
            self.verbose,
        )
        with importer:
            importer.load(splitext(relpath(self.filepath, root))[0], context.collection)
        return {'FINISHED'}

    def draw(self, context: bpy.types.Context) -> None:
        layout: bpy.types.UILayout = self.layout
        super().draw(context)
        layout.prop(self, "import_materials")
        layout.prop(self, "verbose")


# NOTE: Imports invalid rotation, disabled
class ImportSceneMDL(_ValveGameOperator, _ValveGameOperatorProps):
    bl_idname = "import_scene.mdl_enhanced"
    bl_label = "Import MDL (enhanced)"
    bl_options = {'UNDO', 'PRESET'}

    filepath: bpy.props.StringProperty(subtype='FILE_PATH', options={'HIDDEN'})  # type: ignore
    filter_glob: bpy.props.StringProperty(default="*.mdl", options={'HIDDEN'})  # type: ignore

    import_materials: bpy.props.BoolProperty(  # type: ignore
        name="Import materials",
        default=True,
    )

    verbose: bpy.props.BoolProperty(  # type: ignore
        name="Verbose",
        description="Enable to print more info into console",
        default=False,
    )

    def execute(self, context: bpy.types.Context) -> Set[str]:
        try:
            from . import import_mdl
        except ImportError:
            self.report({'ERROR'}, "SourceIO must be installed for importing MDL files")
            return {'CANCELLED'}
        result = self._check_valve_props(context)
        if result is not None:
            return result
        from . import import_vmt
        from vmfpy.fs import VMFFileSystem
        root = _get_source_path_root(self.filepath)
        print("Indexing game files...")
        fs = VMFFileSystem(self.data_dirs, self.data_paks, index_files=True)
        print("Importing model...")
        importer = import_mdl.MDLImporter(
            fs,
            import_vmt.VMTImporter(self.verbose) if self.import_materials else None,
            self.verbose,
        )
        importer.load(splitext(relpath(self.filepath, root))[0], self.filepath, context.collection)
        return {'FINISHED'}

    def draw(self, context: bpy.types.Context) -> None:
        layout: bpy.types.UILayout = self.layout
        super().draw(context)
        layout.prop(self, "import_materials")
        layout.prop(self, "verbose")


class ImportSceneVMT(_ValveGameOperator, _ValveGameOperatorProps):
    bl_idname = "import_scene.vmt"
    bl_label = "Import VMT"
    bl_options = {'UNDO', 'PRESET'}

    filepath: bpy.props.StringProperty(subtype='FILE_PATH', options={'HIDDEN'})  # type: ignore
    filter_glob: bpy.props.StringProperty(default="*.vmt", options={'HIDDEN'})  # type: ignore

    simple_materials: bpy.props.BoolProperty(  # type: ignore
        name="Simple materials",
        description="Import simple, exporter-friendly versions of materials.",
        default=False,
    )

    verbose: bpy.props.BoolProperty(  # type: ignore
        name="Verbose",
        description="Enable to print more info into console",
        default=False,
    )

    def execute(self, context: bpy.types.Context) -> Set[str]:
        result = self._check_valve_props(context)
        if result is not None:
            return result
        from . import import_vmt
        from vmfpy.fs import VMFFileSystem
        from vmfpy.vmt import VMT
        print("Indexing game files...")
        fs = VMFFileSystem(self.data_dirs, self.data_paks, index_files=True)
        print("Loading material...")
        importer = import_vmt.VMTImporter(self.verbose, self.simple_materials)
        importer.load(
            splitext(basename(self.filepath))[0],
            lambda: VMT(open(self.filepath, encoding='utf-8'), fs, allow_patch=False)
        )
        return {'FINISHED'}

    def draw(self, context: bpy.types.Context) -> None:
        layout: bpy.types.UILayout = self.layout
        super().draw(context)
        layout.prop(self, "simple_materials")
        layout.prop(self, "verbose")


class ImportSceneAGREnhanced(_ValveGameOperator, _ValveGameOperatorProps):
    bl_idname = "import_scene.agr_enhanced"
    bl_label = "Import AGR (enhanced)"
    bl_options = {'UNDO', 'PRESET'}

    filepath: bpy.props.StringProperty(subtype='FILE_PATH', options={'HIDDEN'})  # type: ignore
    filter_glob: bpy.props.StringProperty(default="*.agr", options={'HIDDEN'})  # type: ignore

    import_materials: bpy.props.BoolProperty(  # type: ignore
        name="Import materials",
        default=True,
    )

    simple_materials: bpy.props.BoolProperty(  # type: ignore
        name="Simple materials",
        description="Import simple, exporter-friendly versions of materials.",
        default=False,
    )

    inter_key: bpy.props.BoolProperty(  # type: ignore
        name="Add interpolated key frames",
        description="Create interpolated key frames for frames in-between the original key frames.",
        default=False,
    )

    global_scale: bpy.props.FloatProperty(  # type: ignore
        name="Scale",
        description="Scale everything by this value (0.01 old default, 0.0254 is more accurate)",
        min=0.000001, max=1000000.0,
        soft_min=0.001, soft_max=1.0,
        default=0.01,
    )

    scale_invisible_zero: bpy.props.BoolProperty(  # type: ignore
        name="Scale invisible to zero",
        description="If set entities will scaled to zero when not visible.",
        default=False,
    )

    verbose: bpy.props.BoolProperty(  # type: ignore
        name="Verbose",
        description="Enable to print more info into console",
        default=False,
    )

    def execute(self, context: bpy.types.Context) -> Set[str]:
        result = self._check_valve_props(context)
        if result is not None:
            return result
        preferences: ValveGameAddonPreferences = context.preferences.addons[__package__].preferences
        dec_models_path = preferences.dec_models_path
        delete_files = False
        if dec_models_path == "":
            delete_files = True
            dec_models_path = join(context.preferences.filepaths.temporary_directory, "blender_io_import_vmf_models")
        from . import import_agr
        from vmfpy.fs import VMFFileSystem
        print("Indexing game files...")
        fs = VMFFileSystem(self.data_dirs, self.data_paks, index_files=True)
        importer = import_agr.AgrImporter(
            dec_models_path, fs,
            import_materials=self.import_materials, simple_materials=self.simple_materials,
            inter_key=self.inter_key, global_scale=self.global_scale, scale_invisible_zero=self.scale_invisible_zero,
        )
        with importer:
            importer.load(self.filepath, context.collection)
        if delete_files:
            rmtree(dec_models_path, ignore_errors=True)
        return {'FINISHED'}

    def draw(self, context: bpy.types.Context) -> None:
        layout: bpy.types.UILayout = self.layout
        super().draw(context)
        box = layout.box()
        box.label(text="Models will be imported using Blender Source Tools.")
        preferences: ValveGameAddonPreferences = context.preferences.addons[__package__].preferences
        if not preferences.dec_models_path:
            box.label(text="They will be decompiled into a temp directory and deleted.")
            row = box.row()
            row.label(text="You can specify a persistent path for decompiled models.", icon='INFO')
            row.operator("io_import_vmf.open_preferences", text="", icon='PREFERENCES')
        else:
            box.label(text="Missing models will be decompiled.")
        layout.prop(self, "import_materials")
        if self.import_materials:
            box = layout.box()
            box.prop(self, "simple_materials")
        layout.prop(self, "inter_key")
        layout.prop(self, "global_scale")
        layout.prop(self, "scale_invisible_zero")
        layout.prop(self, "verbose")


classes = (
    ValveGameSettings,
    ValveGameSettingsList,
    AddValveGameOperator,
    RemoveValveGameOperator,
    ValveGameAddonPreferences,
    ValveGameOpenPreferencesOperator,
    ExportVMFMDLs,
    ImportSceneVMF,
    ImportSceneQC,
    # ImportSceneMDL,
    ImportSceneVMT,
    ImportSceneAGREnhanced,
)


def import_menu_func(self: bpy.types.Menu, context: bpy.types.Context) -> None:
    self.layout.operator(ImportSceneVMF.bl_idname, text="Valve Map Format (.vmf)")
    self.layout.operator(ImportSceneVMT.bl_idname, text="Valve Material Type (.vmt)")
    self.layout.operator(ImportSceneQC.bl_idname, text="Source Engine Model (enhanced) (.qc)")
    # self.layout.operator(ImportSceneMDL.bl_idname, text="Source Engine Model (enhanced) (.mdl)")
    self.layout.operator(ImportSceneAGREnhanced.bl_idname, text="HLAE afxGameRecord (enhanced) (.agr)")


def register() -> None:
    for cls in classes:
        bpy.utils.register_class(cls)
    bpy.types.TOPBAR_MT_file_import.append(import_menu_func)


def unregister() -> None:
    for cls in classes:
        bpy.utils.unregister_class(cls)
    bpy.types.TOPBAR_MT_file_import.remove(import_menu_func)
