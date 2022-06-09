import bpy
from bpy.types import Collection

from .utils import truncate_name
from ..plumber import BuiltOverlay


def import_overlay(overlay: BuiltOverlay, collection: Collection) -> None:
    id = overlay.id()
    name = f"overlay_{id}"
    mesh = bpy.data.meshes.new(name)

    vertices = overlay.vertices()
    mesh.vertices.add(len(vertices) // 3)
    mesh.loops.add(overlay.loops_len())
    mesh.polygons.add(overlay.polygons_len())
    mesh.vertices.foreach_set("co", vertices)
    mesh.polygons.foreach_set("loop_total", overlay.polygon_loop_totals())
    mesh.polygons.foreach_set("loop_start", overlay.polygon_loop_starts())
    mesh.polygons.foreach_set("vertices", overlay.polygon_vertices())
    mesh.update()
    uv_layer = mesh.uv_layers.new()
    uv_layer.data.foreach_set("uv", overlay.loop_uvs())

    material = truncate_name(overlay.material())
    material_data = bpy.data.materials.get(material)
    if material_data is None:
        material_data = bpy.data.materials.new(material)
    mesh.materials.append(material_data)

    obj = bpy.data.objects.new(name, object_data=mesh)
    obj.location = overlay.position()
    obj.scale = overlay.scale()
    collection.objects.link(obj)
