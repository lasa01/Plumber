import bpy
from bpy.types import Context, Menu

from . import preferences, importer, tools, benchmark, version_str
from .importer import ImportMdl, ImportVmf, ImportVmt, ImportVtf
from .tools import IMPORT_MT_plumber_browse


class IMPORT_MT_plumber(Menu):
    bl_idname = "IMPORT_MT_plumber"
    bl_label = "Plumber"

    def draw(self, context: Context):
        self.layout.operator(
            ImportVmf.bl_idname, text="Valve Map Format (.vmf)"
        ).from_game_fs = False
        self.layout.operator(
            ImportMdl.bl_idname, text="Source Model (.mdl)"
        ).from_game_fs = False
        self.layout.operator(
            ImportVmt.bl_idname, text="Valve Material Type (.vmt)"
        ).from_game_fs = False
        self.layout.operator(
            ImportVtf.bl_idname, text="Valve Texture Format (.vtf)"
        ).from_game_fs = False

        self.layout.menu(IMPORT_MT_plumber_browse.bl_idname)


def menu_func_import(self: Menu, context: Context):
    self.layout.menu(IMPORT_MT_plumber.bl_idname)


def register():
    from . import plumber

    rust_version = plumber.version()
    if rust_version != version_str:
        raise Exception(
            f"Native code version {rust_version} does not match Python code version {version_str}. "
            + "Please restart Blender and reinstall the addon."
        )

    preferences.register()
    importer.register()
    tools.register()
    benchmark.register()

    bpy.utils.register_class(IMPORT_MT_plumber)
    bpy.types.TOPBAR_MT_file_import.append(menu_func_import)


def unregister():
    bpy.types.TOPBAR_MT_file_import.remove(menu_func_import)
    bpy.utils.unregister_class(IMPORT_MT_plumber)

    benchmark.unregister()
    tools.unregister()
    importer.unregister()
    preferences.unregister()
