import bpy
from .utils import filesystemify
import sys
import os
from os.path import join, relpath, abspath, dirname, basename, splitext, isdir, isabs
from shutil import rmtree
import glob
import time
from typing import Set, Optional, Tuple, List, Dict, Sequence, Iterator
sys.path.append(join(dirname(abspath(__file__)), "deps"))
from vmfpy.fs import VMFFileSystem  # noqa: 402


bl_info = {
    "name": "Import Valve Map Format / Valve Material Type",
    "author": "Lassi Säike",
    "description": "Import Valve Map Format (VMF) and Valve Material Type (VMT) files.",
    "blender": (2, 82, 0),
    "version": (0, 5, 1),
    "location": "File > Import",
    "warning": "",
    "tracker_url": "https://github.com/lasa01/io_import_vmf",
    "category": "Import-Export"
}


class ValveGameDir(bpy.types.PropertyGroup):
    def get_dirpath(self) -> str:
        return self.get("dirpath", "")

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
        return self.get("filepath", "")

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
        return self.get("dirpath", "")

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


fs_dict: Dict[str, VMFFileSystem] = {}


class ValveGameSettings(bpy.types.PropertyGroup):
    def get_name(self) -> str:
        return self.get("name", "")

    def set_name(self, value: str) -> None:
        preferences: 'ValveGameAddonPreferences' = bpy.context.preferences.addons[__package__].preferences
        for game in preferences.games:
            if game == self:
                continue
            if game.name == value:
                number = 1
                while any(game.name == f"{value} {number}" for game in preferences.games):
                    number += 1
                value = f"{value} {number}"
                break
        cache_path = preferences.cache_path
        if self.name != "" and cache_path != "" and value != "":
            old_dir = join(cache_path, filesystemify(self.name))
            if isdir(old_dir):
                os.rename(old_dir, join(cache_path, filesystemify(value)))
        self["name"] = value

    name: bpy.props.StringProperty(  # type: ignore
        name="Name", default="Source Game",
        get=get_name, set=set_name,
    )

    pakfiles: bpy.props.CollectionProperty(type=ValveGamePak)  # type: ignore
    pakfile_index: bpy.props.IntProperty(name="Game VPK archive")  # type: ignore

    gamedirs: bpy.props.CollectionProperty(type=ValveGameDir)  # type: ignore
    gamedir_index: bpy.props.IntProperty(name="Game directory")  # type: ignore

    wildcard_dirs: bpy.props.CollectionProperty(type=ValveGameWildcardDir)  # type: ignore
    wildcard_dir_index: bpy.props.IntProperty(name="Game wildcard directory")  # type: ignore

    def get_indexed_filesystem(self) -> VMFFileSystem:
        global fs_dict
        if self.name in fs_dict:
            print("Game files already indexed")
            return fs_dict[self.name]
        data_paks = [pak.filepath for pak in self.pakfiles]
        data_dirs = [gamedir.dirpath for gamedir in self.gamedirs]
        for wildcard_dir in self.wildcard_dirs:
            for dir_entry in os.scandir(wildcard_dir.dirpath):
                if dir_entry.is_dir():
                    data_dirs.append(dir_entry.path)
                elif dir_entry.name.endswith(".vpk"):
                    data_paks.append(dir_entry.path)
        print("Indexing game files...")
        start = time.time()
        fs_dict[self.name] = VMFFileSystem(data_dirs, data_paks, index_files=True)
        print(f"Indexing done in {time.time() - start} s")
        return fs_dict[self.name]

    def get_dec_models_path(self, context: bpy.types.Context) -> Tuple[bool, str]:
        preferences: ValveGameAddonPreferences = context.preferences.addons[__package__].preferences
        cache_path = preferences.cache_path
        if cache_path == "":
            return True, join(
                context.preferences.filepaths.temporary_directory,
                "blender_io_import_vmf_cache",
                "dec_models",
            )
        return False, join(cache_path, filesystemify(self.name), "dec_models")


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

    def get_cache_path(self) -> str:
        return self.get("cache_path", "")

    def set_cache_path(self, value: str) -> None:
        self["cache_path"] = bpy.path.abspath(value)

    cache_path: bpy.props.StringProperty(  # type: ignore
        name="Cache directory path",
        default="",
        description="A path to cache external game assets into for faster reimports",
        subtype='DIR_PATH',
        get=get_cache_path, set=set_cache_path,
    )

    @staticmethod
    def game_enum_items(self: bpy.types.EnumProperty, context: bpy.types.Context) -> List[Tuple[str, str, str]]:
        preferences: ValveGameAddonPreferences = context.preferences.addons[__package__].preferences
        items = [(str(i), game.name, "") for i, game in enumerate(preferences.games.values())]
        items.append(('NONE', "None", ""))
        return items

    def draw(self, context: bpy.types.Context) -> None:
        layout: bpy.types.UILayout = self.layout
        layout.prop(self, "cache_path")
        layout.separator_spacer()
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


