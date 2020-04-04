from vmfpy import vmt
from typing import NamedTuple, Dict, DefaultDict, Set, Tuple, Optional, Union, Any, Iterator, Iterable, List, Callable
from abc import ABC, abstractmethod
from collections import defaultdict
import bpy
from bpy.types import NodeTree, NodeSocket, Node
from . import import_vtf


class VMTData(NamedTuple):
    width: int
    height: int
    material: bpy.types.Material


class _PosRef():
    def __init__(self, x: int = 0, y: int = 0) -> None:
        self.x = x
        self.y = y

    def loc(self, x: int = 0, y: int = 0) -> Tuple[int, int]:
        return (self.x + x, self.y + y)

    def copy(self, x: int = 0, y: int = 0) -> '_PosRef':
        return _PosRef(self.x + x, self.y + y)


class _MaterialInputBase(ABC):
    def __init__(self, required_inputs: Iterable['_MaterialInputBase'] = ()) -> None:
        self.node: Node = None
        self.required_inputs = list(required_inputs)
        self.dimension_x = 0
        self.dimension_y = 0

    @abstractmethod
    def create(self, node_tree: NodeTree, pos: _PosRef) -> None:
        pass

    def full_create(self, node_tree: NodeTree, pos: _PosRef, created_inputs: Set['_MaterialInputBase']) -> None:
        pos.x -= self.dimension_x
        required_input_pos = pos.copy()
        for required_input in self.required_inputs:
            if required_input in created_inputs:
                continue
            dimension_y = required_input.full_dimension_y(created_inputs)
            required_input.full_create(node_tree, required_input_pos.copy(), created_inputs)
            required_input_pos.y -= dimension_y
        self.create(node_tree, pos)
        created_inputs.add(self)

    def full_dimension_y(self, created_inputs: Set['_MaterialInputBase']) -> int:
        return max(
            self.dimension_y,
            sum(
                required_input.full_dimension_y(created_inputs) for required_input in self.required_inputs
                if required_input not in created_inputs
            )
        )

    def __hash__(self) -> int:
        return hash(id(self))


class _MaterialInputSocket():
    def __init__(self, primary_input: _MaterialInputBase, output: Any):
        self.primary_input = primary_input
        self.output_name = output

    def connect(self, node_tree: NodeTree, input_s: NodeSocket) -> None:
        node_tree.links.new(self.primary_input.node.outputs[self.output_name], input_s)


class _MaterialNode():
    def __init__(self, node_name: str, output_name: Union[str, int],
                 input_name: Union[str, int], used_inputs: Iterable[_MaterialInputSocket] = ()):
        self._node_name = node_name
        self._output_name = output_name
        self._input_name = input_name
        self.used_inputs: List[_MaterialInputBase] = [socket.primary_input for socket in used_inputs]
        self.dimension_x = 0
        self.dimension_y = 0

    def connect_inputs(self, node_tree: NodeTree) -> None:
        return

    def connect(self, node_tree: NodeTree, input_s: NodeSocket, pos: _PosRef) -> NodeSocket:
        self.node: Node = node_tree.nodes.new(self._node_name)
        self.node.location = pos.loc()
        node_tree.links.new(self.node.outputs[self._output_name], input_s)
        return self.node.inputs[self._input_name]


class _MaterialNodePath():
    def __init__(self, min_start_y: int = 0) -> None:
        self.min_start_y = min_start_y
        self.nodes: List[_MaterialNode] = []
        self.input: Optional[_MaterialInputSocket] = None
        self.const: Optional[Any] = None

    def append(self, node: _MaterialNode) -> None:
        self.nodes.append(node)

    def dimension_x(self) -> int:
        if self.input is None:
            return 0
        return sum(node.dimension_x for node in self.nodes)

    def dimension_y(self) -> int:
        return max((node.dimension_y for node in self.nodes), default=0)

    def connect_path(self, node_tree: NodeTree, input_s: NodeSocket, pos: _PosRef) -> Iterator[_MaterialInputBase]:
        if self.input is None:
            if self.const is not None:
                input_s.default_value = self.const
            return
        yielded_inputs: Dict[_MaterialInputBase, _MaterialInputBase] = {}
        for node in reversed(self.nodes):
            pos.x -= node.dimension_x
            input_s = node.connect(node_tree, input_s, pos)
            yield from (yielded_inputs.setdefault(inp, inp) for inp in node.used_inputs if inp not in yielded_inputs)
        self._input_s = input_s
        self._input_pos = pos
        if self.input.primary_input not in yielded_inputs:
            yield self.input.primary_input

    def connect_inputs(self, node_tree: NodeTree) -> None:
        if self.input is None:
            return
        self.input.connect(node_tree, self._input_s)
        for node in self.nodes:
            node.connect_inputs(node_tree)


class _NormalMapMaterialNode(_MaterialNode):
    def __init__(self) -> None:
        super().__init__('ShaderNodeNormalMap', 'Normal', 'Color')
        self.dimension_x = 200
        self.dimension_y = 200


