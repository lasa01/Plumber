import bpy
from bpy.types import Context, Collection

from ..plumber import Light, SpotLight, EnvLight


def import_light(light: Light, collection: Collection) -> None:
    name = f"light_{light.id()}"

    light_data = bpy.data.lights.new(name, "POINT")
    light_data.cycles.use_multiple_importance_sampling = False
    light_data.color = light.color()
    light_data.energy = light.energy()

    obj = bpy.data.objects.new(name, object_data=light_data)
    collection.objects.link(obj)

    obj.location = light.position()


def import_spot_light(light: SpotLight, collection: Collection) -> None:
    name = f"light_spot_{light.id()}"

    light_data = bpy.data.lights.new(name, "SPOT")
    light_data.cycles.use_multiple_importance_sampling = False
    light_data.color = light.color()
    light_data.energy = light.energy()
    light_data.spot_size = light.spot_size()
    light_data.spot_blend = light.spot_blend()

    obj = bpy.data.objects.new(name, object_data=light_data)
    collection.objects.link(obj)

    obj.location = light.position()
    obj.rotation_euler = light.rotation()


def import_env_light(light: EnvLight, context: Context, collection: Collection) -> None:
    name = f"light_environment_{light.id()}"

    light_data = bpy.data.lights.new(name, "SUN")
    light_data.cycles.use_multiple_importance_sampling = True
    light_data.color = light.sun_color()
    light_data.energy = light.sun_energy()
    light_data.angle = light.angle()

    obj = bpy.data.objects.new(name, object_data=light_data)
    collection.objects.link(obj)

    obj.location = light.position()
    obj.rotation_euler = light.rotation()

    if context.scene.world is None:
        context.scene.world = bpy.data.worlds.new("World")

    context.scene.world.use_nodes = True
    nt = context.scene.world.node_tree
    if nt.nodes:
        # don't override imported skybox or a previous material with this
        return

    out_node: bpy.types.Node = nt.nodes.new("ShaderNodeOutputWorld")
    out_node.location = (0, 0)

    bg_node: bpy.types.Node = nt.nodes.new("ShaderNodeBackground")
    bg_node.location = (-300, 0)

    nt.links.new(bg_node.outputs["Background"], out_node.inputs["Surface"])

    bg_node.inputs["Color"].default_value = light.ambient_color()
    bg_node.inputs["Strength"].default_value = light.ambient_strength()
