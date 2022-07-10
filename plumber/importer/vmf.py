from typing import Set
from os.path import basename, splitext, isdir, isabs, dirname, join

from bpy.props import (
    BoolProperty,
    EnumProperty,
    FloatProperty,
    StringProperty,
    IntProperty,
)
from bpy.types import Context, Panel, UILayout
import bpy

from . import (
    GameFileImporterOperator,
    GameFileImporterOperatorProps,
    ImporterOperatorProps,
    MaterialToggleOperatorProps,
)
from ..asset import AssetCallbacks
from ..plumber import Importer


class ImportVmf(
    GameFileImporterOperator,
    ImporterOperatorProps,
    GameFileImporterOperatorProps,
    MaterialToggleOperatorProps,
):
    """Import Source Engine VMF map"""

    bl_idname = "import_scene.plumber_vmf"
    bl_label = "Import VMF"
    bl_options = {"REGISTER", "UNDO", "PRESET"}

    filename_ext = ".vmf"

    filter_glob: StringProperty(
        default="*.vmf",
        options={"HIDDEN"},
        maxlen=255,
    )

    map_data_path: StringProperty(
        name="Embedded files path", default="", description="Leave empty to auto-detect"
    )

    import_brushes: BoolProperty(
        name="Brushes",
        default=True,
    )

    import_overlays: BoolProperty(
        name="Overlays",
        description="Import overlays on top of brushes, such as bomb site sprays",
        default=True,
    )

    epsilon: FloatProperty(
        name="Epsilon",
        description="Equality threshold for building geometry",
        min=0,
        max=1.0,
        soft_min=0.0001,
        soft_max=0.01,
        default=0.001,
        precision=6,
    )

    cut_threshold: FloatProperty(
        name="Cut threshold",
        description="Threshold for cutting geometry",
        min=0,
        max=1.0,
        soft_min=0.0001,
        soft_max=0.01,
        default=0.001,
        precision=6,
    )

    merge_solids: EnumProperty(
        name="Merge solids",
        items=[
            ("MERGE", "Merge", "Solids are merged into one mesh object per brush"),
            (
                "SEPARATE",
                "Separate",
                "Create a separate mesh object for each solid (slower)",
            ),
        ],
        default="MERGE",
    )

    invisible_solids: EnumProperty(
        name="Invisible solids",
        items=[
            ("IMPORT", "Import", "Import invisible solids normally"),
            ("SKIP", "Skip", "Skip fully invisible solids"),
        ],
        default="SKIP",
    )

    import_props: BoolProperty(
        name="Props",
        default=True,
    )

    dynamic_props: EnumProperty(
        name="Dynamic props",
        description="Import settings for props that are not static",
        items=[
            ("NORMAL", "Normal", "Import dynamic props with armatures and animations"),
            (
                "REMOVE_ANIM",
                "Remove animations",
                "Remove prop animations by applying the first frame",
            ),
            (
                "REMOVE_ARM",
                "Remove armatures",
                "Remove armatures and animations by creating a copy of the mesh "
                + "for each instance and applying the armature (slower)",
            ),
        ],
        default="NORMAL",
    )

    import_lights: BoolProperty(
        name="Lights",
        default=True,
    )

    light_factor: FloatProperty(
        name="Light brightness factor",
        description="Factor for converting light brightness into Blender",
        min=0,
        max=100.0,
        soft_min=0.0001,
        soft_max=1.0,
        default=0.1,
        precision=4,
    )

    sun_factor: FloatProperty(
        name="Sun brightness factor",
        description="Factor for converting sun brightness into Blender",
        min=0,
        max=100.0,
        soft_min=0.0001,
        soft_max=1.0,
        default=0.01,
        precision=4,
    )

    ambient_factor: FloatProperty(
        name="Ambient brightness factor",
        description="Factor for converting ambient brightness into Blender",
        min=0,
        max=100.0,
        soft_min=0.0001,
        soft_max=1.0,
        default=0.001,
        precision=4,
    )

    import_sky_camera: BoolProperty(
        name="Sky camera",
        default=True,
    )

    import_sky: BoolProperty(
        name="Sky",
        default=True,
    )

    sky_equi_height: IntProperty(
        name="Sky output height",
        default=0,
        description="0 uses automatic resolution. Higher values may increase quality at the cost of import time",
        min=0,
        max=32768,
        soft_min=0,
        soft_max=8192,
        subtype="PIXEL",
    )

    import_unknown_entities: BoolProperty(
        name="Unknown entities",
        description="Import all entities not imported elsewhere as empties",
        default=False,
    )

    scale: FloatProperty(
        name="Scale",
        default=0.01,
        min=1e-6,
        max=1e6,
        soft_min=0.001,
        soft_max=1.0,
    )

    def execute(self, context: Context) -> Set[str]:
        fs = self.get_game_fs(context)

        if self.map_data_path == "":
            map_data_path = None
        else:
            if isabs(self.map_data_path) or self.from_game_fs:
                map_data_path = self.map_data_path
            else:
                map_data_path = join(dirname(self.filepath), self.map_data_path)

            if not isdir(map_data_path):
                self.report(
                    {"ERROR_INVALID_INPUT"},
                    "The specified embedded files directory doesn't exist.",
                )
                return {"CANCELLED"}

        map_name = splitext(basename(self.filepath))[0]

        map_collection = bpy.data.collections.new(map_name)
        context.collection.children.link(map_collection)

        if self.import_brushes:
            brush_collection = bpy.data.collections.new("brushes")
            map_collection.children.link(brush_collection)
        else:
            brush_collection = None

        if self.import_brushes and self.import_overlays:
            overlay_collection = bpy.data.collections.new("overlays")
            map_collection.children.link(overlay_collection)
        else:
            overlay_collection = None

        if self.import_props:
            prop_collection = bpy.data.collections.new("props")
            map_collection.children.link(prop_collection)
        else:
            prop_collection = None

        if self.import_lights:
            light_collection = bpy.data.collections.new("lights")
            map_collection.children.link(light_collection)
        else:
            light_collection = None

        if self.import_unknown_entities:
            entity_collection = bpy.data.collections.new("entities")
            map_collection.children.link(entity_collection)
        else:
            entity_collection = None

        asset_callbacks = AssetCallbacks(
            context,
            main_collection=map_collection,
            brush_collection=brush_collection,
            overlay_collection=overlay_collection,
            prop_collection=prop_collection,
            light_collection=light_collection,
            entity_collection=entity_collection,
            apply_armatures=self.dynamic_props == "REMOVE_ARM",
        )

        try:
            importer = Importer(
                fs,
                asset_callbacks,
                self.get_threads_suggestion(context),
                import_lights=self.import_lights,
                light_factor=self.light_factor,
                sun_factor=self.sun_factor,
                ambient_factor=self.ambient_factor,
                import_sky_camera=self.import_sky_camera,
                sky_equi_height=self.sky_equi_height
                if self.sky_equi_height != 0
                else None,
                import_unknown_entities=self.import_unknown_entities,
                scale=self.scale,
                target_fps=self.get_target_fps(context),
                remove_animations=self.dynamic_props in ("REMOVE_ANIM", "REMOVE_ARM"),
                simple_materials=self.simple_materials,
                allow_culling=self.allow_culling,
                editor_materials=self.editor_materials,
                texture_interpolation=self.texture_interpolation,
                # automatic map data path detection happens here
                vmf_path=self.filepath if map_data_path is None else None,
                map_data_path=map_data_path,
            )
        except OSError as err:
            self.report({"ERROR"}, f"Could not open file system: {err}")
            return {"CANCELLED"}

        try:
            importer.import_vmf(
                self.filepath,
                self.from_game_fs,
                import_brushes=self.import_brushes,
                import_overlays=self.import_overlays,
                epsilon=self.epsilon,
                cut_threshold=self.cut_threshold,
                merge_solids=self.merge_solids,
                invisible_solids=self.invisible_solids,
                import_materials=self.import_materials,
                import_props=self.import_props,
                import_entities=self.import_lights or self.import_sky_camera,
                import_sky=self.import_sky,
                scale=self.scale,
            )
        except OSError as err:
            self.report({"ERROR"}, f"Could not parse vmf: {err}")
            return {"CANCELLED"}

        asset_callbacks.finish()

        return {"FINISHED"}

    def draw(self, context: Context):
        if self.from_game_fs:
            draw_map_data_props(self.layout, self, context)

            self.layout.prop(self, "import_brushes")
            draw_geometry_props(self.layout.box(), self, context)

            self.layout.prop(self, "import_lights")
            draw_light_props(self.layout.box(), self, context)

            self.layout.prop(self, "import_sky")
            draw_sky_props(self.layout.box(), self, context)

            self.layout.prop(self, "import_props")
            draw_props_props(self.layout.box(), self, context)

            MaterialToggleOperatorProps.draw_props(self.layout, self, context)

            draw_main_props(self.layout, self, context)