class _InvertMaterialNode(_MaterialNode):
    def __init__(self) -> None:
        super().__init__('ShaderNodeMath', 0, 1)
        self.dimension_x = 200
        self.dimension_y = 200

    def connect(self, node_tree: NodeTree, input_s: NodeSocket, pos: _PosRef) -> NodeSocket:
        input_s = super().connect(node_tree, input_s, pos)
        self.node.operation = 'SUBTRACT'
        self.node.inputs[0].default_value = 1.0
        return input_s


class _MultiplyMaterialNode(_MaterialNode):
    def __init__(self, factor: float) -> None:
        super().__init__('ShaderNodeMath', 0, 0)
        self.factor = factor
        self.dimension_x = 200
        self.dimension_y = 200

    def connect(self, node_tree: NodeTree, input_s: NodeSocket, pos: _PosRef) -> NodeSocket:
        input_s = super().connect(node_tree, input_s, pos)
        self.node.operation = 'MULTIPLY'
        self.node.inputs[1].default_value = self.factor
        return input_s


class _MultiplyRGBMaterialNode(_MaterialNode):
    def __init__(self, factor: Tuple[float, float, float]) -> None:
        super().__init__('ShaderNodeMixRGB', 'Color', 'Color1')
        self.factor = factor
        self.dimension_x = 200
        self.dimension_y = 250

    def connect(self, node_tree: NodeTree, input_s: NodeSocket, pos: _PosRef) -> NodeSocket:
        input_s = super().connect(node_tree, input_s, pos)
        self.node.blend_type = 'MULTIPLY'
        self.node.inputs['Color2'].default_value = (self.factor[0], self.factor[1], self.factor[2], 1)
        return input_s


class _SubtractMaterialNode(_MaterialNode):
    def __init__(self, value: float) -> None:
        super().__init__('ShaderNodeMath', 0, 0)
        self.value = value
        self.dimension_x = 200
        self.dimension_y = 200

    def connect(self, node_tree: NodeTree, input_s: NodeSocket, pos: _PosRef) -> NodeSocket:
        input_s = super().connect(node_tree, input_s, pos)
        self.node.operation = 'SUBTRACT'
        self.node.inputs[1].default_value = self.value
        return input_s


class _SsbumpToNormalMaterialNode(_MaterialNode):
    def __init__(self) -> None:
        super().__init__('ShaderNodeVectorMath', 0, 0)
        self.dimension_x = 850
        self.dimension_y = 600

    def connect(self, node_tree: NodeTree, input_s: NodeSocket, pos: _PosRef) -> NodeSocket:
        input_s = super().connect(node_tree, input_s, pos.copy(700, 0))
        self.node.operation = 'NORMALIZE'
        add_node2: Node = node_tree.nodes.new('ShaderNodeVectorMath')
        add_node2.location = pos.loc(550, 0)
        add_node2.operation = 'ADD'
        node_tree.links.new(add_node2.outputs[0], input_s)
        add_node1: Node = node_tree.nodes.new('ShaderNodeVectorMath')
        add_node1.location = pos.loc(400, 0)
        add_node1.operation = 'ADD'
        node_tree.links.new(add_node1.outputs[0], add_node2.inputs[0])
        multiply_node_x: Node = node_tree.nodes.new('ShaderNodeVectorMath')
        multiply_node_x.location = pos.loc(200, 0)
        multiply_node_x.operation = 'MULTIPLY'
        multiply_node_x.inputs[1].default_value = (0.81649661064147949, 0.0, 0.57735025882720947)
        node_tree.links.new(multiply_node_x.outputs[0], add_node1.inputs[0])
        multiply_node_y: Node = node_tree.nodes.new('ShaderNodeVectorMath')
        multiply_node_y.location = pos.loc(200, 200)
        multiply_node_y.operation = 'MULTIPLY'
        multiply_node_y.inputs[1].default_value = (-0.40824833512306213, 0.70710676908493042, 0.57735025882720947)
        node_tree.links.new(multiply_node_y.outputs[0], add_node1.inputs[1])
        multiply_node_z: Node = node_tree.nodes.new('ShaderNodeVectorMath')
        multiply_node_z.location = pos.loc(200, 400)
        multiply_node_z.operation = 'MULTIPLY'
        multiply_node_z.inputs[1].default_value = (-0.40824821591377258, -0.7071068286895752, 0.57735025882720947)
        node_tree.links.new(multiply_node_z.outputs[0], add_node2.inputs[1])
        separate_node: Node = node_tree.nodes.new('ShaderNodeSeparateXYZ')
        separate_node.location = pos.loc()
        node_tree.links.new(separate_node.outputs['X'], multiply_node_x.inputs[0])
        node_tree.links.new(separate_node.outputs['Y'], multiply_node_y.inputs[0])
        node_tree.links.new(separate_node.outputs['Z'], multiply_node_z.inputs[0])
        return separate_node.inputs['Vector']


class _TextureInputBase(_MaterialInputBase):
    color: _MaterialInputSocket
    channels: '_SplitTextureInput'
    alpha: _MaterialInputSocket

    @abstractmethod
    def setimage(self, image: bpy.types.Image) -> None:
        pass


