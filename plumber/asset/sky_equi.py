import bpy
from bpy.types import Context, ShaderNode

from .utils import truncate_name
from ..plumber import SkyEqui


def import_sky_equi(sky_equi: SkyEqui, context: Context) -> None:
    width = sky_equi.width()
    height = sky_equi.height()
    format = sky_equi.format()
    image_name = truncate_name(f"{sky_equi.name()}.{format}")

    image_data = bpy.data.images.new(image_name, width, height)

    if format == "exr":
        image_data.file_format = "OPEN_EXR"
    else:
        image_data.file_format = "TARGA_RAW"

    image_data.source = "FILE"
    bytes = sky_equi.bytes()
    image_data.pack(data=bytes, data_len=len(bytes))

    if context.scene.world is None:
        context.scene.world = bpy.data.worlds.new("World")

    context.scene.world.use_nodes = True
    nt = context.scene.world.node_tree
    nt.nodes.clear()
    out_node: ShaderNode = nt.nodes.new("ShaderNodeOutputWorld")
    out_node.location = (0, 0)
    bg_node: ShaderNode = nt.nodes.new("ShaderNodeBackground")
    bg_node.location = (-300, 0)
    nt.links.new(bg_node.outputs["Background"], out_node.inputs["Surface"])
    tex_node: ShaderNode = nt.nodes.new("ShaderNodeTexEnvironment")
    tex_node.image = image_data
    tex_node.location = (-600, 0)
    nt.links.new(tex_node.outputs["Color"], bg_node.inputs["Color"])