class ValveGameOpenPreferencesOperator(bpy.types.Operator):
    """Open the preferences of the VMF importer"""
    bl_idname = "io_import_vmf.open_preferences"
    bl_label = "Open Valve game definition preferences"
    bl_options = {'INTERNAL'}

    def execute(self, context: bpy.types.Context) -> Set[str]:
        bpy.ops.preferences.addon_show('INVOKE_SCREEN', module=__package__)
        return {'FINISHED'}


class _ValveGameOperatorProps():
    game: bpy.props.EnumProperty(  # type: ignore
        items=ValveGameAddonPreferences.game_enum_items,
        name="Game definition",
        description="Used for searching files",
    )

    verbose: bpy.props.BoolProperty(  # type: ignore
        name="Verbose",
        description="Enable to print more info into Blender console",
        default=False,
    )


class _ValveGameOperator(bpy.types.Operator, _ValveGameOperatorProps):
    def get_filesystem(self, context: bpy.types.Context) -> Optional[VMFFileSystem]:
        if self.game == 'NONE':
            return None
        preferences: ValveGameAddonPreferences = context.preferences.addons[__package__].preferences
        game_def: ValveGameSettings = preferences.games[int(self.game)]
        return game_def.get_indexed_filesystem()

    def get_dec_models_path(self, context: bpy.types.Context) -> Tuple[bool, str]:
        if self.game == 'NONE':
            return True, join(
                context.preferences.filepaths.temporary_directory,
                "blender_io_import_vmf_cache",
                "dec_models",
            )
        preferences: ValveGameAddonPreferences = context.preferences.addons[__package__].preferences
        game_def: ValveGameSettings = preferences.games[int(self.game)]
        return game_def.get_dec_models_path(context)

    def invoke(self, context: bpy.types.Context, event: bpy.types.Event) -> Set[str]:
        context.window_manager.fileselect_add(self)
        return {'RUNNING_MODAL'}


class VMF_PT_valve_games(bpy.types.Panel):
    bl_space_type = 'FILE_BROWSER'
    bl_region_type = 'TOOL_PROPS'
    bl_label = ""
    bl_parent_id = "FILE_PT_operator"
    bl_options = {'HIDE_HEADER'}

    @classmethod
    def poll(cls, context: bpy.types.Context) -> bool:
        operator = context.space_data.active_operator
        return isinstance(operator, _ValveGameOperatorProps)

    def draw(self, context: bpy.types.Context) -> None:
        layout: bpy.types.UILayout = self.layout
        layout.use_property_split = True
        layout.use_property_decorate = False
        preferences: ValveGameAddonPreferences = context.preferences.addons[__package__].preferences
        operator = context.space_data.active_operator
        layout.prop(operator, "verbose")
        layout.prop(operator, "game")
        if not preferences.games:
            row = layout.box().row()
            row.alignment = 'RIGHT'
            row.label(text="Open preferences to add game definitions.", icon='INFO')
            row.operator("io_import_vmf.open_preferences", text="", icon='PREFERENCES')