class _TextureInput(_TextureInputBase):
    def __init__(self) -> None:
        super().__init__()
        self.image: bpy.types.Image = None
        self.color = _MaterialInputSocket(self, 'Color')
        self.channels = _SplitTextureInput(self.color)
        self.alpha = _MaterialInputSocket(self, 'Alpha')
        self.dimension_x = 300
        self.dimension_y = 300

    def setimage(self, image: bpy.types.Image) -> None:
        self.image = image

    def create(self, node_tree: NodeTree, pos: _PosRef) -> None:
        self.node: Node = node_tree.nodes.new('ShaderNodeTexImage')
        self.node.image = self.image
        self.node.location = pos.loc()


class _TransformedTextureInput(_TextureInput):
    def __init__(self, scale: Tuple[float, float] = (1, 1), rotate: float = 0, translate: Tuple[float, float] = (1, 1)):
        super().__init__()
        self.scale = scale
        self.rotate = rotate
        self.translate = translate
        self.dimension_x = 700
        self.dimension_y = 400

    def create(self, node_tree: NodeTree, pos: _PosRef) -> None:
        super().create(node_tree, pos)
        coord_node: Node = node_tree.nodes.new('ShaderNodeTexCoord')
        coord_node.location = pos.loc()
        map_node: Node = node_tree.nodes.new('ShaderNodeMapping')
        map_node.inputs['Scale'].default_value = (self.scale[0], self.scale[1], 1)
        map_node.inputs['Rotation'].default_value = (0, 0, self.rotate)
        map_node.inputs['Location'].default_value = (self.translate[0], self.translate[1], 0)
        map_node.location = pos.loc(200)
        node_tree.links.new(coord_node.outputs['UV'], map_node.inputs['Vector'])
        self.node.location = pos.loc(400)
        node_tree.links.new(map_node.outputs['Vector'], self.node.inputs['Vector'])


class _SplitTextureInput(_MaterialInputBase):
    def __init__(self, texture_input: _MaterialInputSocket) -> None:
        super().__init__((texture_input.primary_input, ))
        self.input = texture_input
        self.r = _MaterialInputSocket(self, 'R')
        self.g = _MaterialInputSocket(self, 'G')
        self.b = _MaterialInputSocket(self, 'B')
        self.dimension_x = 200
        self.dimension_y = 200

    def create(self, node_tree: NodeTree, pos: _PosRef) -> None:
        self.node: Node = node_tree.nodes.new('ShaderNodeSeparateRGB')
        self.node.location = pos.loc()
        self.input.connect(node_tree, self.node.inputs['Image'])


class _BlendedTextureInput(_TextureInputBase):
    def __init__(self, fac_inp: _MaterialInputSocket, a_inp: _TextureInputBase, b_inp: _TextureInputBase) -> None:
        super().__init__()
        self.input1 = a_inp
        self.input2 = b_inp
        self.color: _MaterialInputSocket = _BlendedColorInput(fac_inp, self.input1.color, self.input2.color).color
        self.channels = _SplitTextureInput(self.color)
        self.alpha: _MaterialInputSocket = _BlendedValueInput(fac_inp, self.input1.alpha, self.input2.alpha).value

    def setimage(self, image: bpy.types.Image) -> None:
        self.input1.setimage(image)

    def create(self, node_tree: NodeTree, pos: _PosRef) -> None:
        return


class _DetailedTextureInput(_TextureInputBase):
    def __init__(self, base_inp: _TextureInputBase, detail_inp: _TextureInputBase, blend: float = 1) -> None:
        super().__init__((base_inp, detail_inp))
        self.base_inp = base_inp
        self.detail_inp = detail_inp
        self.blend = blend
        self.color = _MaterialInputSocket(self, 'Color')
        self.channels = _SplitTextureInput(self.color)
        self.alpha = base_inp.alpha
        self.dimension_x = 400
        self.dimension_y = 250

    def setimage(self, image: bpy.types.Image) -> None:
        self.base_inp.setimage(image)

    def create(self, node_tree: NodeTree, pos: _PosRef) -> None:
        mul_node: Node = node_tree.nodes.new('ShaderNodeMixRGB')
        mul_node.blend_type = 'MULTIPLY'
        mul_node.location = pos.loc()
        mul_node.inputs['Color2'].default_value = (2, 2, 2, 1)
        mul_node.inputs['Fac'].default_value = 1
        self.detail_inp.color.connect(node_tree, mul_node.inputs['Color1'])
        self.node: Node = node_tree.nodes.new('ShaderNodeMixRGB')
        self.node.location = pos.loc(200)
        self.node.blend_type = 'MULTIPLY'
        self.node.inputs['Fac'].default_value = self.blend
        self.base_inp.color.connect(node_tree, self.node.inputs['Color1'])
        node_tree.links.new(mul_node.outputs['Color'], self.node.inputs['Color2'])


class _BlendedColorInput(_MaterialInputBase):
    def __init__(self, fac_inp: _MaterialInputSocket, a_inp: _MaterialInputSocket, b_inp: _MaterialInputSocket):
        super().__init__((fac_inp.primary_input, a_inp.primary_input, b_inp.primary_input))
        self.fac_inp = fac_inp
        self.a_inp = a_inp
        self.b_inp = b_inp
        self.color = _MaterialInputSocket(self, 'Color')
        self.dimension_x = 200
        self.dimension_y = 250

    def create(self, node_tree: NodeTree, pos: _PosRef) -> None:
        self.node: Node = node_tree.nodes.new('ShaderNodeMixRGB')
        self.node.location = pos.loc()
        self.node.blend_type = 'MIX'
        self.fac_inp.connect(node_tree, self.node.inputs['Fac'])
        self.a_inp.connect(node_tree, self.node.inputs['Color1'])
        self.b_inp.connect(node_tree, self.node.inputs['Color2'])


