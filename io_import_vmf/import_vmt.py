from vmfpy import vmt
from vmfpy.fs import VMFFileSystem
from .utils import truncate_name, is_invisible_tool
from typing import NamedTuple, Dict, DefaultDict, Set, Tuple, Optional, Union, Any, Iterator, Iterable, List, Callable
from abc import ABC, abstractmethod
from collections import defaultdict
import traceback
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


class _DXNormalMapConverterMaterialNode(_MaterialNode):
    def __init__(self) -> None:
        super().__init__('ShaderNodeCombineRGB', 'Image', 'G')
        self.dimension_x = 600
        self.dimension_y = 200

    def connect(self, node_tree: NodeTree, input_s: NodeSocket, pos: _PosRef) -> NodeSocket:
        separate_node: Node = node_tree.nodes.new('ShaderNodeSeparateRGB')
        separate_node.location = pos.loc()
        invert_node: Node = node_tree.nodes.new('ShaderNodeMath')
        invert_node.location = pos.loc(200)
        invert_node.operation = 'SUBTRACT'
        invert_node.inputs[0].default_value = 1.0
        node_tree.links.new(separate_node.outputs['G'], invert_node.inputs[1])
        g_input = super().connect(node_tree, input_s, pos.copy(400))
        node_tree.links.new(separate_node.outputs['R'], self.node.inputs['R'])
        node_tree.links.new(invert_node.outputs[0], g_input)
        node_tree.links.new(separate_node.outputs['B'], self.node.inputs['B'])
        return separate_node.inputs['Image']


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
    def __init__(self, color: Union[Tuple[float, float, float], _MaterialInputSocket],
                 factor: Union[float, _MaterialInputSocket] = 1) -> None:
        inputs = []
        if isinstance(color, _MaterialInputSocket):
            inputs.append(color)
        if isinstance(factor, _MaterialInputSocket):
            inputs.append(factor)
        super().__init__('ShaderNodeMixRGB', 'Color', 'Color1', inputs)
        self.color = color
        self.factor = factor
        self.dimension_x = 200
        self.dimension_y = 250

    def connect(self, node_tree: NodeTree, input_s: NodeSocket, pos: _PosRef) -> NodeSocket:
        input_s = super().connect(node_tree, input_s, pos)
        self.node.blend_type = 'MULTIPLY'
        if not isinstance(self.factor, _MaterialInputSocket):
            self.node.inputs['Fac'].default_value = self.factor
        if not isinstance(self.color, _MaterialInputSocket):
            self.node.inputs['Color2'].default_value = (self.color[0], self.color[1], self.color[2], 1)
        return input_s

    def connect_inputs(self, node_tree: NodeTree) -> None:
        if isinstance(self.factor, _MaterialInputSocket):
            self.factor.connect(node_tree, self.node.inputs['Fac'])
        if isinstance(self.color, _MaterialInputSocket):
            self.color.connect(node_tree, self.node.inputs['Color2'])


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
    def __init__(self, interpolation: str = 'Linear') -> None:
        super().__init__()
        self.interpolation = interpolation
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
        self.node.interpolation = self.interpolation
        self.node.location = pos.loc()


class _TransformedTextureInput(_TextureInput):
    def __init__(self, scale: Tuple[float, float] = (1, 1), rotate: float = 0, translate: Tuple[float, float] = (1, 1),
                 interpolation: str = 'Linear'):
        super().__init__(interpolation)
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
    def __init__(self, fac_inp: Union[_MaterialInputSocket, float],
                 a_inp: _TextureInputBase, b_inp: _TextureInputBase) -> None:
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
    def __init__(self, fac_inp: Union[_MaterialInputSocket, float],
                 a_inp: _MaterialInputSocket, b_inp: _MaterialInputSocket):
        if isinstance(fac_inp, _MaterialInputSocket):
            super().__init__((fac_inp.primary_input, a_inp.primary_input, b_inp.primary_input))
        else:
            super().__init__((a_inp.primary_input, b_inp.primary_input))
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
        if isinstance(self.fac_inp, _MaterialInputSocket):
            self.fac_inp.connect(node_tree, self.node.inputs['Fac'])
        else:
            self.node.inputs['Fac'].default_value = self.fac_inp
        self.a_inp.connect(node_tree, self.node.inputs['Color1'])
        self.b_inp.connect(node_tree, self.node.inputs['Color2'])