class ImportSceneVMF(_ValveGameOperator, _ValveGameOperatorProps):
    """Load a Source Engine VMF file"""
    bl_idname = "import_scene.vmf"
    bl_label = "Import VMF"
    bl_options = {'UNDO', 'PRESET'}

    filepath: bpy.props.StringProperty(subtype='FILE_PATH', options={'HIDDEN'})  # type: ignore
    filter_glob: bpy.props.StringProperty(default="*.vmf", options={'HIDDEN'})  # type: ignore

    map_data_path_prop: bpy.props.StringProperty(name="Embedded files path", default="",  # type: ignore
                                                 description="Leave empty to auto-detect")

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

    invisible_behaviour: bpy.props.EnumProperty(  # type: ignore
        name="Invisible brushes",
        items=(
            ('NORMAL', "Normal", "Invisible brushes will be imported normally."),
            ('SKIP', "Skip", "Invisible brushes will not be imported."),
            ('SEPARATE', "Separate", "Invisible brushes will be imported into a separate collection."),
        ),
        default='SKIP',
    )

    import_overlays: bpy.props.BoolProperty(  # type: ignore
        name="Import overlays",
        default=True,
    )

    import_props: bpy.props.BoolProperty(  # type: ignore
        name="Import props",
        default=True,
        description="SourceIO or Blender Source Tools must be installed for this to work",
    )

    skip_collision: bpy.props.BoolProperty(  # type: ignore
        name="Skip collision meshes",
        default=True,
        description="Skips importing collision meshes",
    )

    skip_lod: bpy.props.BoolProperty(  # type: ignore
        name="Skip LOD meshes",
        default=True,
        description="Skips importing LOD meshes",
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
        description="The imported sky texture height in pixels. Higher values increase quality",
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
        description="Import simple, exporter-friendly versions of materials",
        default=False,
    )

    texture_interpolation: bpy.props.EnumProperty(  # type: ignore
        name="Texture interpolation",
        description="Interpolation type to use for image textures",
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
        description="Enable backface culling for materials which don't disable it",
        default=False,
    )

    reuse_old_materials: bpy.props.BoolProperty(  # type: ignore
        name="Reuse old materials",
        description="Reuse previously imported materials and images instead of reimporting them",
        default=True,
    )

    reuse_old_models: bpy.props.BoolProperty(  # type: ignore
        name="Reuse old models",
        description="Reuse previously imported models instead of reimporting them",
        default=True,
    )

    global_scale: bpy.props.FloatProperty(  # type: ignore
        name="Scale",
        description="Scale everything by this value",
        min=0.000001, max=1000000.0,
        soft_min=0.001, soft_max=1.0,
        default=0.01,
    )

    # mdl_available = False
    qc_available = False

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

    def invoke(self, context: bpy.types.Context, event: bpy.types.Event) -> Set[str]:
        # self.mdl_available = "SourceIO" in context.preferences.addons
        self.qc_available = "io_scene_valvesource" in context.preferences.addons
        return super().invoke(context, event)

    def execute(self, context: bpy.types.Context) -> Set[str]:
        result = self._check_vmf_props()
        if result is not None:
            return result
        delete_files = False
        dec_models_path = None
        if self.import_props or self.import_materials or self.import_sky:
            fs = self.get_filesystem(context)
            if fs is None:
                self.report({'ERROR_INVALID_INPUT'}, "A game must be specified for the current import settings.")
                return {'CANCELLED'}
            delete_files, dec_models_path = self.get_dec_models_path(context)
        else:
            fs = None
        from . import import_vmf
        importer = import_vmf.VMFImporter(fs, dec_models_path,
                                          import_solids=self.import_solids, import_overlays=self.import_overlays,
                                          import_props=self.import_props, optimize_props=self.optimize_props,
                                          skip_collision=self.skip_collision, skip_lod=self.skip_lod,
                                          import_sky_origin=self.import_sky_origin,
                                          import_sky=self.import_sky, sky_resolution=self.sky_resolution,
                                          import_materials=self.import_materials,
                                          simple_materials=self.simple_materials, cull_materials=self.cull_materials,
                                          texture_interpolation=self.texture_interpolation,
                                          reuse_old_materials=self.reuse_old_materials,
                                          reuse_old_models=self.reuse_old_models,
                                          import_lights=self.import_lights,
                                          scale=self.global_scale, epsilon=self.epsilon,
                                          light_factor=self.light_factor, sun_factor=self.sun_factor,
                                          ambient_factor=self.ambient_factor,
                                          verbose=self.verbose,
                                          skip_tools=self.invisible_behaviour == 'SKIP',
                                          separate_tools=self.invisible_behaviour == 'SEPARATE')
        with importer:
            importer.load(self.filepath, context, self.map_data_path)
        if delete_files and dec_models_path is not None:
            rmtree(dec_models_path, ignore_errors=True)
        return {'FINISHED'}

    def draw(self, context: bpy.types.Context) -> None:
        pass


class VMF_PT_vmf_map_data(bpy.types.Panel):
    bl_space_type = 'FILE_BROWSER'
    bl_region_type = 'TOOL_PROPS'
    bl_label = ""
    bl_parent_id = "FILE_PT_operator"
    bl_options = {'HIDE_HEADER'}

    @classmethod
    def poll(cls, context: bpy.types.Context) -> bool:
        operator = context.space_data.active_operator
        return operator.bl_idname == "IMPORT_SCENE_OT_vmf"

    def draw(self, context: bpy.types.Context) -> None:
        layout: bpy.types.UILayout = self.layout
        layout.use_property_split = True
        layout.use_property_decorate = False
        operator = context.space_data.active_operator
        layout.prop(operator, "map_data_path_prop", icon='FILE_FOLDER')


class VMF_PT_vmf_import_solids(bpy.types.Panel):
    bl_space_type = 'FILE_BROWSER'
    bl_region_type = 'TOOL_PROPS'
    bl_label = "Solids"
    bl_parent_id = "FILE_PT_operator"
    bl_options = {'DEFAULT_CLOSED'}

    @classmethod
    def poll(cls, context: bpy.types.Context) -> bool:
        operator = context.space_data.active_operator
        return operator.bl_idname == "IMPORT_SCENE_OT_vmf"

    def draw_header(self, context: bpy.types.Context) -> None:
        layout: bpy.types.UILayout = self.layout
        operator = context.space_data.active_operator
        layout.prop(operator, "import_solids", text="")

    def draw(self, context: bpy.types.Context) -> None:
        layout: bpy.types.UILayout = self.layout
        layout.use_property_split = True
        layout.use_property_decorate = False
        operator = context.space_data.active_operator

        layout.enabled = operator.import_solids
        layout.prop(operator, "epsilon")
        layout.prop(operator, "invisible_behaviour", expand=True)
        layout.prop(operator, "import_overlays")