class _BlendedValueInput(_MaterialInputBase):
    def __init__(self, fac_inp: _MaterialInputSocket, a_inp: _MaterialInputSocket, b_inp: _MaterialInputSocket):
        super().__init__((fac_inp.primary_input, a_inp.primary_input, b_inp.primary_input))
        self.fac_inp = fac_inp
        self.a_inp = a_inp
        self.b_inp = b_inp
        self.value = _MaterialInputSocket(self, 'Result')
        self.dimension_x = 200
        self.dimension_y = 250

    def create(self, node_tree: NodeTree, pos: _PosRef) -> None:
        self.node: Node = node_tree.nodes.new('ShaderNodeMapRange')
        self.node.location = pos.loc()
        self.node.inputs['From Min'].default_value = 0
        self.node.inputs['From Max'].default_value = 1
        self.node.clamp = False
        self.a_inp.connect(node_tree, self.node.inputs['To Min'])
        self.b_inp.connect(node_tree, self.node.inputs['To Max'])
        self.fac_inp.connect(node_tree, self.node.inputs['Value'])


class _BlendedConstantInput(_MaterialInputBase):
    def __init__(self, fac_inp: _MaterialInputSocket, a_const: float = 0.0, b_const: float = 0.0):
        super().__init__((fac_inp.primary_input, ))
        self.fac_inp = fac_inp
        self.a_const = a_const
        self.b_const = b_const
        self.const = _MaterialInputSocket(self, 'Result')
        self.dimension_x = 200
        self.dimension_y = 250

    def create(self, node_tree: NodeTree, pos: _PosRef) -> None:
        self.node: Node = node_tree.nodes.new('ShaderNodeMapRange')
        self.node.location = pos.loc()
        self.node.inputs['From Min'].default_value = 0
        self.node.inputs['From Max'].default_value = 1
        self.node.clamp = False
        self.node.inputs['To Min'].default_value = self.a_const
        self.node.inputs['To Max'].default_value = self.b_const
        self.fac_inp.connect(node_tree, self.node.inputs['Value'])


class _VertexColorInput(_MaterialInputBase):
    def __init__(self) -> None:
        super().__init__()
        self.color = _MaterialInputSocket(self, 'Color')
        self.alpha = _MaterialInputSocket(self, 'Alpha')
        self.dimension_x = 200
        self.dimension_y = 150

    def create(self, node_tree: NodeTree, pos: _PosRef) -> None:
        self.node: Node = node_tree.nodes.new('ShaderNodeVertexColor')
        self.node.layer_name = "Col"
        self.node.location = pos.loc()


class _ModulatedBlendFactorInput(_MaterialInputBase):
    def __init__(self, mod_ch_input: _SplitTextureInput, vertex_alpha_inp: _MaterialInputSocket):
        super().__init__((mod_ch_input, vertex_alpha_inp.primary_input))
        self.mod_ch_input = mod_ch_input
        self.vertex_alpha_inp = vertex_alpha_inp
        self.fac = _MaterialInputSocket(self, 0)
        self.dimension_x = 400
        self.dimension_y = 300

    def create(self, node_tree: NodeTree, pos: _PosRef) -> None:
        sub_node: Node = node_tree.nodes.new('ShaderNodeMath')
        sub_node.operation = 'SUBTRACT'
        sub_node.use_clamp = True
        sub_node.location = pos.loc()
        self.mod_ch_input.g.connect(node_tree, sub_node.inputs[0])
        self.mod_ch_input.r.connect(node_tree, sub_node.inputs[1])
        add_node: Node = node_tree.nodes.new('ShaderNodeMath')
        add_node.operation = 'ADD'
        add_node.use_clamp = True
        add_node.location = pos.loc(0, -150)
        self.mod_ch_input.g.connect(node_tree, add_node.inputs[0])
        self.mod_ch_input.r.connect(node_tree, add_node.inputs[1])
        self.node: Node = node_tree.nodes.new('ShaderNodeMapRange')
        self.node.location = pos.loc(200)
        self.node.interpolation_type = 'SMOOTHSTEP'
        self.node.inputs['To Min'].default_value = 0
        self.node.inputs['To Max'].default_value = 1
        self.node.clamp = False
        node_tree.links.new(sub_node.outputs[0], self.node.inputs['From Min'])
        node_tree.links.new(add_node.outputs[0], self.node.inputs['From Max'])
        self.vertex_alpha_inp.connect(node_tree, self.node.inputs['Value'])


_NODRAW_PARAMS = frozenset((
    "%compilenodraw", "%compileinvisible", "%compilehint", "%compileskip",
    "%compilesky", "%compile2dsky", "%compiletrigger", "%compileorigin", "%compilefog",
    "%compilenpcclip", "%compileplayerclip", "%compiledroneclip", "%compilegrenadeclip", "%compileclip",
    "$no_draw"
))


