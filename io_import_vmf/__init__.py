import bpy
import sys
import os
from os.path import join, relpath, abspath, dirname, basename, splitext, isdir, isabs
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
    "version": (0, 3, 1),
    "location": "File > Import",
    "warning": "",
    "tracker_url": "https://github.com/lasa01/io_import_vmf",
    "category": "Import-Export"
}


class ValveGameDir(bpy.types.PropertyGroup):
    def get_dirpath(self) -> str:
        return self["dirpath"]

    def set_dirpath(self, value: str) -> None:
        self["dirpath"] = bpy.path.abspath(value)

    dirpath: bpy.props.StringProperty(  # type: ignore
        name="Directory path", default="", subtype='DIR_PATH',
        get=get_dirpath, set=set_dirpath,
    )


class ValveGameDirList(bpy.types.UIList):
    bl_idname = "IO_IMPORT_VMF_UL_valvedirslist"

    def draw_item(self, context: bpy.types.Context, layout: bpy.types.UILayout,
                  data: 'ValveGameSettings', item: ValveGameDir,
                  icon: int, active_data: int, active_propname: str) -> None:
        if self.layout_type in {'DEFAULT', 'COMPACT'}:
            layout.prop(item, "dirpath", text="", emboss=False, icon_value=icon)
        elif self.layout_type in {'GRID'}:
            layout.alignment = 'CENTER'
            layout.label(text=item.dirpath, icon_value=icon)


class AddValveDirOperator(bpy.types.Operator):
    """Add a new empty game directory definition to the selected game"""
    bl_idname = "io_import_vmf.valvedir_add"
    bl_label = "Add a Valve game directory definition"
    bl_options = {'REGISTER', 'UNDO'}

    @classmethod
    def poll(cls, context: bpy.types.Context) -> bool:
        return bool(context.preferences.addons[__package__].preferences.games)

    def execute(self, context: bpy.types.Context) -> Set[str]:
        preferences: ValveGameAddonPreferences = context.preferences.addons[__package__].preferences
        game: ValveGameSettings = preferences.games[preferences.game_index]
        game.gamedirs.add()
        game.gamedir_index = len(game.gamedirs) - 1
        return {'FINISHED'}


class RemoveValveDirOperator(bpy.types.Operator):
    """Remove the selected game directory definition from the selected game"""
    bl_idname = "io_import_vmf.valvedir_remove"
    bl_label = "Remove a Valve game directory definition"
    bl_options = {'REGISTER', 'UNDO'}

    @classmethod
    def poll(cls, context: bpy.types.Context) -> bool:
        preferences: ValveGameAddonPreferences = context.preferences.addons[__package__].preferences
        return bool(preferences.games) and bool(preferences.games[preferences.game_index].gamedirs)

    def execute(self, context: bpy.types.Context) -> Set[str]:
        preferences: ValveGameAddonPreferences = context.preferences.addons[__package__].preferences
        game: ValveGameSettings = preferences.games[preferences.game_index]
        game.gamedirs.remove(game.gamedir_index)
        game.gamedir_index = min(max(0, game.gamedir_index - 1), len(game.gamedirs) - 1)
        return {'FINISHED'}


class ValveGamePak(bpy.types.PropertyGroup):
    def get_filepath(self) -> str:
        return self["filepath"]

    def set_filepath(self, value: str) -> None:
        self["filepath"] = bpy.path.abspath(value)

    filepath: bpy.props.StringProperty(  # type: ignore
        name="VPK path", default="", subtype='FILE_PATH',
        get=get_filepath, set=set_filepath,
    )


class ValveGamePakList(bpy.types.UIList):
    bl_idname = "IO_IMPORT_VMF_UL_valvepakslist"

    def draw_item(self, context: bpy.types.Context, layout: bpy.types.UILayout,
                  data: 'ValveGameSettings', item: ValveGamePak,
                  icon: int, active_data: int, active_propname: str) -> None:
        if self.layout_type in {'DEFAULT', 'COMPACT'}:
            layout.prop(item, "filepath", text="", emboss=False, icon_value=icon)
        elif self.layout_type in {'GRID'}:
            layout.alignment = 'CENTER'
            layout.label(text=item.filepath, icon_value=icon)