class VMF_PT_vmf_import_props(bpy.types.Panel):
    bl_space_type = 'FILE_BROWSER'
    bl_region_type = 'TOOL_PROPS'
    bl_label = "Props"
    bl_parent_id = "FILE_PT_operator"
    bl_options = {'DEFAULT_CLOSED'}

    @classmethod
    def poll(cls, context: bpy.types.Context) -> bool:
        operator = context.space_data.active_operator
        return operator.bl_idname == "IMPORT_SCENE_OT_vmf"

    def draw_header(self, context: bpy.types.Context) -> None:
        layout: bpy.types.UILayout = self.layout
        operator = context.space_data.active_operator
        layout.prop(operator, "import_props", text="")

    def draw(self, context: bpy.types.Context) -> None:
        layout: bpy.types.UILayout = self.layout
        layout.use_property_split = True
        layout.use_property_decorate = False
        operator = context.space_data.active_operator

        if operator.qc_available:
            layout.label(text="Models will be imported using Blender Source Tools.")
            preferences: ValveGameAddonPreferences = context.preferences.addons[__package__].preferences
            if not preferences.cache_path:
                layout.label(text="They will be decompiled into a temp directory and deleted.")
                row = layout.row()
                row.label(text="You can specify a persistent cache path.", icon='INFO')
                row.operator("io_import_vmf.open_preferences", text="", icon='PREFERENCES')
            else:
                layout.label(text="Missing models will be decompiled.")
        else:
            operator.import_props = False
            layout.label(text="Blender Source tools must be installed to import props.")
        layout.prop(operator, "skip_collision")
        layout.prop(operator, "skip_lod")
        layout.prop(operator, "optimize_props")
        layout.prop(operator, "reuse_old_models")
        layout.enabled = operator.import_props


class VMF_PT_import_materials(bpy.types.Panel):
    bl_space_type = 'FILE_BROWSER'
    bl_region_type = 'TOOL_PROPS'
    bl_label = "Materials"
    bl_parent_id = "FILE_PT_operator"
    bl_options = {'DEFAULT_CLOSED'}

    @classmethod
    def poll(cls, context: bpy.types.Context) -> bool:
        operator = context.space_data.active_operator
        return operator.bl_idname in (
            "IMPORT_SCENE_OT_vmf",
            "IMPORT_SCENE_OT_sourcemodel_enhanced",
            "IMPORT_SCENE_OT_agr_enhanced",
        )

    def draw_header(self, context: bpy.types.Context) -> None:
        layout: bpy.types.UILayout = self.layout
        operator = context.space_data.active_operator
        if operator.bl_idname == "IMPORT_SCENE_OT_vmf" and not operator.import_solids and not operator.import_props:
            layout.enabled = False
            operator.import_materials = False
        layout.prop(operator, "import_materials", text="")

    def draw(self, context: bpy.types.Context) -> None:
        layout: bpy.types.UILayout = self.layout
        layout.use_property_split = True
        layout.use_property_decorate = False
        operator = context.space_data.active_operator

        layout.enabled = operator.import_materials
        layout.prop(operator, "simple_materials")
        layout.prop(operator, "texture_interpolation")
        layout.prop(operator, "cull_materials")
        layout.prop(operator, "reuse_old_materials")


class VMF_PT_vmf_import_lights(bpy.types.Panel):
    bl_space_type = 'FILE_BROWSER'
    bl_region_type = 'TOOL_PROPS'
    bl_label = "Lights"
    bl_parent_id = "FILE_PT_operator"
    bl_options = {'DEFAULT_CLOSED'}

    @classmethod
    def poll(cls, context: bpy.types.Context) -> bool:
        operator = context.space_data.active_operator
        return operator.bl_idname == "IMPORT_SCENE_OT_vmf"

    def draw_header(self, context: bpy.types.Context) -> None:
        layout: bpy.types.UILayout = self.layout
        operator = context.space_data.active_operator
        layout.prop(operator, "import_lights", text="")

    def draw(self, context: bpy.types.Context) -> None:
        layout: bpy.types.UILayout = self.layout
        layout.use_property_split = True
        layout.use_property_decorate = False
        operator = context.space_data.active_operator

        layout.enabled = operator.import_lights
        layout.prop(operator, "light_factor")
        layout.prop(operator, "sun_factor")
        layout.prop(operator, "ambient_factor")