_SUPPORTED_PARAMS = frozenset((
    "$basetexture", "$basetexturetransform", "$basetexture2", "$basetexturetransform2", "$vertexcolor", "$color",
    "$bumpmap", "$bumptransform", "$bumpmap2", "$bumptransform2", "$ssbump",
    "$translucent", "$alphatest", "$alphatestreference", "$alpha", "$vertexalpha",
    "$phong", "$basemapalphaphongmask", "$basemapluminancephongmask", "$phongexponent", "$phongexponent2",
    "$phongexponenttexture", "$phongalbedotint",
    "$detail", "$detailblendmode", "$detailtexturetransform", "$detail2", "$detailtexturetransform2",
    "$detailblendfactor", "$detailblendfactor2", "$detailscale", "$detailscale2",
    "$envmap", "$basealphaenvmapmask", "$basealphaenvmask", "$normalmapalphaenvmapmask",
    "$envmapmask", "$envmapmasktransform", "$envmaptint",
    "$selfillum_envmapmask_alpha", "$selfillum", "$selfillummask",
    "$blendmodulatetexture", "$blendmodulatetransform", "$masks1", "$metalness",
    # ignored parameters
    "%keywords", "%compilepassbullets", "%compilenonsolid", "%tooltexture",
    "$surfaceprop", "$surfaceprop2", "$nocull", "$model",
))


