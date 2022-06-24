bl_info = {
    "name": "Plumber",
    "author": "Lassi Säike",
    "version": (1, 0, 0),
    "blender": (2, 82, 0),
    "location": "File > Import -> Plumber",
    "description": "Imports Source Engine assets.",
    "warning": "beta2",
    "tracker_url": "https://github.com/lasa01/plumber",
    "category": "Import-Export",
}

# check if imported by setup.py or actually running in Blender
from bpy.app import version

if version is not None:
    import bpy
    from bpy.types import Context, Menu

    from . import preferences, importer, tools
    from .importer import ImportMdl, ImportVmf, ImportVmt
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

            self.layout.menu(IMPORT_MT_plumber_browse.bl_idname)

    def menu_func_import(self: Menu, context: Context):
        self.layout.menu(IMPORT_MT_plumber.bl_idname)

    def register():
        preferences.register()
        importer.register()
        tools.register()

        bpy.utils.register_class(IMPORT_MT_plumber)
        bpy.types.TOPBAR_MT_file_import.append(menu_func_import)

    def unregister():
        bpy.types.TOPBAR_MT_file_import.remove(menu_func_import)
        bpy.utils.unregister_class(IMPORT_MT_plumber)

        tools.unregister()
        importer.unregister()
        preferences.unregister()