class VMF_PT_vmf_import_sky(bpy.types.Panel):
    bl_space_type = 'FILE_BROWSER'
    bl_region_type = 'TOOL_PROPS'
    bl_label = "Sky"
    bl_parent_id = "FILE_PT_operator"
    bl_options = {'DEFAULT_CLOSED'}

    @classmethod
    def poll(cls, context: bpy.types.Context) -> bool:
        operator = context.space_data.active_operator
        return operator.bl_idname == "IMPORT_SCENE_OT_vmf"

    def draw_header(self, context: bpy.types.Context) -> None:
        layout: bpy.types.UILayout = self.layout
        operator = context.space_data.active_operator
        layout.prop(operator, "import_sky", text="")

    def draw(self, context: bpy.types.Context) -> None:
        layout: bpy.types.UILayout = self.layout
        layout.use_property_split = True
        layout.use_property_decorate = False
        operator = context.space_data.active_operator

        layout.enabled = operator.import_sky
        layout.prop(operator, "sky_resolution")


class VMF_PT_vmf_import_main(bpy.types.Panel):
    bl_space_type = 'FILE_BROWSER'
    bl_region_type = 'TOOL_PROPS'
    bl_label = ""
    bl_parent_id = "FILE_PT_operator"
    bl_options = {'HIDE_HEADER'}

    @classmethod
    def poll(cls, context: bpy.types.Context) -> bool:
        operator = context.space_data.active_operator
        return operator.bl_idname == "IMPORT_SCENE_OT_vmf"

    def draw(self, context: bpy.types.Context) -> None:
        layout: bpy.types.UILayout = self.layout
        layout.use_property_split = True
        layout.use_property_decorate = False
        operator = context.space_data.active_operator

        layout.prop(operator, "import_sky_origin")
        layout.separator()
        layout.prop(operator, "global_scale")


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


class ImportSceneSourceModel(_ValveGameOperator, _ValveGameOperatorProps):
    """Load a Source Engine QC/MDL file"""
    bl_idname = "import_scene.sourcemodel_enhanced"
    bl_label = "Import QC/MDL (enhanced)"
    bl_options = {'UNDO', 'PRESET'}

    filepath: bpy.props.StringProperty(subtype='FILE_PATH', options={'HIDDEN'})  # type: ignore
    filter_glob: bpy.props.StringProperty(default="*.qc;*.mdl", options={'HIDDEN'})  # type: ignore

    strategy: bpy.props.EnumProperty(  # type: ignore
        name="MDL strategy",
        items=(
            ('BST', "BST", "Decompile model and import using Blender Source Tools"),
            ('SOURCEIO', "SourceIO", "Import model directly using SourceIO"),
        ),
        default='BST',
    )

    skip_collision: bpy.props.BoolProperty(  # type: ignore
        name="Skip collision meshes",
        default=True,
        description="Skips importing collision meshes",
    )

    skip_lod: bpy.props.BoolProperty(  # type: ignore
        name="Skip LOD meshes",
        default=True,
        description="Skips importing LOD meshes",
    )

    import_materials: bpy.props.BoolProperty(  # type: ignore
        name="Import materials",
        default=True,
    )

    simple_materials: bpy.props.BoolProperty(  # type: ignore
        name="Simple materials",
        description="Import simple, exporter-friendly versions of materials",
        default=False,
    )

    texture_interpolation: bpy.props.EnumProperty(  # type: ignore
        name="Texture interpolation",
        description="Interpolation type to use for image textures",
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
        description="Enable backface culling for materials which don't disable it",
        default=False,
    )

    reuse_old_materials: bpy.props.BoolProperty(  # type: ignore
        name="Reuse old materials",
        description="Reuse previously imported materials and images instead of reimporting them",
        default=True,
    )

    @classmethod
    def poll(cls, context: bpy.types.Context) -> bool:
        addons = context.preferences.addons
        return "io_scene_valvesource" in addons or "SourceIO" in addons

    def execute(self, context: bpy.types.Context) -> Set[str]:
        root = _get_source_path_root(self.filepath)
        if root is None:
            root = dirname(self.filepath)
        vmt_importer = None
        if self.import_materials:
            from . import import_vmt
            fs = self.get_filesystem(context)
            if fs is None:
                self.report({'ERROR_INVALID_INPUT'}, "A game must be specified to import materials.")
                return {'CANCELLED'}
            vmt_importer = import_vmt.VMTImporter(
                self.verbose, self.simple_materials,
                self.texture_interpolation, self.cull_materials,
                reuse_old=self.reuse_old_materials, reuse_old_images=self.reuse_old_materials
            )
        else:
            fs = None
        if self.filepath.endswith(".qc"):
            self.strategy = 'BST'
        if self.strategy == 'SOURCEIO':
            try:
                from . import import_mdl
            except ImportError:
                self.report({'ERROR'}, "SourceIO is not installed")
                return {'CANCELLED'}
            print("Importing model...")
            mdl_importer = import_mdl.MDLImporter(fs, vmt_importer, self.verbose)
            mdl_importer.load(splitext(relpath(self.filepath, root))[0], self.filepath, context.collection)
        elif self.strategy == 'BST':
            try:
                from . import import_qc
            except ImportError:
                self.report({'ERROR'}, "Blender Source Tools is not installed")
                return {'CANCELLED'}
            delete_files, dec_models_path = self.get_dec_models_path(context)
            print("Importing model...")
            qc_importer = import_qc.QCImporter(
                dec_models_path, fs, vmt_importer,
                skip_collision=self.skip_collision, skip_lod=self.skip_lod,
                reuse_old=False, verbose=self.verbose,
            )
            with qc_importer:
                name = splitext(relpath(self.filepath, root))[0]
                qc_importer.stage(name, self.filepath, context, root)
                qc_importer.load_all()
                qc_importer.get(name, context.collection, context)
            if delete_files:
                rmtree(dec_models_path, ignore_errors=True)
        if vmt_importer is not None:
            vmt_importer.load_all()
        return {'FINISHED'}

    def draw(self, context: bpy.types.Context) -> None:
        pass


