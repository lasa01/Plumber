import bpy
from bpy.types import Context, Collection

from ..plumber import SkyCamera


def import_sky_camera(
    sky_camera: SkyCamera, context: Context, collection: Collection
) -> None:
    name = f"sky_camera_{sky_camera.id()}"

    obj = bpy.data.objects.new(name, object_data=None)
    obj.location = sky_camera.position()
    obj.scale = sky_camera.scale()
    collection.objects.link(obj)

    obj.select_set(True)
    context.view_layer.objects.active = obj