def draw_map_data_props(layout: UILayout, operator: ImportVmf, context: Context):
    layout.use_property_split = True
    layout.use_property_decorate = False
    layout.prop(operator, "map_data_path", icon="FILE_FOLDER")


class PLUMBER_PT_vmf_map_data(Panel):
    bl_space_type = "FILE_BROWSER"
    bl_region_type = "TOOL_PROPS"
    bl_label = ""
    bl_parent_id = "FILE_PT_operator"
    bl_options = {"HIDE_HEADER"}

    @classmethod
    def poll(cls, context: Context) -> bool:
        operator = context.space_data.active_operator
        return operator.bl_idname == "IMPORT_SCENE_OT_plumber_vmf"

    def draw(self, context: Context) -> None:
        draw_map_data_props(self.layout, context.space_data.active_operator, context)


def draw_geometry_props(layout: UILayout, operator: ImportVmf, context: Context):
    layout.use_property_split = True
    layout.enabled = operator.import_brushes
    layout.prop(operator, "import_overlays")
    layout.prop(operator, "epsilon")
    layout.prop(operator, "cut_threshold")
    layout.prop(operator, "merge_solids", expand=True)
    layout.prop(operator, "invisible_solids", expand=True)


class PLUMBER_PT_vmf_geometry(Panel):
    bl_space_type = "FILE_BROWSER"
    bl_region_type = "TOOL_PROPS"
    bl_label = ""
    bl_parent_id = "FILE_PT_operator"
    bl_options = {"DEFAULT_CLOSED", "HEADER_LAYOUT_EXPAND"}

    @classmethod
    def poll(cls, context: Context) -> bool:
        operator = context.space_data.active_operator
        return operator.bl_idname == "IMPORT_SCENE_OT_plumber_vmf"

    def draw_header(self, context: Context) -> None:
        layout = self.layout
        operator = context.space_data.active_operator
        layout.prop(operator, "import_brushes")

    def draw(self, context: Context) -> None:
        draw_geometry_props(self.layout, context.space_data.active_operator, context)