class AddValvePakOperator(bpy.types.Operator):
    """Add a new empty VPK archive definition to the selected game"""
    bl_idname = "io_import_vmf.valvepak_add"
    bl_label = "Add a Valve game pak definition"
    bl_options = {'REGISTER', 'UNDO'}

    @classmethod
    def poll(cls, context: bpy.types.Context) -> bool:
        return bool(context.preferences.addons[__package__].preferences.games)

    def execute(self, context: bpy.types.Context) -> Set[str]:
        preferences: ValveGameAddonPreferences = context.preferences.addons[__package__].preferences
        game: ValveGameSettings = preferences.games[preferences.game_index]
        game.pakfiles.add()
        game.pakfile_index = len(game.pakfiles) - 1
        return {'FINISHED'}


class RemoveValvePakOperator(bpy.types.Operator):
    """Remove the selected VPK archive definition from the selected game"""
    bl_idname = "io_import_vmf.valvepak_remove"
    bl_label = "Remove a Valve game pak definition"
    bl_options = {'REGISTER', 'UNDO'}

    @classmethod
    def poll(cls, context: bpy.types.Context) -> bool:
        preferences: ValveGameAddonPreferences = context.preferences.addons[__package__].preferences
        return bool(preferences.games) and bool(preferences.games[preferences.game_index].pakfiles)

    def execute(self, context: bpy.types.Context) -> Set[str]:
        preferences: ValveGameAddonPreferences = context.preferences.addons[__package__].preferences
        game: ValveGameSettings = preferences.games[preferences.game_index]
        game.pakfiles.remove(game.pakfile_index)
        game.pakfile_index = min(max(0, game.pakfile_index - 1), len(game.pakfiles) - 1)
        return {'FINISHED'}


class ValveGameWildcardDir(bpy.types.PropertyGroup):
    def get_dirpath(self) -> str:
        return self["dirpath"]

    def set_dirpath(self, value: str) -> None:
        self["dirpath"] = bpy.path.abspath(value)

    dirpath: bpy.props.StringProperty(  # type: ignore
        name="Directory path", default="", subtype='DIR_PATH',
        get=get_dirpath, set=set_dirpath,
    )


class ValveGameWildcardDirList(bpy.types.UIList):
    bl_idname = "IO_IMPORT_VMF_UL_valvewildcarddirslist"

    def draw_item(self, context: bpy.types.Context, layout: bpy.types.UILayout,
                  data: 'ValveGameSettings', item: ValveGameWildcardDir,
                  icon: int, active_data: int, active_propname: str) -> None:
        if self.layout_type in {'DEFAULT', 'COMPACT'}:
            layout.prop(item, "dirpath", text="", emboss=False, icon_value=icon)
        elif self.layout_type in {'GRID'}:
            layout.alignment = 'CENTER'
            layout.label(text=item.dirpath, icon_value=icon)


class AddValveWildcardDirOperator(bpy.types.Operator):
    """Add a new empty wildcard directory definition to the selected game"""
    bl_idname = "io_import_vmf.valvewildcarddir_add"
    bl_label = "Add a Valve wildcard directory definition"
    bl_options = {'REGISTER', 'UNDO'}

    @classmethod
    def poll(cls, context: bpy.types.Context) -> bool:
        return bool(context.preferences.addons[__package__].preferences.games)

    def execute(self, context: bpy.types.Context) -> Set[str]:
        preferences: ValveGameAddonPreferences = context.preferences.addons[__package__].preferences
        game: ValveGameSettings = preferences.games[preferences.game_index]
        game.wildcard_dirs.add()
        game.wildcard_dir_index = len(game.wildcard_dirs) - 1
        return {'FINISHED'}