class VMF_PT_sourcemodel_import_main(bpy.types.Panel):
    bl_space_type = 'FILE_BROWSER'
    bl_region_type = 'TOOL_PROPS'
    bl_label = ""
    bl_parent_id = "FILE_PT_operator"
    bl_options = {'HIDE_HEADER'}

    @classmethod
    def poll(cls, context: bpy.types.Context) -> bool:
        operator = context.space_data.active_operator
        return operator.bl_idname == "IMPORT_SCENE_OT_sourcemodel_enhanced"

    def draw(self, context: bpy.types.Context) -> None:
        layout: bpy.types.UILayout = self.layout
        layout.use_property_split = True
        layout.use_property_decorate = False
        operator = context.space_data.active_operator

        layout.prop(operator, "skip_collision")
        layout.prop(operator, "skip_lod")
        layout.prop(operator, "strategy", expand=True)


class ImportSceneVMT(_ValveGameOperator, _ValveGameOperatorProps):
    """Load a Source Engine VMT file"""
    bl_idname = "import_scene.vmt"
    bl_label = "Import VMT"
    bl_options = {'UNDO', 'PRESET'}

    directory: bpy.props.StringProperty(subtype='DIR_PATH', options={'HIDDEN'})  # type: ignore
    files: bpy.props.CollectionProperty(type=bpy.types.OperatorFileListElement, options={'HIDDEN'})  # type: ignore
    filter_glob: bpy.props.StringProperty(default="*.vmt", options={'HIDDEN'})  # type: ignore

    simple_materials: bpy.props.BoolProperty(  # type: ignore
        name="Simple materials",
        description="Import simple, exporter-friendly versions of materials",
        default=False,
    )

    texture_interpolation: bpy.props.EnumProperty(  # type: ignore
        name="Texture interpolation",
        description="Interpolation type to use for image textures",
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
        description="Enable backface culling for materials which don't disable it",
        default=False,
    )

    reuse_old_images: bpy.props.BoolProperty(  # type: ignore
        name="Reuse old images",
        description="Reuse previously imported images instead of reimporting them",
        default=True,
    )

    def execute(self, context: bpy.types.Context) -> Set[str]:
        from . import import_vmt
        from vmfpy.vmt import VMT
        root = _get_source_path_root(self.directory, "materials")
        fs = self.get_filesystem(context)
        if fs is None:
            fs = VMFFileSystem()
        if root is not None:
            print("Indexing local root directory...")
            fs.index_dir(root)
        print("Loading materials...")
        importer = import_vmt.VMTImporter(self.verbose, self.simple_materials,
                                          self.texture_interpolation, self.cull_materials,
                                          reuse_old=False, reuse_old_images=self.reuse_old_images)
        for file_obj in self.files:
            filepath = join(self.directory, file_obj.name)
            importer.stage(
                splitext(file_obj.name)[0],
                lambda: VMT(open(filepath, encoding='utf-8'), fs, allow_patch=True)
            )
        importer.load_all()
        return {'FINISHED'}

    def draw(self, context: bpy.types.Context) -> None:
        pass