def draw_light_props(layout: UILayout, operator: ImportVmf, context: Context):
    layout.use_property_split = True
    layout.enabled = operator.import_lights
    layout.prop(operator, "light_factor")
    layout.prop(operator, "sun_factor")
    layout.prop(operator, "ambient_factor")


class PLUMBER_PT_vmf_lights(Panel):
    bl_space_type = "FILE_BROWSER"
    bl_region_type = "TOOL_PROPS"
    bl_label = "Lights"
    bl_parent_id = "FILE_PT_operator"
    bl_options = {"DEFAULT_CLOSED"}

    @classmethod
    def poll(cls, context: Context) -> bool:
        operator = context.space_data.active_operator
        return operator.bl_idname == "IMPORT_SCENE_OT_plumber_vmf"

    def draw_header(self, context: Context) -> None:
        layout = self.layout
        operator = context.space_data.active_operator
        layout.prop(operator, "import_lights", text="")

    def draw(self, context: Context) -> None:
        draw_light_props(self.layout, context.space_data.active_operator, context)


def draw_sky_props(layout: UILayout, operator: ImportVmf, context: Context):
    layout.use_property_split = True
    layout.enabled = operator.import_sky
    layout.prop(operator, "sky_equi_height")


class PLUMBER_PT_vmf_sky(Panel):
    bl_space_type = "FILE_BROWSER"
    bl_region_type = "TOOL_PROPS"
    bl_label = "Sky"
    bl_parent_id = "FILE_PT_operator"
    bl_options = {"DEFAULT_CLOSED"}

    @classmethod
    def poll(cls, context: Context) -> bool:
        operator = context.space_data.active_operator
        return operator.bl_idname == "IMPORT_SCENE_OT_plumber_vmf"

    def draw_header(self, context: Context) -> None:
        layout = self.layout
        operator = context.space_data.active_operator
        layout.prop(operator, "import_sky", text="")

    def draw(self, context: Context) -> None:
        draw_sky_props(self.layout, context.space_data.active_operator, context)


def draw_props_props(layout: UILayout, operator: ImportVmf, context: Context):
    layout.use_property_split = True
    layout.enabled = operator.import_props
    layout.prop(operator, "dynamic_props")


class PLUMBER_PT_vmf_props(Panel):
    bl_space_type = "FILE_BROWSER"
    bl_region_type = "TOOL_PROPS"
    bl_label = "Props"
    bl_parent_id = "FILE_PT_operator"
    bl_options = {"DEFAULT_CLOSED"}

    @classmethod
    def poll(cls, context: Context) -> bool:
        operator = context.space_data.active_operator
        return operator.bl_idname == "IMPORT_SCENE_OT_plumber_vmf"

    def draw_header(self, context: Context) -> None:
        layout = self.layout
        operator = context.space_data.active_operator
        layout.prop(operator, "import_props", text="")

    def draw(self, context: Context) -> None:
        draw_props_props(self.layout, context.space_data.active_operator, context)


def draw_main_props(layout: UILayout, operator: ImportVmf, context: Context):
    layout.use_property_split = True
    layout.prop(operator, "import_sky_camera")
    layout.prop(operator, "import_unknown_entities")
    layout.prop(operator, "scale")


class PLUMBER_PT_vmf_main(Panel):
    bl_space_type = "FILE_BROWSER"
    bl_region_type = "TOOL_PROPS"
    bl_label = ""
    bl_parent_id = "FILE_PT_operator"
    bl_options = {"HIDE_HEADER"}

    @classmethod
    def poll(cls, context: Context) -> bool:
        operator = context.space_data.active_operator
        return operator.bl_idname == "IMPORT_SCENE_OT_plumber_vmf"

    def draw(self, context: Context) -> None:
        draw_main_props(self.layout, context.space_data.active_operator, context)