class RemoveValveWildcardDirOperator(bpy.types.Operator):
    """Remove the selected wildcard directory definition from the selected game"""
    bl_idname = "io_import_vmf.valvewildcarddir_remove"
    bl_label = "Remove a Valve wildcard directory definition"
    bl_options = {'REGISTER', 'UNDO'}

    @classmethod
    def poll(cls, context: bpy.types.Context) -> bool:
        preferences: ValveGameAddonPreferences = context.preferences.addons[__package__].preferences
        return bool(preferences.games) and bool(preferences.games[preferences.game_index].wildcard_dirs)

    def execute(self, context: bpy.types.Context) -> Set[str]:
        preferences: ValveGameAddonPreferences = context.preferences.addons[__package__].preferences
        game: ValveGameSettings = preferences.games[preferences.game_index]
        game.wildcard_dirs.remove(game.wildcard_dir_index)
        game.wildcard_dir_index = min(max(0, game.wildcard_dir_index - 1), len(game.wildcard_dirs) - 1)
        return {'FINISHED'}


class ValveGameSettings(bpy.types.PropertyGroup):
    name: bpy.props.StringProperty(name="Name", default="Source Game")  # type: ignore

    pakfiles: bpy.props.CollectionProperty(type=ValveGamePak)  # type: ignore
    pakfile_index: bpy.props.IntProperty(name="Game VPK archive")  # type: ignore

    gamedirs: bpy.props.CollectionProperty(type=ValveGameDir)  # type: ignore
    gamedir_index: bpy.props.IntProperty(name="Game directory")  # type: ignore

    wildcard_dirs: bpy.props.CollectionProperty(type=ValveGameWildcardDir)  # type: ignore
    wildcard_dir_index: bpy.props.IntProperty(name="Game wildcard directory")  # type: ignore


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
    """Add a new empty Valve game definition"""
    bl_idname = "io_import_vmf.valvegame_add"
    bl_label = "Add an empty Valve game definition"
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context: bpy.types.Context) -> Set[str]:
        preferences: ValveGameAddonPreferences = context.preferences.addons[__package__].preferences
        preferences.games.add()
        preferences.game_index = len(preferences.games) - 1
        return {'FINISHED'}


class RemoveValveGameOperator(bpy.types.Operator):
    """Remove the selected Valve game definition"""
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


class DetectValveGameOperator(bpy.types.Operator):
    """Automatically detect VPKs inside a game directory and add them to the selected game definition"""
    bl_idname = "io_import_vmf.valvegame_detect"
    bl_label = "Detect Valve game data from a game directory"
    bl_options = {'REGISTER', 'UNDO'}

    directory: bpy.props.StringProperty(  # type: ignore
        name="Game directory path",
        subtype='DIR_PATH'
    )
    filter_folder: bpy.props.BoolProperty(default=True, options={'HIDDEN'})  # type: ignore

    @classmethod
    def poll(cls, context: bpy.types.Context) -> bool:
        return bool(context.preferences.addons[__package__].preferences.games)

    def invoke(self, context: bpy.types.Context, event: bpy.types.Event) -> Set[str]:
        context.window_manager.fileselect_add(self)
        return {'RUNNING_MODAL'}

    def execute(self, context: bpy.types.Context) -> Set[str]:
        game_dir = self.directory.rstrip("\\/")
        if not isdir(game_dir):
            self.report({'ERROR_INVALID_INPUT'}, "The specified game directory doesn't exist.")
            return {'CANCELLED'}
        game_id = basename(game_dir)
        name = basename(dirname(game_dir))
        pak_candidates = glob.glob(join(game_dir, "*_dir.vpk"))
        preferences: ValveGameAddonPreferences = context.preferences.addons[__package__].preferences
        game: ValveGameSettings = preferences.games[preferences.game_index]
        if game.name == "" or game.name == "Source Game":
            game.name = name
        gamedir: ValveGameDir = game.gamedirs.add()
        gamedir.dirpath = game_dir
        game.gamedir_index = len(game.gamedirs) - 1
        for pak_candidate in pak_candidates:
            pak_filename = basename(pak_candidate)
            if "pak01" not in pak_filename and game_id not in pak_filename:
                continue
            pakfile: ValveGamePak = game.pakfiles.add()
            pakfile.filepath = pak_candidate
        game.pakfile_index = len(game.pakfiles) - 1
        custom_path = join(game_dir, "custom").rstrip("\\/")
        if isdir(custom_path):
            custom_dir: ValveGameWildcardDir = game.wildcard_dirs.add()
            custom_dir.dirpath = custom_path
            game.wildcard_dir_index = len(game.wildcard_dirs) - 1
        return {'FINISHED'}


