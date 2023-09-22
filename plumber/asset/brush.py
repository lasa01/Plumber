import bpy
from bpy.types import Collection

from .utils import truncate_name
from ..plumber import BuiltBrushEntity, BuiltSolid, MergedSolids


def import_brush(brush: BuiltBrushEntity, collection: Collection) -> None:
    id = brush.id()
    class_name = brush.class_name()
    brush_name = f"{class_name}_{id}"

    merged_solids = brush.merged_solids()
    if merged_solids is not None:
        import_merged_solids(collection, brush_name, merged_solids)

    for solid in brush.solids():
        import_solid(collection, brush_name, solid)


def import_solid(collection: Collection, brush_name: str, solid: BuiltSolid) -> None:
    id = solid.id()
    solid_name = f"{brush_name}_{id}"
    mesh = bpy.data.meshes.new(solid_name)

    vertices = solid.vertices()
    mesh.vertices.add(len(vertices) // 3)
    mesh.loops.add(solid.loops_len())
    mesh.polygons.add(solid.polygons_len())
    mesh.vertices.foreach_set("co", vertices)
    mesh.polygons.foreach_set("loop_total", solid.polygon_loop_totals())
    mesh.polygons.foreach_set("loop_start", solid.polygon_loop_starts())
    mesh.polygons.foreach_set("vertices", solid.polygon_vertices())
    mesh.polygons.foreach_set("material_index", solid.polygon_material_indices())

    # Blender 3.6 sets meshes to smooth by default, which looks bad
    if bpy.app.version >= (3, 6, 0):
        mesh.shade_flat()

    mesh.update()

    uv_layer = mesh.uv_layers.new()
    uv_layer.data.foreach_set("uv", solid.loop_uvs())

    color_layer = mesh.vertex_colors.new(name="Col", do_init=False)
    color_layer.data.foreach_set("color", solid.loop_colors())

    for material in solid.materials():
        material_data = bpy.data.materials.get(truncate_name(material))
        if material_data is None:
            material_data = bpy.data.materials.new(material)
        mesh.materials.append(material_data)

    obj = bpy.data.objects.new(solid_name, object_data=mesh)
    obj.location = solid.position()
    obj.scale = solid.scale()
    collection.objects.link(obj)


def import_merged_solids(
    collection: Collection, brush_name: str, merged_solids: MergedSolids
) -> None:
    mesh = bpy.data.meshes.new(brush_name)

    vertices = merged_solids.vertices()
    mesh.vertices.add(len(vertices) // 3)
    mesh.loops.add(merged_solids.loops_len())
    mesh.polygons.add(merged_solids.polygons_len())
    mesh.vertices.foreach_set("co", vertices)
    mesh.polygons.foreach_set("loop_total", merged_solids.polygon_loop_totals())
    mesh.polygons.foreach_set("loop_start", merged_solids.polygon_loop_starts())
    mesh.polygons.foreach_set("vertices", merged_solids.polygon_vertices())
    mesh.polygons.foreach_set(
        "material_index", merged_solids.polygon_material_indices()
    )

    # Blender 3.6 sets meshes to smooth by default, which looks bad
    if bpy.app.version >= (3, 6, 0):
        mesh.shade_flat()

    mesh.update()

    uv_layer = mesh.uv_layers.new()
    uv_layer.data.foreach_set("uv", merged_solids.loop_uvs())

    color_layer = mesh.vertex_colors.new(name="Col", do_init=False)
    color_layer.data.foreach_set("color", merged_solids.loop_colors())

    for material in merged_solids.materials():
        material_data = bpy.data.materials.get(truncate_name(material))
        if material_data is None:
            material_data = bpy.data.materials.new(material)
        mesh.materials.append(material_data)

    obj = bpy.data.objects.new(brush_name, object_data=mesh)
    obj.location = merged_solids.position()
    obj.scale = merged_solids.scale()
    collection.objects.link(obj)