class _BlendedValueInput(_MaterialInputBase):
    def __init__(self, fac_inp: Union[_MaterialInputSocket, float],
                 a_inp: _MaterialInputSocket, b_inp: _MaterialInputSocket):
        if isinstance(fac_inp, _MaterialInputSocket):
            super().__init__((fac_inp.primary_input, a_inp.primary_input, b_inp.primary_input))
        else:
            super().__init__((a_inp.primary_input, b_inp.primary_input))
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
        if isinstance(self.fac_inp, _MaterialInputSocket):
            self.fac_inp.connect(node_tree, self.node.inputs['Value'])
        else:
            self.node.inputs['Value'].default_value = self.fac_inp


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


class _ObjectColorInput(_MaterialInputBase):
    def __init__(self) -> None:
        super().__init__()
        self.color = _MaterialInputSocket(self, 'Color')
        self.dimension_x = 200
        self.dimension_y = 200

    def create(self, node_tree: NodeTree, pos: _PosRef) -> None:
        self.node: Node = node_tree.nodes.new('ShaderNodeObjectInfo')
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


_NODRAW_MATERIALS = frozenset((
    "tools/toolsareaportal", "tools/toolsoccluder",
))


_NODRAW_PARAMS = frozenset((
    "%compilenodraw", "%compileinvisible", "%compilehint", "%compileskip",
    "%compilesky", "%compile2dsky", "%compiletrigger", "%compileorigin", "%compilefog",
    "%compilenpcclip", "%compileplayerclip", "%compiledroneclip", "%compilegrenadeclip", "%compileclip",
    "$no_draw"
))


_SUPPORTED_PARAMS = frozenset((
    "$basetexture", "$basetexturetransform", "$basetexture2", "$basetexturetransform2", "$vertexcolor", "$color",
    "$bumpmap", "$bumptransform", "$bumpmap2", "$bumptransform2", "$ssbump",
    "$addbumpmaps", "$bumpdetailscale1", "$bumpdetailscale2",
    "$translucent", "$alphatest", "$alphatestreference", "$allowalphatocoverage", "$alpha", "$vertexalpha",
    "$phong", "$basemapalphaphongmask", "$basemapluminancephongmask", "$phongexponent", "$phongexponent2",
    "$phongexponenttexture", "$phongalbedotint",
    "$detail", "$detailblendmode", "$detailtexturetransform", "$detail2", "$detailtexturetransform2",
    "$detailblendfactor", "$detailblendfactor2", "$detailscale", "$detailscale2",
    "$envmap", "$basealphaenvmapmask", "$basealphaenvmask", "$normalmapalphaenvmapmask",
    "$envmapmask", "$envmapmasktransform", "$envmaptint", "$envmapmaskintintmasktexture",
    "$selfillum_envmapmask_alpha", "$selfillum", "$selfillummask",
    "$blendmodulatetexture", "$blendmodulatetransform", "$masks1", "$metalness", "$nocull", "%compilenolight",
    "%compilewater", "$normalmap", "$fogenable", "$fogcolor",
    "$color2", "$allowdiffusemodulation", "$notint", "$blendtintbybasealpha", "$tintmasktexture",
    # ignored parameters
    "%keywords", "%compilepassbullets", "%compilenonsolid", "%tooltexture",
    "$surfaceprop", "$surfaceprop2", "$model", "$reflectivity", "$decal", "$decalscale"
))