class ValveGameAddonPreferences(bpy.types.AddonPreferences):
    bl_idname = __package__

    games: bpy.props.CollectionProperty(type=ValveGameSettings)  # type: ignore
    game_index: bpy.props.IntProperty(name="Game definition")  # type: ignore

    def get_dec_models_path(self) -> str:
        return self["dec_models_path"]

    def set_dec_models_path(self, value: str) -> None:
        self["dec_models_path"] = bpy.path.abspath(value)

    dec_models_path: bpy.props.StringProperty(  # type: ignore
        name="Models path",
        default="",
        description="Path to the directory for decompiled models.",
        subtype='DIR_PATH',
        get=get_dec_models_path, set=set_dec_models_path,
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
            box.operator("io_import_vmf.valvegame_detect", text="Detect from a game directory", icon='FILE_FOLDER')
            box.label(text="Game directories:")
            row = box.row()
            row.template_list("IO_IMPORT_VMF_UL_valvedirslist", "", game, "gamedirs", game, "gamedir_index")
            col = row.column()
            col.operator("io_import_vmf.valvedir_add", text="", icon='ADD')
            col.operator("io_import_vmf.valvedir_remove", text="", icon='REMOVE')
            box.label(text="Game VPK archives:")
            row = box.row()
            row.template_list("IO_IMPORT_VMF_UL_valvepakslist", "", game, "pakfiles", game, "pakfile_index")
            col = row.column()
            col.operator("io_import_vmf.valvepak_add", text="", icon='ADD')
            col.operator("io_import_vmf.valvepak_remove", text="", icon='REMOVE')
            box.label(text="Game wildcard directories:")
            box.label(text="Every VPK file and subdirectory inside these directories will be searched.", icon='INFO')
            row = box.row()
            row.template_list("IO_IMPORT_VMF_UL_valvewildcarddirslist", "",
                              game, "wildcard_dirs", game, "wildcard_dir_index")
            col = row.column()
            col.operator("io_import_vmf.valvewildcarddir_add", text="", icon='ADD')
            col.operator("io_import_vmf.valvewildcarddir_remove", text="", icon='REMOVE')
        layout.separator_spacer()
        layout.prop(self, "dec_models_path")
        layout.label(text="Specifies a persistent path to save decompiled models to.", icon='INFO')


class ValveGameOpenPreferencesOperator(bpy.types.Operator):
    """Open the preferences of the VMF importer"""
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
    data_dirs: List[str]
    data_paks: List[str]

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
            self.data_paks = [pak.filepath for pak in game_def.pakfiles]
            self.data_dirs = [gamedir.dirpath for gamedir in game_def.gamedirs]
            for wildcard_dir in game_def.wildcard_dirs:
                for dir_entry in os.scandir(wildcard_dir.dirpath):
                    if dir_entry.is_dir():
                        self.data_dirs.append(dir_entry.path)
                    elif dir_entry.name.endswith(".vpk"):
                        self.data_paks.append(dir_entry.path)
        else:
            self.data_paks = []
            self.data_dirs = []
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

    def _check_vmf_props(self) -> Optional[Set[str]]:
        map_data_path: str = self.map_data_path_prop
        if map_data_path == "":
            map_data_path = splitext(self.filepath)[0]
            if not isdir(map_data_path):
                self.map_data_path = None
            else:
                self.map_data_path = map_data_path
        else:
            if not isabs(map_data_path):
                map_data_path = join(dirname(self.filepath), map_data_path)
            if not isdir(map_data_path):
                self.report({'ERROR_INVALID_INPUT'}, "The specified embedded files directory doesn't exist.")
                return {'CANCELLED'}
            self.map_data_path = map_data_path
        return None


class ExportVMFMDLs(_VMFOperator, _VMFOperatorProps):
    """Export required MDL files for a VMF"""
    bl_idname = "export.vmf_mdls"
    bl_label = "Export VMF MDLs for decompilation"
    bl_options: Set[str] = set()

    out_path: bpy.props.StringProperty(name="Output directory", default="",  # type: ignore
                                       description="Leave empty to use a directory next to input file")

    def execute(self, context: bpy.types.Context) -> Set[str]:
        result = self._check_valve_props(context)
        if result is not None:
            return result
        result = self._check_vmf_props()
        if result is not None:
            return result
        if self.out_path == "":
            self.out_path = join(dirname(self.filepath), f"{splitext(basename(self.filepath))[0]}_models")
        os.makedirs(self.out_path, exist_ok=True)
        print(f"Output path: {self.out_path}")
        print(f"Map data path: {self.map_data_path}")
        print("Loading VMF...")
        import vmfpy
        print("Indexing game files...")
        data_dirs = self.data_dirs + [self.map_data_path] if self.map_data_path is not None else self.data_dirs
        vmf_fs = vmfpy.VMFFileSystem(data_dirs, self.data_paks, index_files=True)
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
    """Load a Source Engine VMF file"""
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
        name="Skip invisible brushes",
        description="Skip importing brushes containing only invisible textures.",
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

    optimize_props: bpy.props.BoolProperty(  # type: ignore
        name="Optimize props",
        default=True,
        description="Removes unnecessary armatures with 1 bone and animations with 1 frame from static props",
    )

    import_lights: bpy.props.BoolProperty(  # type: ignore
        name="Import lights",
        default=True,
    )

    import_sky_origin: bpy.props.BoolProperty(  # type: ignore
        name="Import 3D sky origin",
        default=True,
    )

    import_sky: bpy.props.BoolProperty(  # type: ignore
        name="Import sky",
        default=True,
    )

    sky_resolution: bpy.props.IntProperty(  # type: ignore
        name="Sky resolution",
        description="The imported sky texture height in pixels. Higher values increase quality.",
        min=1, max=32768,
        soft_min=256, soft_max=8192,
        default=1024,
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

    texture_interpolation: bpy.props.EnumProperty(  # type: ignore
        name="Texture interpolation",
        description="Interpolation type to use for image textures.",
        items=[
            ('Linear', "Linear", "Linear interpolation"),
            ('Closest', "Closest", "No interpolation"),
            ('Cubic', "Cubic", "Cubic interpolation"),
            ('Smart', "Smart", "Bicubic when magnifying, else bilinear"),
        ],
        default='Linear',
    )

    cull_materials: bpy.props.BoolProperty(  # type: ignore
        name="Allow backface culling",
        description="Enable backface culling for materials which don't disable it.",
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
        # self.mdl_available = "SourceIO" in context.preferences.addons
        self.qc_available = "io_scene_valvesource" in context.preferences.addons
        return super().invoke(context, event)

    def execute(self, context: bpy.types.Context) -> Set[str]:
        result = self._check_valve_props(context)
        if result is not None:
            return result
        result = self._check_vmf_props()
        if result is not None:
            return result
        preferences: ValveGameAddonPreferences = context.preferences.addons[__package__].preferences
        dec_models_path = preferences.dec_models_path
        delete_files = False
        if dec_models_path == "":
            delete_files = True
            dec_models_path = join(context.preferences.filepaths.temporary_directory, "blender_io_import_vmf_models")
        from . import import_vmf
        importer = import_vmf.VMFImporter(self.data_dirs, self.data_paks, dec_models_path,
                                          import_solids=self.import_solids, import_overlays=self.import_overlays,
                                          import_props=self.import_props, optimize_props=self.optimize_props,
                                          import_sky_origin=self.import_sky_origin,
                                          import_sky=self.import_sky, sky_resolution=self.sky_resolution,
                                          import_materials=self.import_materials,
                                          simple_materials=self.simple_materials, cull_materials=self.cull_materials,
                                          texture_interpolation=self.texture_interpolation,
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
            # NOTE: Imports invalid rotation, disabled
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
            box.prop(self, "optimize_props")
        if not self.qc_available:
            self.import_props = False
            col.enabled = False
            col.label(text="Blender Source tools must be installed to import props.")
        if self.import_solids or self.import_props:
            layout.prop(self, "import_materials")
            if self.import_materials:
                box = layout.box()
                box.alignment = 'RIGHT'
                box.prop(self, "simple_materials")
                box.prop(self, "texture_interpolation")
                box.prop(self, "cull_materials")
        layout.prop(self, "import_lights")
        if self.import_lights:
            box = layout.box()
            box.prop(self, "light_factor")
            box.prop(self, "sun_factor")
            box.prop(self, "ambient_factor")
        layout.prop(self, "import_sky_origin")
        layout.prop(self, "import_sky")
        if self.import_sky:
            box = layout.box()
            box.prop(self, "sky_resolution")
        layout.separator_spacer()
        layout.prop(self, "global_scale")
        layout.prop(self, "verbose")


class ObjectTransform3DSky(bpy.types.Operator):
    """Transform the selected 3D sky objects, based on the active empty object"""
    bl_idname = "object.transform_3d_sky"
    bl_label = "Transform VMF 3D sky"
    bl_options = {'REGISTER', 'UNDO'}

    @classmethod
    def poll(cls, context: bpy.types.Context) -> bool:
        return (context.active_object and context.active_object.type == 'EMPTY') and context.selected_objects

    def execute(self, context: bpy.types.Context) -> Set[str]:
        target = context.active_object
        for obj in context.selected_objects:
            if obj != target and obj.parent is None:
                obj.parent = target
                obj.location -= target.location
        target.location = (0, 0, 0)
        return {'FINISHED'}


def _get_source_path_root(path: str, stop: str = "models") -> Optional[str]:
    while True:
        new_path = dirname(path)
        if new_path == path:
            return None
        path = new_path
        if basename(path) == stop:
            break
    return dirname(path)


class ImportSceneQC(_ValveGameOperator, _ValveGameOperatorProps):
    """Load a Source Engine QC file"""
    bl_idname = "import_scene.qc_enhanced"
    bl_label = "Import QC (enhanced)"
    bl_options = {'UNDO', 'PRESET'}

    filepath: bpy.props.StringProperty(subtype='FILE_PATH', options={'HIDDEN'})  # type: ignore
    filter_glob: bpy.props.StringProperty(default="*.qc", options={'HIDDEN'})  # type: ignore

    import_materials: bpy.props.BoolProperty(  # type: ignore
        name="Import materials",
        default=True,
    )

    simple_materials: bpy.props.BoolProperty(  # type: ignore
        name="Simple materials",
        description="Import simple, exporter-friendly versions of materials.",
        default=False,
    )

    texture_interpolation: bpy.props.EnumProperty(  # type: ignore
        name="Texture interpolation",
        description="Interpolation type to use for image textures.",
        items=[
            ('Linear', "Linear", "Linear interpolation"),
            ('Closest', "Closest", "No interpolation"),
            ('Cubic', "Cubic", "Cubic interpolation"),
            ('Smart', "Smart", "Bicubic when magnifying, else bilinear"),
        ],
        default='Linear',
    )

    cull_materials: bpy.props.BoolProperty(  # type: ignore
        name="Allow backface culling",
        description="Enable backface culling for materials which don't disable it.",
        default=False,
    )

    verbose: bpy.props.BoolProperty(  # type: ignore
        name="Verbose",
        description="Enable to print more info into console",
        default=False,
    )

    @classmethod
    def poll(cls, context: bpy.types.Context) -> bool:
        return "io_scene_valvesource" in context.preferences.addons

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
        if root is None:
            root = dirname(self.filepath)
        importer = import_qc.QCImporter(
            root,
            fs,
            import_vmt.VMTImporter(self.verbose, self.simple_materials, self.texture_interpolation, self.cull_materials)
            if self.import_materials else None,
            self.verbose,
        )
        with importer:
            importer.load(splitext(relpath(self.filepath, root))[0], context.collection)
        return {'FINISHED'}

    def draw(self, context: bpy.types.Context) -> None:
        layout: bpy.types.UILayout = self.layout
        super().draw(context)
        layout.prop(self, "import_materials")
        if self.import_materials:
            box = layout.box()
            box.alignment = 'RIGHT'
            box.prop(self, "simple_materials")
            box.prop(self, "texture_interpolation")
            box.prop(self, "cull_materials")
        layout.prop(self, "verbose")


class ImportSceneMDL(_ValveGameOperator, _ValveGameOperatorProps):
    """Load a Source Engine MDL file"""
    bl_idname = "import_scene.mdl_enhanced"
    bl_label = "Import MDL (enhanced)"
    bl_options = {'UNDO', 'PRESET'}

    filepath: bpy.props.StringProperty(subtype='FILE_PATH', options={'HIDDEN'})  # type: ignore
    filter_glob: bpy.props.StringProperty(default="*.mdl", options={'HIDDEN'})  # type: ignore

    import_materials: bpy.props.BoolProperty(  # type: ignore
        name="Import materials",
        default=True,
    )

    simple_materials: bpy.props.BoolProperty(  # type: ignore
        name="Simple materials",
        description="Import simple, exporter-friendly versions of materials.",
        default=False,
    )

    texture_interpolation: bpy.props.EnumProperty(  # type: ignore
        name="Texture interpolation",
        description="Interpolation type to use for image textures.",
        items=[
            ('Linear', "Linear", "Linear interpolation"),
            ('Closest', "Closest", "No interpolation"),
            ('Cubic', "Cubic", "Cubic interpolation"),
            ('Smart', "Smart", "Bicubic when magnifying, else bilinear"),
        ],
        default='Linear',
    )

    cull_materials: bpy.props.BoolProperty(  # type: ignore
        name="Allow backface culling",
        description="Enable backface culling for materials which don't disable it.",
        default=False,
    )

    verbose: bpy.props.BoolProperty(  # type: ignore
        name="Verbose",
        description="Enable to print more info into console",
        default=False,
    )

    @classmethod
    def poll(cls, context: bpy.types.Context) -> bool:
        return "SourceIO" in context.preferences.addons

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
        if root is None:
            root = ""
        print("Indexing game files...")
        fs = VMFFileSystem(self.data_dirs, self.data_paks, index_files=True)
        print("Importing model...")
        importer = import_mdl.MDLImporter(
            fs,
            import_vmt.VMTImporter(self.verbose, self.simple_materials, self.texture_interpolation, self.cull_materials)
            if self.import_materials else None,
            self.verbose,
        )
        importer.load(splitext(relpath(self.filepath, root))[0], self.filepath, context.collection)
        return {'FINISHED'}

    def draw(self, context: bpy.types.Context) -> None:
        layout: bpy.types.UILayout = self.layout
        super().draw(context)
        layout.prop(self, "import_materials")
        if self.import_materials:
            box = layout.box()
            box.alignment = 'RIGHT'
            box.prop(self, "simple_materials")
            box.prop(self, "texture_interpolation")
            box.prop(self, "cull_materials")
        layout.prop(self, "verbose")


class ImportSceneVMT(_ValveGameOperator, _ValveGameOperatorProps):
    """Load a Source Engine VMT file"""
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

    texture_interpolation: bpy.props.EnumProperty(  # type: ignore
        name="Texture interpolation",
        description="Interpolation type to use for image textures.",
        items=[
            ('Linear', "Linear", "Linear interpolation"),
            ('Closest', "Closest", "No interpolation"),
            ('Cubic', "Cubic", "Cubic interpolation"),
            ('Smart', "Smart", "Bicubic when magnifying, else bilinear"),
        ],
        default='Linear',
    )

    cull_materials: bpy.props.BoolProperty(  # type: ignore
        name="Allow backface culling",
        description="Enable backface culling for materials which don't disable it.",
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
        root = _get_source_path_root(self.filepath, "materials")
        if root is not None and root not in self.data_dirs:
            self.data_dirs.append(root)
        fs = VMFFileSystem(self.data_dirs, self.data_paks, index_files=True)
        print("Loading material...")
        importer = import_vmt.VMTImporter(self.verbose, self.simple_materials,
                                          self.texture_interpolation, self.cull_materials)
        importer.load(
            splitext(basename(self.filepath))[0],
            lambda: VMT(open(self.filepath, encoding='utf-8'), fs, allow_patch=True)
        )
        return {'FINISHED'}

    def draw(self, context: bpy.types.Context) -> None:
        layout: bpy.types.UILayout = self.layout
        super().draw(context)
        layout.prop(self, "simple_materials")
        layout.prop(self, "texture_interpolation")
        layout.prop(self, "cull_materials")
        layout.prop(self, "verbose")


class ImportSceneAGREnhanced(_ValveGameOperator, _ValveGameOperatorProps):
    """Load a HLAE AGR file"""
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

    texture_interpolation: bpy.props.EnumProperty(  # type: ignore
        name="Texture interpolation",
        description="Interpolation type to use for image textures.",
        items=[
            ('Linear', "Linear", "Linear interpolation"),
            ('Closest', "Closest", "No interpolation"),
            ('Cubic', "Cubic", "Cubic interpolation"),
            ('Smart', "Smart", "Bicubic when magnifying, else bilinear"),
        ],
        default='Linear',
    )

    cull_materials: bpy.props.BoolProperty(  # type: ignore
        name="Allow backface culling",
        description="Enable backface culling for materials which don't disable it.",
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

    @classmethod
    def poll(cls, context: bpy.types.Context) -> bool:
        return "advancedfx" in context.preferences.addons

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
            texture_interpolation=self.texture_interpolation, cull_materials=self.cull_materials,
            verbose=self.verbose,
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
            box.alignment = 'RIGHT'
            box.prop(self, "simple_materials")
            box.prop(self, "texture_interpolation")
            box.prop(self, "cull_materials")
        layout.prop(self, "inter_key")
        layout.prop(self, "global_scale")
        layout.prop(self, "scale_invisible_zero")
        layout.prop(self, "verbose")


classes = (
    ValveGameDir,
    ValveGameDirList,
    AddValveDirOperator,
    RemoveValveDirOperator,
    ValveGamePak,
    ValveGamePakList,
    AddValvePakOperator,
    RemoveValvePakOperator,
    ValveGameWildcardDir,
    ValveGameWildcardDirList,
    AddValveWildcardDirOperator,
    RemoveValveWildcardDirOperator,
    ValveGameSettings,
    ValveGameSettingsList,
    AddValveGameOperator,
    RemoveValveGameOperator,
    DetectValveGameOperator,
    ValveGameAddonPreferences,
    ValveGameOpenPreferencesOperator,
    ExportVMFMDLs,
    ImportSceneVMF,
    ImportSceneQC,
    ImportSceneMDL,
    ImportSceneVMT,
    ImportSceneAGREnhanced,
    ObjectTransform3DSky,
)


def import_menu_func(self: bpy.types.Menu, context: bpy.types.Context) -> None:
    self.layout.operator(ImportSceneVMF.bl_idname, text="Valve Map Format (.vmf)")
    self.layout.operator(ImportSceneVMT.bl_idname, text="Valve Material Type (.vmt)")
    self.layout.operator(ImportSceneQC.bl_idname, text="Source Engine Model (enhanced) (.qc)")
    self.layout.operator(ImportSceneMDL.bl_idname, text="Source Engine Model (enhanced) (.mdl)")
    self.layout.operator(ImportSceneAGREnhanced.bl_idname, text="HLAE afxGameRecord (enhanced) (.agr)")


def object_menu_func(self: bpy.types.Menu, context: bpy.types.Context) -> None:
    self.layout.separator()
    self.layout.operator(ObjectTransform3DSky.bl_idname)


def register() -> None:
    for cls in classes:
        bpy.utils.register_class(cls)
    bpy.types.TOPBAR_MT_file_import.append(import_menu_func)
    bpy.types.VIEW3D_MT_object.append(object_menu_func)


def unregister() -> None:
    for cls in classes:
        bpy.utils.unregister_class(cls)
    bpy.types.TOPBAR_MT_file_import.remove(import_menu_func)
    bpy.types.VIEW3D_MT_object.remove(object_menu_func)