class _MaterialBuilder():
    def __init__(self, vtf_importer: import_vtf.VTFImporter, name: str, vmt_data: vmt.VMT):
        self._vtf_importer = vtf_importer
        self.name = name
        self.width = 1
        self.height = 1
        self.nodraw = False
        self.blend_method = 'OPAQUE'
        self.shadow_method = 'OPAQUE'
        self._shader_dict: Dict[str, _MaterialNodePath] = {
            'Base Color': _MaterialNodePath(0),
            'Metallic': _MaterialNodePath(-150),
            'Specular': _MaterialNodePath(-160),
            'Specular Tint': _MaterialNodePath(-170),
            'Roughness': _MaterialNodePath(-180),
            'Emission': _MaterialNodePath(-400),
            'Alpha': _MaterialNodePath(-410),
            'Normal': _MaterialNodePath(-420),
        }
        texture_inputs: DefaultDict[str, _TextureInputBase] = defaultdict(lambda: _TextureInput())
        vertex_col_input = _VertexColorInput()
        params = vmt_data.parameters

        # flags that imply nodraw
        if any(p in _NODRAW_PARAMS and vmt_data.param_as_bool(p) for p in params):
            self.blend_method = 'CLIP'
            self.shadow_method = 'CLIP'
            self.nodraw = True
            return
        blend_input = vertex_col_input.alpha

        if "$basetexture" in params:
            image = self._vtf_importer.load(params["$basetexture"], vmt_data.param_open_texture("$basetexture"))
            image.alpha_mode = 'CHANNEL_PACKED'
            image.colorspace_settings.name = 'sRGB'
            if "$basetexturetransform" in params:
                transform = vmt_data.param_as_transform("$basetexturetransform")
                if transform.scale != (1, 1) or transform.rotate != 0 or transform.translate != (0, 0):
                    texture_inputs["$basetexture"] = _TransformedTextureInput(
                        transform.scale, transform.rotate, transform.translate
                    )
            texture_inputs["$basetexture"].setimage(image)
            self.width, self.height = image.size
            if "$blendmodulatetexture" in params:
                bimage = self._vtf_importer.load(
                    params["$blendmodulatetexture"], vmt_data.param_open_texture("$blendmodulatetexture")
                )
                bimage.colorspace_settings.name = 'Non-Color'
                if "$blendmodulatetransform" in params:
                    transform = vmt_data.param_as_transform("$blendmodulatetransform")
                    if transform.scale != (1, 1) or transform.rotate != 0 or transform.translate != (0, 0):
                        texture_inputs["$blendmodulatetexture"] = _TransformedTextureInput(
                            transform.scale, transform.rotate, transform.translate
                        )
                texture_inputs["$blendmodulatetexture"].setimage(bimage)
                blend_input = _ModulatedBlendFactorInput(
                    texture_inputs["$blendmodulatetexture"].channels, vertex_col_input.alpha
                ).fac
            if "$detail" in params and ("$detailblendmode" not in params
                                        or vmt_data.param_as_int("$detailblendmode") == 0):  # TODO: other blend modes
                dimage = self._vtf_importer.load(params["$detail"], vmt_data.param_open_texture("$detail"))
                dimage.colorspace_settings.name = 'Non-Color'
                scale = (1, 1)
                if "$detailscale" in params:
                    try:
                        scale_x, scale_y, _ = vmt_data.param_as_vec3("$detailscale")
                    except vmt.VMTParseException:
                        try:  # ...
                            scale_x, scale_y = vmt_data.param_as_vec2("$detailscale")
                        except vmt.VMTParseException:  # thank you valve for consistency
                            scale_x = scale_y = vmt_data.param_as_float("$detailscale")
                    scale = (scale[0] * scale_x, scale[1] * scale_y)
                if "$detailtexturetransform" in params:
                    transform = vmt_data.param_as_transform("$detailtexturetransform")
                    scale = (scale[0] * transform.scale[0], scale[1] * transform.scale[1])
                    rotate = transform.rotate
                    translate = transform.translate
                else:
                    rotate = 0
                    translate = (0, 0)
                if scale != (1, 1) or rotate != 0 or translate != (0, 0):
                    texture_inputs["$detail"] = _TransformedTextureInput(scale, rotate, translate)
                texture_inputs["$detail"].setimage(dimage)
                blend_fac = vmt_data.param_as_float("$detailblendfactor") if "$detailblendfactor" in params else 1
                texture_inputs["$basetexture"] = _DetailedTextureInput(
                    texture_inputs["$basetexture"], texture_inputs["$detail"], blend_fac
                )
            if "$basetexture2" in params:
                image2 = self._vtf_importer.load(params["$basetexture2"], vmt_data.param_open_texture("$basetexture2"))
                image2.alpha_mode = 'CHANNEL_PACKED'
                image2.colorspace_settings.name = 'sRGB'
                if "$basetexturetransform2" in params:
                    transform = vmt_data.param_as_transform("$basetexturetransform2")
                    if transform.scale != (1, 1) or transform.rotate != 0 or transform.translate != (0, 0):
                        texture_inputs["$basetexture2"] = _TransformedTextureInput(
                            transform.scale, transform.rotate, transform.translate
                        )
                texture_inputs["$basetexture2"].setimage(image2)
                if "$detail2" in params:
                    dimage2 = self._vtf_importer.load(params["$detail2"], vmt_data.param_open_texture("$detail2"))
                    dimage2.colorspace_settings.name = 'Non-Color'
                    scale = (1, 1)
                    if "$detailscale2" in params:
                        try:
                            scale_x, scale_y, _ = vmt_data.param_as_vec3("$detailscale2")
                        except vmt.VMTParseException:
                            try:
                                scale_x, scale_y = vmt_data.param_as_vec2("$detailscale2")
                            except vmt.VMTParseException:
                                scale_x = scale_y = vmt_data.param_as_float("$detailscale2")
                        scale = (scale[0] * scale_x, scale[1] * scale_y)
                    if "$detailtexturetransform2" in params:
                        transform = vmt_data.param_as_transform("$detailtexturetransform2")
                        scale = (scale[0] * transform.scale[0], scale[1] * transform.scale[1])
                        rotate = transform.rotate
                        translate = transform.translate
                    else:
                        rotate = 0
                        translate = (0, 0)
                    if scale != (1, 1) or rotate != 0 or translate != (0, 0):
                        texture_inputs["$detail2"] = _TransformedTextureInput(scale, rotate, translate)
                    texture_inputs["$detail2"].setimage(dimage2)
                    blend_fac = vmt_data.param_as_float("$detailblendfactor2") if "$detailblendfactor2" in params else 1
                    texture_inputs["$basetexture2"] = _DetailedTextureInput(
                        texture_inputs["$basetexture2"], texture_inputs["$detail2"], blend_fac
                    )
                blended = _BlendedTextureInput(
                    blend_input, texture_inputs["$basetexture"], texture_inputs["$basetexture2"]
                )
                texture_inputs["$basetexture"] = blended
            self._shader_dict['Base Color'].input = texture_inputs["$basetexture"].color
            if "$color" in params:
                self._shader_dict['Base Color'].append(_MultiplyRGBMaterialNode(vmt_data.param_as_color("$color")))
        elif "$color" in params:
            self._shader_dict['Base Color'].const = vmt_data.param_as_color("$color") + (1,)
        elif vmt_data.param_flag("$vertexcolor"):
            self._shader_dict['Base Color'].input = vertex_col_input.color

        if "$bumpmap" in params:
            image = self._vtf_importer.load(params["$bumpmap"], vmt_data.param_open_texture("$bumpmap"))
            image.colorspace_settings.name = 'Non-Color'
            if "$bumptransform" in params:
                transform = vmt_data.param_as_transform("$bumptransform")
                if transform.scale != (1, 1) or transform.rotate != 0 or transform.translate != (0, 0):
                    texture_inputs["$bumpmap"] = _TransformedTextureInput(
                        transform.scale, transform.rotate, transform.translate
                    )
            texture_inputs["$bumpmap"].setimage(image)
            if "$bumpmap2" in params:
                image2 = self._vtf_importer.load(params["$bumpmap2"], vmt_data.param_open_texture("$bumpmap2"))
                image2.colorspace_settings.name = 'Non-Color'
                if "$bumptransform2" in params:
                    transform = vmt_data.param_as_transform("$bumptransform2")
                    if transform.scale != (1, 1) or transform.rotate != 0 or transform.translate != (0, 0):
                        texture_inputs["$bumpmap2"] = _TransformedTextureInput(
                            transform.scale, transform.rotate, transform.translate
                        )
                texture_inputs["$bumpmap2"].setimage(image2)
                blended = _BlendedTextureInput(blend_input, texture_inputs["$bumpmap"], texture_inputs["$bumpmap2"])
                texture_inputs["$bumpmap"] = blended
            self._shader_dict['Normal'].input = texture_inputs["$bumpmap"].color
            if vmt_data.param_flag("$ssbump"):
                self._shader_dict['Normal'].append(_SsbumpToNormalMaterialNode())
            else:
                self._shader_dict['Normal'].append(_NormalMapMaterialNode())
        elif "$detail" in params and "$detailblendmode" in params and vmt_data.param_as_int("$detailblendmode") == 10:
            dimage = self._vtf_importer.load(params["$detail"], vmt_data.param_open_texture("$detail"))
            dimage.colorspace_settings.name = 'Non-Color'
            scale = (1, 1)
            if "$detailscale" in params:
                try:
                    scale_x, scale_y, _ = vmt_data.param_as_vec3("$detailscale")
                except vmt.VMTParseException:
                    try:
                        scale_x, scale_y = vmt_data.param_as_vec2("$detailscale")
                    except vmt.VMTParseException:
                        scale_x = scale_y = vmt_data.param_as_float("$detailscale")
                scale = (scale[0] * scale_x, scale[1] * scale_y)
            if "$detailtexturetransform" in params:
                transform = vmt_data.param_as_transform("$detailtexturetransform")
                scale = (scale[0] * transform.scale[0], scale[1] * transform.scale[1])
                rotate = transform.rotate
                translate = transform.translate
            else:
                rotate = 0
                translate = (0, 0)
            if scale != (1, 1) or rotate != 0 or translate != (0, 0):
                texture_inputs["$detail"] = _TransformedTextureInput(scale, rotate, translate)
            texture_inputs["$detail"].setimage(dimage)
            self._shader_dict['Normal'].input = texture_inputs["$detail"].color
            self._shader_dict['Normal'].append(_SsbumpToNormalMaterialNode())

        if "$alpha" in params:
            self._shader_dict['Alpha'].const = vmt_data.param_as_float("$alpha")
        elif vmt_data.param_flag("$translucent"):
            self.blend_method = 'BLEND'
            self.shadow_method = 'HASHED'
            self._shader_dict['Alpha'].input = texture_inputs["$basetexture"].alpha
        elif vmt_data.param_flag("$alphatest"):
            self.blend_method = 'CLIP'
            self.shadow_method = 'CLIP'
            self._shader_dict['Alpha'].input = texture_inputs["$basetexture"].alpha
            if "$alphatestreference" in params:
                self._shader_dict['Alpha'].append(
                    _SubtractMaterialNode(1 - vmt_data.param_as_float("$alphatestreference"))
                )
        elif vmt_data.param_flag("$vertexalpha"):
            self.blend_method = 'BLEND'
            self.shadow_method = 'HASHED'
            self._shader_dict['Alpha'].input = vertex_col_input.alpha

        if "$masks1" in params:
            image = self._vtf_importer.load(params["$masks1"], vmt_data.param_open_texture("$masks1"))
            image.colorspace_settings.name = 'Non-Color'
            texture_inputs["$masks1"].setimage(image)
            masks1 = True
        else:
            masks1 = False

        if vmt_data.param_flag("$phong") or vmt_data.shader == "character":
            if vmt_data.param_flag("$basemapluminancephongmask"):
                self._shader_dict['Specular'].input = texture_inputs["$basetexture"].color
            elif vmt_data.param_flag("$basemapalphaphongmask"):
                self._shader_dict['Specular'].input = texture_inputs["$basetexture"].alpha
            elif masks1:
                self._shader_dict['Specular'].input = texture_inputs["$masks1"].channels.g
            else:
                self._shader_dict['Specular'].input = texture_inputs["$bumpmap"].alpha
            if "$phongexponent" in params:
                if "$phongexponent2" in params:
                    self._shader_dict['Roughness'].input = _BlendedConstantInput(
                        blend_input,
                        ((150 - vmt_data.param_as_float("$phongexponent")) / 150) * 0.5,
                        ((150 - vmt_data.param_as_float("$phongexponent2")) / 150) * 0.5,
                    ).const
                else:
                    self._shader_dict['Roughness'].const = (
                        (150 - vmt_data.param_as_float("$phongexponent")) / 150
                    ) * 0.5
            elif "$phongexponenttexture" in params:
                image = self._vtf_importer.load(
                    params["$phongexponenttexture"],
                    vmt_data.param_open_texture("$phongexponenttexture")
                )
                image.colorspace_settings.name = 'Non-Color'
                texture_inputs["$phongexponenttexture"].setimage(image)
                self._shader_dict['Roughness'].input = texture_inputs["$phongexponenttexture"].channels.r
                self._shader_dict['Roughness'].append(_InvertMaterialNode())
                self._shader_dict['Roughness'].append(_MultiplyMaterialNode(0.5))
                if vmt_data.param_flag("$phongalbedotint"):
                    self._shader_dict['Specular Tint'].input = texture_inputs["$phongexponenttexture"].channels.g
            else:
                self._shader_dict['Roughness'].const = 0.3
        elif "$envmap" in params:
            if vmt_data.param_flag("$basealphaenvmapmask") or vmt_data.param_flag("$basealphaenvmask"):
                self._shader_dict['Specular'].input = texture_inputs["$basetexture"].alpha
                self._shader_dict['Specular'].append(_InvertMaterialNode())
            elif vmt_data.param_flag("$normalmapalphaenvmapmask"):
                self._shader_dict['Specular'].input = texture_inputs["$bumpmap"].alpha
            elif "$envmapmask" in params:
                image = self._vtf_importer.load(params["$envmapmask"], vmt_data.param_open_texture("$envmapmask"))
                image.colorspace_settings.name = 'Non-Color'
                if "$envmapmasktransform" in params:
                    transform = vmt_data.param_as_transform("$envmapmasktransform")
                    if transform.scale != (1, 1) or transform.rotate != 0 or transform.translate != (0, 0):
                        texture_inputs["$envmapmask"] = _TransformedTextureInput(
                            transform.scale, transform.rotate, transform.translate
                        )
                texture_inputs["$envmapmask"].setimage(image)
                self._shader_dict['Specular'].input = texture_inputs["$envmapmask"].color
                if "$envmaptint" in params:
                    tint = vmt_data.param_as_vec3("$envmaptint")
                    self._shader_dict['Specular'].append(_MultiplyMaterialNode(sum(tint) / 3))
            elif "$envmaptint" in params:
                tint = vmt_data.param_as_vec3("$envmaptint")
                self._shader_dict['Specular'].const = sum(tint) / 3
            else:
                self._shader_dict['Specular'].const = 0.8
            self._shader_dict['Roughness'].const = 0.1

        if masks1:
            self._shader_dict['Metallic'].input = texture_inputs["$masks1"].channels.b
        elif "$metalness" in params:
            self._shader_dict['Metallic'].const = vmt_data.param_as_float("$metalness")

        if vmt_data.param_flag("$selfillum_envmapmask_alpha"):
            self._shader_dict['Emission'].input = texture_inputs["$envmapmask"].alpha
        elif vmt_data.param_flag("$selfillum"):
            if "$selfillummask" in params:
                image = self._vtf_importer.load(params["$selfillummask"], vmt_data.param_open_texture("$selfillummask"))
                image.colorspace_settings.name = 'Non-Color'
                texture_inputs["$selfillummask"].setimage(image)
                self._shader_dict['Emission'].input = texture_inputs["$selfillummask"].color
            else:
                self._shader_dict['Emission'].input = texture_inputs["$basetexture"].alpha

        unsupported_params = [p for p in params if p not in _SUPPORTED_PARAMS]
        if len(unsupported_params) != 0:
            print(f"WARNING: UNSUPPORTED MATERIAL PARAMS: {', '.join(unsupported_params)} in {name}")

    def build(self) -> bpy.types.Material:
        material: bpy.types.Material = bpy.data.materials.new(self.name)
        material.use_nodes = True
        material.blend_method = self.blend_method
        material.shadow_method = self.shadow_method
        nt = material.node_tree
        nt.nodes.clear()
        pos_ref = _PosRef()
        out_node: Node = nt.nodes.new('ShaderNodeOutputMaterial')
        out_node.location = pos_ref.loc()
        pos_ref.x -= 300
        if self.nodraw:
            shader_node: Node = nt.nodes.new('ShaderNodeBsdfTransparent')
        else:
            shader_node = nt.nodes.new('ShaderNodeBsdfPrincipled')
        shader_node.location = pos_ref.loc()
        pos_ref.x -= 100
        nt.links.new(shader_node.outputs['BSDF'], out_node.inputs['Surface'])
        if self.nodraw:
            return material
        required_inputs: Dict[_MaterialInputBase, None] = {}  # Waiting for ordered sets
        paths_pos_ref = pos_ref.copy()
        path_end_pos_x = 0
        for socket_name in self._shader_dict:
            paths_pos_ref.y = min(paths_pos_ref.y, self._shader_dict[socket_name].min_start_y)
            path_pos_ref = paths_pos_ref.copy()
            required_inputs.update(map(
                lambda x: (x, None),
                self._shader_dict[socket_name].connect_path(nt, shader_node.inputs[socket_name], path_pos_ref)
            ))
            if path_pos_ref.x < path_end_pos_x:
                path_end_pos_x = path_pos_ref.x
            paths_pos_ref.y -= self._shader_dict[socket_name].dimension_y()
        created_inputs: Set[_MaterialInputBase] = set()
        input_pos_ref = pos_ref.copy()
        input_pos_ref.x = path_end_pos_x - 100
        for material_input in required_inputs:
            if material_input in created_inputs:
                continue
            dimension_y = material_input.full_dimension_y(created_inputs)
            material_input.full_create(nt, input_pos_ref.copy(), created_inputs)
            input_pos_ref.y -= dimension_y
        for socket_name in self._shader_dict:
            self._shader_dict[socket_name].connect_inputs(nt)
        return material


class VMTImporter():
    def __init__(self, verbose: bool = False) -> None:
        self.verbose = verbose
        self._cache: Dict[str, VMTData] = {}
        self._vtf_importer = import_vtf.VTFImporter()

    def load(self, material_name: str, vmt_data: Callable[[], vmt.VMT]) -> VMTData:
        material_name = material_name.lower()
        if material_name in self._cache:
            return self._cache[material_name]
        if self.verbose:
            print(f"Building material {material_name}...")
        builder = _MaterialBuilder(self._vtf_importer, material_name, vmt_data())
        material = builder.build()
        data = VMTData(builder.width, builder.height, material)
        self._cache[material_name] = data
        return data