class _MaterialBuilder():
    def __init__(self, vtf_importer: import_vtf.VTFImporter, name: str, vmt_data: vmt.VMT,
                 simple: bool = False, interpolation: str = 'Linear', cull: bool = False):
        self._vtf_importer = vtf_importer
        self.name = name
        self.simple = simple
        self.width = 1
        self.height = 1
        self.nodraw = False
        self.water = False
        self.blend_method = 'OPAQUE'
        self.shadow_method = 'OPAQUE'
        self.alpha_reference = 0.7
        self.cull = cull
        params = vmt_data.parameters

        # flags that imply nodraw
        if any(p in _NODRAW_PARAMS and vmt_data.param_as_bool(p) for p in params) or name in _NODRAW_MATERIALS:
            self.blend_method = 'CLIP'
            self.shadow_method = 'CLIP'
            self.nodraw = True
            return

        texture_inputs: DefaultDict[str, _TextureInputBase] = defaultdict(lambda: _TextureInput(interpolation))

        unsupported_params = [p for p in params if p not in _SUPPORTED_PARAMS]
        if len(unsupported_params) != 0:
            print(f"WARNING: UNSUPPORTED MATERIAL PARAMS: {', '.join(unsupported_params)} in {name}")

        if vmt_data.param_flag("%compilewater"):
            self.water = True
            self.blend_method = 'BLEND'
            self.shadow_method = 'HASHED'
            self._shader_dict: Dict[str, _MaterialNodePath] = {
                'Color': _MaterialNodePath(),
                'Normal': _MaterialNodePath()
            }
            if vmt_data.param_flag("$fogenable") and "$fogcolor" in params:
                self._shader_dict['Color'].const = vmt_data.param_as_color("$fogcolor") + (1,)
            if "$normalmap" in params:
                image = self._vtf_importer.load(
                    params["$normalmap"], vmt_data.param_open_texture("$normalmap"), 'Non-Color'
                )
                self.width, self.height = image.size
                if "$bumptransform" in params:
                    transform = vmt_data.param_as_transform("$bumptransform")
                    if transform.scale != (1, 1) or transform.rotate != 0 or transform.translate != (0, 0):
                        texture_inputs["$bumpmap"] = _TransformedTextureInput(
                            transform.scale, transform.rotate, transform.translate, interpolation
                        )
                texture_inputs["$normalmap"].setimage(image)
                self._shader_dict['Normal'].input = texture_inputs["$normalmap"].color
                if not self.simple:
                    self._shader_dict['Normal'].append(_DXNormalMapConverterMaterialNode())
                self._shader_dict['Normal'].append(_NormalMapMaterialNode())
            return

        self._shader_dict = {
            'Base Color': _MaterialNodePath(0),
            'Metallic': _MaterialNodePath(-150),
            'Specular': _MaterialNodePath(-160),
            'Specular Tint': _MaterialNodePath(-170),
            'Roughness': _MaterialNodePath(-180),
            'Emission': _MaterialNodePath(-400),
            'Alpha': _MaterialNodePath(-410),
            'Normal': _MaterialNodePath(-420),
        }

        vertex_col_input = _VertexColorInput()
        object_col_input = _ObjectColorInput()
        blend_input = vertex_col_input.alpha

        if vmt_data.param_flag("$nocull") or vmt_data.param_flag("$decal"):
            # don't cull overlays since imported normals are wrong
            self.cull = False

        if "$basetexture" in params:
            image = self._vtf_importer.load(params["$basetexture"], vmt_data.param_open_texture("$basetexture"))
            if "$basetexturetransform" in params:
                transform = vmt_data.param_as_transform("$basetexturetransform")
                if transform.scale != (1, 1) or transform.rotate != 0 or transform.translate != (0, 0):
                    texture_inputs["$basetexture"] = _TransformedTextureInput(
                        transform.scale, transform.rotate, transform.translate, interpolation
                    )
            texture_inputs["$basetexture"].setimage(image)
            self.width, self.height = image.size
            if not self.simple and "$blendmodulatetexture" in params:
                bimage = self._vtf_importer.load(
                    params["$blendmodulatetexture"], vmt_data.param_open_texture("$blendmodulatetexture"), 'Non-Color'
                )
                if "$blendmodulatetransform" in params:
                    transform = vmt_data.param_as_transform("$blendmodulatetransform")
                    if transform.scale != (1, 1) or transform.rotate != 0 or transform.translate != (0, 0):
                        texture_inputs["$blendmodulatetexture"] = _TransformedTextureInput(
                            transform.scale, transform.rotate, transform.translate, interpolation
                        )
                texture_inputs["$blendmodulatetexture"].setimage(bimage)
                blend_input = _ModulatedBlendFactorInput(
                    texture_inputs["$blendmodulatetexture"].channels, vertex_col_input.alpha
                ).fac
            if not self.simple and "$detail" in params and ("$detailblendmode" not in params  # TODO: other blend modes
                                                            or vmt_data.param_as_int("$detailblendmode") == 0):
                dimage = self._vtf_importer.load(params["$detail"], vmt_data.param_open_texture("$detail"), 'Non-Color')
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
                    texture_inputs["$detail"] = _TransformedTextureInput(scale, rotate, translate, interpolation)
                texture_inputs["$detail"].setimage(dimage)
                blend_fac = vmt_data.param_as_float("$detailblendfactor") if "$detailblendfactor" in params else 1
                texture_inputs["$basetexture"] = _DetailedTextureInput(
                    texture_inputs["$basetexture"], texture_inputs["$detail"], blend_fac
                )
            if not self.simple and "$basetexture2" in params:
                image2 = self._vtf_importer.load(params["$basetexture2"], vmt_data.param_open_texture("$basetexture2"))
                if "$basetexturetransform2" in params:
                    transform = vmt_data.param_as_transform("$basetexturetransform2")
                    if transform.scale != (1, 1) or transform.rotate != 0 or transform.translate != (0, 0):
                        texture_inputs["$basetexture2"] = _TransformedTextureInput(
                            transform.scale, transform.rotate, transform.translate, interpolation
                        )
                texture_inputs["$basetexture2"].setimage(image2)
                if "$detail2" in params:
                    dimage2 = self._vtf_importer.load(
                        params["$detail2"], vmt_data.param_open_texture("$detail2"), 'Non-Color'
                    )
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
                        texture_inputs["$detail2"] = _TransformedTextureInput(scale, rotate, translate, interpolation)
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
            if not self.simple and "$color" in params:
                self._shader_dict['Base Color'].append(_MultiplyRGBMaterialNode(vmt_data.param_as_color("$color")))
            if (not self.simple and vmt_data.shader == "vertexlitgeneric"
                    and not vmt_data.param_flag("$allowdiffusemodulation") and not vmt_data.param_flag("$notint")):
                if "$tintmasktexture" in params:
                    image = self._vtf_importer.load(
                        params["$tintmasktexture"],
                        vmt_data.param_open_texture("$tintmasktexture"),
                        'Non-Color'
                    )
                    texture_inputs["$tintmasktexture"].setimage(image)
                    factor: Union[float, _MaterialInputSocket] = texture_inputs["$tintmasktexture"].channels.g
                elif "$blendtintbybasealpha" in params:
                    factor = texture_inputs["$basetexture"].alpha
                else:
                    factor = 1.0
                if "$color2" in params:
                    color = vmt_data.param_as_color("$color2") + (1,)
                else:
                    color = object_col_input.color
                self._shader_dict['Base Color'].append(_MultiplyRGBMaterialNode(color, factor))
        elif "$color" in params:
            self._shader_dict['Base Color'].const = vmt_data.param_as_color("$color") + (1,)
        elif not self.simple and vmt_data.param_flag("$vertexcolor"):
            self._shader_dict['Base Color'].input = vertex_col_input.color

        if "$bumpmap" in params and (not self.simple or not vmt_data.param_flag("$ssbump")):
            image = self._vtf_importer.load(params["$bumpmap"], vmt_data.param_open_texture("$bumpmap"), 'Non-Color')
            if "$bumptransform" in params:
                transform = vmt_data.param_as_transform("$bumptransform")
                if transform.scale != (1, 1) or transform.rotate != 0 or transform.translate != (0, 0):
                    texture_inputs["$bumpmap"] = _TransformedTextureInput(
                        transform.scale, transform.rotate, transform.translate, interpolation
                    )
            texture_inputs["$bumpmap"].setimage(image)
            if not self.simple and "$bumpmap2" in params:
                image2 = self._vtf_importer.load(
                    params["$bumpmap2"], vmt_data.param_open_texture("$bumpmap2"), 'Non-Color'
                )
                if "$bumptransform2" in params:
                    transform = vmt_data.param_as_transform("$bumptransform2")
                    if transform.scale != (1, 1) or transform.rotate != 0 or transform.translate != (0, 0):
                        texture_inputs["$bumpmap2"] = _TransformedTextureInput(
                            transform.scale, transform.rotate, transform.translate, interpolation
                        )
                texture_inputs["$bumpmap2"].setimage(image2)
                if vmt_data.param_flag("$addbumpmaps"):
                    # FIXME: mixing textures is not a correct way of combining normal maps
                    if "$bumpdetailscale1" in params:
                        bumpamount1 = vmt_data.param_as_float("$bumpdetailscale1")
                    else:
                        bumpamount1 = 1
                    if "$bumpdetailscale2" in params:
                        bumpamount2 = vmt_data.param_as_float("$bumpdetailscale2")
                    else:
                        bumpamount2 = 1
                    blend_fac = bumpamount2 / (bumpamount1 + bumpamount2)
                    blended = _BlendedTextureInput(blend_fac, texture_inputs["$bumpmap"], texture_inputs["$bumpmap2"])
                else:
                    blended = _BlendedTextureInput(blend_input, texture_inputs["$bumpmap"], texture_inputs["$bumpmap2"])
                texture_inputs["$bumpmap"] = blended
            self._shader_dict['Normal'].input = texture_inputs["$bumpmap"].color
            if vmt_data.param_flag("$ssbump"):
                self._shader_dict['Normal'].append(_SsbumpToNormalMaterialNode())
            else:
                if not self.simple:
                    self._shader_dict['Normal'].append(_DXNormalMapConverterMaterialNode())
                self._shader_dict['Normal'].append(_NormalMapMaterialNode())
        elif not self.simple and ("$detail" in params and "$detailblendmode" in params
                                  and vmt_data.param_as_int("$detailblendmode") == 10):
            dimage = self._vtf_importer.load(params["$detail"], vmt_data.param_open_texture("$detail"), 'Non-Color')
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
                texture_inputs["$detail"] = _TransformedTextureInput(scale, rotate, translate, interpolation)
            texture_inputs["$detail"].setimage(dimage)
            self._shader_dict['Normal'].input = texture_inputs["$detail"].color
            self._shader_dict['Normal'].append(_SsbumpToNormalMaterialNode())

        if vmt_data.param_flag("$translucent"):
            self.blend_method = 'BLEND'
            self.shadow_method = 'HASHED'
            self._shader_dict['Alpha'].input = texture_inputs["$basetexture"].alpha
            if not self.simple and "$alpha" in params:
                self._shader_dict['Alpha'].append(_MultiplyMaterialNode(vmt_data.param_as_float("$alpha")))
        elif vmt_data.param_flag("$alphatest"):
            self.blend_method = 'CLIP'
            self.shadow_method = 'CLIP'
            self._shader_dict['Alpha'].input = texture_inputs["$basetexture"].alpha
            if "$alphatestreference" in params:
                self.alpha_reference = vmt_data.param_as_float("$alphatestreference")
            elif "$allowalphatocoverage" in params:
                self.blend_method = 'HASHED'
            if not self.simple and "$alpha" in params:
                self._shader_dict['Alpha'].append(_MultiplyMaterialNode(vmt_data.param_as_float("$alpha")))
        elif not self.simple and vmt_data.param_flag("$vertexalpha"):
            self.blend_method = 'BLEND'
            self.shadow_method = 'HASHED'
            self._shader_dict['Alpha'].input = vertex_col_input.alpha
            if not self.simple and "$alpha" in params:
                self._shader_dict['Alpha'].append(_MultiplyMaterialNode(vmt_data.param_as_float("$alpha")))
        elif "$alpha" in params:
            self._shader_dict['Alpha'].const = vmt_data.param_as_float("$alpha")
            self.blend_method = 'BLEND'
            self.shadow_method = 'HASHED'

        if "$masks1" in params:
            image = self._vtf_importer.load(params["$masks1"], vmt_data.param_open_texture("$masks1"), 'Non-Color')
            texture_inputs["$masks1"].setimage(image)
            masks1 = True
        else:
            masks1 = False

        if vmt_data.param_flag("$phong") or vmt_data.shader == "character":
            if vmt_data.param_flag("$basemapluminancephongmask"):
                self._shader_dict['Specular'].input = texture_inputs["$basetexture"].color
            elif not self.simple and vmt_data.param_flag("$basemapalphaphongmask"):
                self._shader_dict['Specular'].input = texture_inputs["$basetexture"].alpha
            elif not self.simple and masks1:
                self._shader_dict['Specular'].input = texture_inputs["$masks1"].channels.g
            elif not self.simple:
                self._shader_dict['Specular'].input = texture_inputs["$bumpmap"].alpha
            if "$phongexponent" in params:
                if not self.simple and "$phongexponent2" in params:
                    self._shader_dict['Roughness'].input = _BlendedConstantInput(
                        blend_input,
                        ((150 - vmt_data.param_as_float("$phongexponent")) / 150) * 0.66,
                        ((150 - vmt_data.param_as_float("$phongexponent2")) / 150) * 0.66,
                    ).const
                else:
                    self._shader_dict['Roughness'].const = (
                        (150 - vmt_data.param_as_float("$phongexponent")) / 150
                    ) * 0.66
            elif not self.simple and "$phongexponenttexture" in params:
                image = self._vtf_importer.load(
                    params["$phongexponenttexture"],
                    vmt_data.param_open_texture("$phongexponenttexture"),
                    'Non-Color'
                )
                texture_inputs["$phongexponenttexture"].setimage(image)
                self._shader_dict['Roughness'].input = texture_inputs["$phongexponenttexture"].channels.r
                self._shader_dict['Roughness'].append(_InvertMaterialNode())
                self._shader_dict['Roughness'].append(_MultiplyMaterialNode(0.66))
                if vmt_data.param_flag("$phongalbedotint"):
                    self._shader_dict['Specular Tint'].input = texture_inputs["$phongexponenttexture"].channels.g
            else:
                self._shader_dict['Roughness'].const = 0.6
        elif "$envmap" in params:
            if not self.simple and (vmt_data.param_flag("$basealphaenvmapmask")
                                    or vmt_data.param_flag("$basealphaenvmask")):
                self._shader_dict['Specular'].input = texture_inputs["$basetexture"].alpha
                self._shader_dict['Specular'].append(_InvertMaterialNode())
            elif not self.simple and vmt_data.param_flag("$normalmapalphaenvmapmask"):
                self._shader_dict['Specular'].input = texture_inputs["$bumpmap"].alpha
            elif not self.simple and vmt_data.param_flag("$envmapmaskintintmasktexture"):
                self._shader_dict['Specular'].input = texture_inputs["$tintmasktexture"].channels.r
            elif "$envmapmask" in params:
                image = self._vtf_importer.load(
                    params["$envmapmask"], vmt_data.param_open_texture("$envmapmask"), 'Non-Color'
                )
                if "$envmapmasktransform" in params:
                    transform = vmt_data.param_as_transform("$envmapmasktransform")
                    if transform.scale != (1, 1) or transform.rotate != 0 or transform.translate != (0, 0):
                        texture_inputs["$envmapmask"] = _TransformedTextureInput(
                            transform.scale, transform.rotate, transform.translate, interpolation
                        )
                texture_inputs["$envmapmask"].setimage(image)
                self._shader_dict['Specular'].input = texture_inputs["$envmapmask"].color
                if not self.simple and "$envmaptint" in params:
                    tint = vmt_data.param_as_color("$envmaptint")
                    self._shader_dict['Specular'].append(_MultiplyMaterialNode(sum(tint) / 3))
            elif "$envmaptint" in params:
                tint = vmt_data.param_as_color("$envmaptint")
                self._shader_dict['Specular'].const = sum(tint) / 3
            else:
                self._shader_dict['Specular'].const = 0.8
            self._shader_dict['Roughness'].const = 0.1
        elif vmt_data.shader == "unlitgeneric" or vmt_data.param_flag("%compilenolight"):
            self._shader_dict['Specular'].const = 0.0
            self._shader_dict['Roughness'].const = 1.0
        else:
            self._shader_dict['Specular'].const = 0.1
            self._shader_dict['Roughness'].const = 0.9

        if not self.simple and masks1:
            self._shader_dict['Metallic'].input = texture_inputs["$masks1"].channels.b
            self._shader_dict['Metallic'].append(_InvertMaterialNode())
        elif "$metalness" in params:
            self._shader_dict['Metallic'].const = vmt_data.param_as_float("$metalness")

        selfillum_input = None
        if not self.simple and vmt_data.param_flag("$selfillum_envmapmask_alpha"):
            selfillum_input = texture_inputs["$envmapmask"].alpha
        elif vmt_data.param_flag("$selfillum"):
            if "$selfillummask" in params:
                image = self._vtf_importer.load(
                    params["$selfillummask"], vmt_data.param_open_texture("$selfillummask"), 'Non-Color'
                )
                texture_inputs["$selfillummask"].setimage(image)
                selfillum_input = texture_inputs["$selfillummask"].color
            elif not self.simple:
                selfillum_input = texture_inputs["$basetexture"].alpha
        if selfillum_input is not None:
            if not self.simple:
                self._shader_dict['Emission'].input = texture_inputs["$basetexture"].color
                self._shader_dict['Emission'].append(_MultiplyRGBMaterialNode(selfillum_input, 1))
            else:
                self._shader_dict['Emission'].input = selfillum_input

    def build(self) -> bpy.types.Material:
        material: bpy.types.Material = bpy.data.materials.new(self.name)
        material.use_nodes = True
        material.blend_method = self.blend_method
        material.shadow_method = self.shadow_method
        material.alpha_threshold = self.alpha_reference
        material.use_backface_culling = self.cull
        nt = material.node_tree
        nt.nodes.clear()
        pos_ref = _PosRef()
        out_node: Node = nt.nodes.new('ShaderNodeOutputMaterial')
        out_node.location = pos_ref.loc()
        pos_ref.x -= 300
        if self.nodraw:
            shader_node: Node = nt.nodes.new('ShaderNodeBsdfTransparent')
        elif self.water:
            material.use_screen_refraction = True
            shader_node = nt.nodes.new('ShaderNodeBsdfGlass')
            shader_node.inputs['IOR'].default_value = 1.333
            shader_node.inputs['Roughness'].default_value = 0.3
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
    def __init__(self, verbose: bool = False, simple: bool = False,
                 interpolation: str = 'Linear', cull: bool = False,
                 reuse_old: bool = True, reuse_old_images: bool = True) -> None:
        self.verbose = verbose
        self.simple = simple
        self.interpolation = interpolation
        self.cull = cull
        self.reuse_old = reuse_old
        self._nodraw_cache: Dict[str, bool] = {}
        self._precache: Dict[str, _MaterialBuilder] = {}
        self._cache: Dict[str, VMTData] = {}
        self._vtf_importer = import_vtf.VTFImporter(reuse_old=reuse_old_images)

    def _fallback_material(self, material_name: str) -> VMTData:
        material: bpy.types.Material = bpy.data.materials.new(material_name)
        return VMTData(1, 1, material)

    def is_nodraw(self, material_name: str, vmt_data: Callable[[], vmt.VMT]) -> bool:
        material_name = material_name.lower()
        truncated_name = truncate_name(material_name)
        if material_name in self._nodraw_cache:
            return self._nodraw_cache[material_name]
        try:
            builder = _MaterialBuilder(self._vtf_importer, truncated_name, vmt_data(),
                                       simple=self.simple, interpolation=self.interpolation, cull=self.cull)
        except FileNotFoundError:
            print(f"WARNING: MATERIAL {material_name} NOT FOUND")
            self._cache[material_name] = self._fallback_material(truncated_name)
            is_nodraw = is_invisible_tool((material_name,))
        except vmt.VMTParseException as err:
            print(f"WARNING: MATERIAL {material_name} IS INVALID")
            if self.verbose:
                traceback.print_exception(type(err), err, err.__traceback__)
            self._cache[material_name] = self._fallback_material(truncated_name)
            is_nodraw = is_invisible_tool((material_name,))
        else:
            self._precache[material_name] = builder
            is_nodraw = builder.nodraw
        self._nodraw_cache[material_name] = is_nodraw
        return is_nodraw

    def load(self, material_name: str, vmt_data: Callable[[], vmt.VMT]) -> VMTData:
        material_name = material_name.lower()
        truncated_name = truncate_name(material_name)
        if material_name in self._cache:
            return self._cache[material_name]
        if self.reuse_old and truncated_name in bpy.data.materials:
            material: bpy.types.Material = bpy.data.materials[truncated_name]
            if material.use_nodes and len(material.node_tree.nodes) != 0:
                return VMTData(material.vmt_data.width, material.vmt_data.height, material)
        if self.verbose:
            print(f"Building material {material_name}...")
        try:
            if material_name in self._precache:
                builder = self._precache[material_name]
            else:
                builder = _MaterialBuilder(self._vtf_importer, truncated_name, vmt_data(),
                                           simple=self.simple, interpolation=self.interpolation, cull=self.cull)
        except FileNotFoundError:
            print(f"WARNING: MATERIAL {material_name} NOT FOUND")
            data = self._fallback_material(material_name)
        except vmt.VMTParseException as err:
            print(f"WARNING: MATERIAL {material_name} IS INVALID")
            if self.verbose:
                traceback.print_exception(type(err), err, err.__traceback__)
            data = self._fallback_material(material_name)
        else:
            try:
                material = builder.build()
            except Exception as err:
                print(f"WARNING: MATERIAL {material_name} BUILDING FAILED: {err}")
                if self.verbose:
                    traceback.print_exception(type(err), err, err.__traceback__)
                data = self._fallback_material(material_name)
            else:
                material.vmt_data.width = builder.width
                material.vmt_data.height = builder.height
                data = VMTData(builder.width, builder.height, material)
        self._cache[material_name] = data
        return data