class VMF_PT_vmt_import_main(bpy.types.Panel):
    bl_space_type = 'FILE_BROWSER'
    bl_region_type = 'TOOL_PROPS'
    bl_label = "Materials"
    bl_parent_id = "FILE_PT_operator"

    @classmethod
    def poll(cls, context: bpy.types.Context) -> bool:
        operator = context.space_data.active_operator
        return operator.bl_idname == "IMPORT_SCENE_OT_vmt"

    def draw(self, context: bpy.types.Context) -> None:
        layout: bpy.types.UILayout = self.layout
        layout.use_property_split = True
        layout.use_property_decorate = False
        operator = context.space_data.active_operator

        layout.prop(operator, "simple_materials")
        layout.prop(operator, "texture_interpolation")
        layout.prop(operator, "cull_materials")
        layout.prop(operator, "reuse_old_images")


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
        description="Import simple, exporter-friendly versions of materials",
        default=False,
    )

    texture_interpolation: bpy.props.EnumProperty(  # type: ignore
        name="Texture interpolation",
        description="Interpolation type to use for image textures",
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
        description="Enable backface culling for materials which don't disable it",
        default=False,
    )

    inter_key: bpy.props.BoolProperty(  # type: ignore
        name="Add interpolated key frames",
        description="Create interpolated key frames for frames in-between the original key frames",
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
        description="If set entities will scaled to zero when not visible",
        default=False,
    )

    keyframe_interpolation: bpy.props.EnumProperty(  # type: ignore
        name="Keyframe interpolation",
        description="Keyframe interpolation type used for animations. Bezier imports fastest.",
        items=[
            ('CONSTANT', "Constant", "No interpolation"),
            ('LINEAR', "Linear", "Linear interpolation"),
            ('BEZIER', "Bezier (fast import)", "Smooth interpolation"),
        ],
        default='BEZIER',
    )

    skip_collision: bpy.props.BoolProperty(  # type: ignore
        name="Skip collision meshes",
        default=True,
        description="Skips importing collision meshes",
    )

    skip_lod: bpy.props.BoolProperty(  # type: ignore
        name="Skip LOD meshes",
        default=True,
        description="Skips importing LOD meshes",
    )

    reuse_old_materials: bpy.props.BoolProperty(  # type: ignore
        name="Reuse old materials",
        description="Reuse previously imported materials and images instead of reimporting them",
        default=True,
    )

    reuse_old_models: bpy.props.BoolProperty(  # type: ignore
        name="Reuse old models",
        description="Reuse previously imported models instead of reimporting them",
        default=False,
    )

    @classmethod
    def poll(cls, context: bpy.types.Context) -> bool:
        return "advancedfx" in context.preferences.addons

    def execute(self, context: bpy.types.Context) -> Set[str]:
        from . import import_agr
        fs = self.get_filesystem(context)
        if fs is None:
            self.report({'ERROR_INVALID_INPUT'}, "A game must be specified to import AGR files.")
            return {'CANCELLED'}
        delete_files, dec_models_path = self.get_dec_models_path(context)
        importer = import_agr.AgrImporter(
            dec_models_path, fs,
            import_materials=self.import_materials, simple_materials=self.simple_materials,
            texture_interpolation=self.texture_interpolation, cull_materials=self.cull_materials,
            reuse_old_materials=self.reuse_old_materials, reuse_old_models=self.reuse_old_models,
            skip_collision=self.skip_collision, skip_lod=self.skip_lod,
            verbose=self.verbose,
            inter_key=self.inter_key, global_scale=self.global_scale, scale_invisible_zero=self.scale_invisible_zero,
            keyframe_interpolation=self.keyframe_interpolation,
        )
        with importer:
            importer.load(self.filepath, context.collection)
        if delete_files:
            rmtree(dec_models_path, ignore_errors=True)
        return {'FINISHED'}

    def draw(self, context: bpy.types.Context) -> None:
        pass


class VMF_PT_agr_import_models(bpy.types.Panel):
    bl_space_type = 'FILE_BROWSER'
    bl_region_type = 'TOOL_PROPS'
    bl_label = "Models"
    bl_parent_id = "FILE_PT_operator"

    @classmethod
    def poll(cls, context: bpy.types.Context) -> bool:
        operator = context.space_data.active_operator
        return operator.bl_idname == "IMPORT_SCENE_OT_agr_enhanced"

    def draw(self, context: bpy.types.Context) -> None:
        layout: bpy.types.UILayout = self.layout
        layout.use_property_split = True
        layout.use_property_decorate = False
        operator = context.space_data.active_operator

        layout.label(text="Models will be imported using Blender Source Tools.")
        preferences: ValveGameAddonPreferences = context.preferences.addons[__package__].preferences
        if not preferences.cache_path:
            layout.label(text="They will be decompiled into a temp directory and deleted.")
            row = layout.row()
            row.label(text="You can specify a persistent cache path.", icon='INFO')
            row.operator("io_import_vmf.open_preferences", text="", icon='PREFERENCES')
        else:
            layout.label(text="Missing models will be decompiled.")
        layout.separator()
        layout.prop(operator, "skip_collision")
        layout.prop(operator, "skip_lod")
        # layout.prop(operator, "reuse_old_models")


class VMF_PT_agr_import_main(bpy.types.Panel):
    bl_space_type = 'FILE_BROWSER'
    bl_region_type = 'TOOL_PROPS'
    bl_label = "AGR"
    bl_parent_id = "FILE_PT_operator"

    @classmethod
    def poll(cls, context: bpy.types.Context) -> bool:
        operator = context.space_data.active_operator
        return operator.bl_idname == "IMPORT_SCENE_OT_agr_enhanced"

    def draw(self, context: bpy.types.Context) -> None:
        layout: bpy.types.UILayout = self.layout
        layout.use_property_split = True
        layout.use_property_decorate = False
        operator = context.space_data.active_operator

        layout.prop(operator, "inter_key")
        layout.prop(operator, "global_scale")
        layout.prop(operator, "scale_invisible_zero")
        layout.prop(operator, "keyframe_interpolation")