_CUBEMAP_SUFFIXES = (
    "lf", "rt", "up", "dn", "ft", "bk",
)


def load_sky(fs: VMFFileSystem, skyname: str, output_res: int = 1024, context: bpy.types.Context = bpy.context) -> None:
    hdr = False
    textures = []
    for suffix in _CUBEMAP_SUFFIXES:
        sky_vmt = vmt.VMT(fs.open_file_utf8(f"{skyname}{suffix}.vmt"), fs)
        params = sky_vmt.parameters
        if "$hdrbasetexture" in params:
            textures.append(sky_vmt.param_open_texture("$hdrbasetexture"))
            hdr = True
        elif "$hdrcompressedtexture" in params:
            textures.append(sky_vmt.param_open_texture("$hdrcompressedtexture"))
            hdr = True
        elif "$basetexture" in params:
            textures.append(sky_vmt.param_open_texture("$basetexture"))
    image = import_vtf.load_as_equi(skyname, textures, output_res, hdr=hdr)

    context.scene.world.use_nodes = True
    nt = context.scene.world.node_tree
    nt.nodes.clear()
    out_node: Node = nt.nodes.new('ShaderNodeOutputWorld')
    out_node.location = (0, 0)
    bg_node: Node = nt.nodes.new('ShaderNodeBackground')
    bg_node.location = (-300, 0)
    nt.links.new(bg_node.outputs['Background'], out_node.inputs['Surface'])
    tex_node: Node = nt.nodes.new('ShaderNodeTexEnvironment')
    tex_node.image = image
    tex_node.location = (-600, 0)
    nt.links.new(tex_node.outputs['Color'], bg_node.inputs['Color'])