class MaterialVMTData(bpy.types.PropertyGroup):
    width: bpy.props.IntProperty(default=1)  # type: ignore
    height: bpy.props.IntProperty(default=1)  # type: ignore
    full_name: bpy.props.StringProperty()  # type: ignore
    nodraw: bpy.props.BoolProperty()  # type: ignore


class QCBoneIdItem(bpy.types.PropertyGroup):
    bone_id: bpy.props.IntProperty()  # type: ignore
    bone_name: bpy.props.StringProperty()  # type: ignore


class QCMeshItem(bpy.types.PropertyGroup):
    mesh_obj: bpy.props.PointerProperty(type=bpy.types.Object)  # type: ignore


class ArmatureQCData(bpy.types.PropertyGroup):
    meshes: bpy.props.CollectionProperty(type=QCMeshItem)  # type: ignore
    bone_id_map: bpy.props.CollectionProperty(type=QCBoneIdItem)  # type: ignore
    action: bpy.props.PointerProperty(type=bpy.types.Action)  # type: ignore
    full_name: bpy.props.StringProperty()  # type: ignore

    def save_meshes(self, meshes: Sequence[bpy.types.Object]) -> None:
        self.meshes.clear()
        for mesh_obj in meshes:
            if mesh_obj.type != 'MESH':
                continue
            mesh_item = self.meshes.add()
            mesh_item.mesh_obj = mesh_obj

    def read_meshes(self) -> Iterator[bpy.types.Object]:
        for mesh_item in self.meshes:
            yield mesh_item.mesh_obj

    def save_bone_id_map(self, bone_id_map: Dict[int, str]) -> None:
        self.bone_id_map.clear()
        for key in bone_id_map:
            map_item = self.bone_id_map.add()
            map_item.bone_id = key
            map_item.bone_name = bone_id_map[key]

    def read_bone_id_map(self) -> Dict[int, str]:
        bone_id_map = {}
        for map_item in self.bone_id_map:
            bone_id_map[map_item.bone_id] = map_item.bone_name
        return bone_id_map


class ImageVTFData(bpy.types.PropertyGroup):
    full_name: bpy.props.StringProperty()  # type: ignore


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
    ImportSceneVMF,
    ImportSceneSourceModel,
    ImportSceneVMT,
    ImportSceneAGREnhanced,
    ObjectTransform3DSky,
    MaterialVMTData,
    QCBoneIdItem,
    QCMeshItem,
    ArmatureQCData,
    ImageVTFData,
    VMF_PT_valve_games,
    VMF_PT_agr_import_main,
    VMF_PT_agr_import_models,
    VMF_PT_sourcemodel_import_main,
    VMF_PT_vmf_map_data,
    VMF_PT_vmf_import_solids,
    VMF_PT_vmf_import_props,
    VMF_PT_import_materials,
    VMF_PT_vmf_import_lights,
    VMF_PT_vmf_import_sky,
    VMF_PT_vmf_import_main,
    VMF_PT_vmt_import_main,
)


def import_menu_func(self: bpy.types.Menu, context: bpy.types.Context) -> None:
    self.layout.operator(ImportSceneVMF.bl_idname, text="Valve Map Format (.vmf)")
    self.layout.operator(ImportSceneVMT.bl_idname, text="Valve Material Type (.vmt)")
    self.layout.operator(ImportSceneSourceModel.bl_idname, text="Source Engine Model (enhanced) (.qc/.mdl)")
    self.layout.operator(ImportSceneAGREnhanced.bl_idname, text="HLAE afxGameRecord (enhanced) (.agr)")


def object_menu_func(self: bpy.types.Menu, context: bpy.types.Context) -> None:
    self.layout.separator()
    self.layout.operator(ObjectTransform3DSky.bl_idname)


def register() -> None:
    for cls in classes:
        bpy.utils.register_class(cls)
    bpy.types.TOPBAR_MT_file_import.append(import_menu_func)
    bpy.types.VIEW3D_MT_object.append(object_menu_func)
    bpy.types.Material.vmt_data = bpy.props.PointerProperty(type=MaterialVMTData)
    bpy.types.Armature.qc_data = bpy.props.PointerProperty(type=ArmatureQCData)
    bpy.types.Image.vtf_data = bpy.props.PointerProperty(type=ImageVTFData)


def unregister() -> None:
    for cls in classes:
        bpy.utils.unregister_class(cls)
    bpy.types.TOPBAR_MT_file_import.remove(import_menu_func)
    bpy.types.VIEW3D_MT_object.remove(object_menu_func)
    del bpy.types.Material.vmt_data
    del bpy.types.Armature.qc_data
    del bpy.types.Image.vtf_data
