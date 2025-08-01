pub const NODE_MARGIN: f32 = 50.0;

pub mod shaders {
    use super::super::nodes::{
        NodeSocketId::{Name, Position},
        NodeType,
    };

    pub static PRINCIPLED: NodeType = NodeType {
        blender_id: "ShaderNodeBsdfPrincipled",
        size: [240.0, 658.0],
        input_sockets: &[
            Name("Base Color"),
            Name("Metallic"),
            Name("Specular"),
            Name("Specular Tint"),
            Name("Roughness"),
            Name("Emission"),
            Name("Alpha"),
            Name("Normal"),
        ],
        output_sockets: &[Position(0)],
        ..NodeType::default()
    };

    pub static TRANSPARENT: NodeType = NodeType {
        blender_id: "ShaderNodeBsdfTransparent",
        size: [140.0, 75.0],
        output_sockets: &[Position(0)],
        ..NodeType::default()
    };

    pub static GLASS: NodeType = NodeType {
        blender_id: "ShaderNodeBsdfGlass",
        size: [150.0, 171.0],
        input_sockets: &[
            Name("Color"),
            Name("Roughness"),
            Name("IOR"),
            Name("Normal"),
        ],
        output_sockets: &[Position(0)],
        ..NodeType::default()
    };
}

pub mod nodes {
    use super::super::nodes::{
        NodeSocketId::{Name, Position},
        NodeType,
    };

    pub static TEX_IMAGE: NodeType = NodeType {
        blender_id: "ShaderNodeTexImage",
        size: [240.0, 252.0],
        input_sockets: &[Name("Vector")],
        output_sockets: &[Name("Color"), Name("Alpha")],
        properties: &["image", "interpolation"],
    };

    pub static TEX_COORD: NodeType = NodeType {
        blender_id: "ShaderNodeTexCoord",
        size: [140.0, 237.0],
        output_sockets: &[Name("UV")],
        ..NodeType::default()
    };

    pub static MAPPING: NodeType = NodeType {
        blender_id: "ShaderNodeMapping",
        size: [140.0, 411.0],
        input_sockets: &[
            Name("Vector"),
            Name("Scale"),
            Name("Rotation"),
            Name("Location"),
        ],
        output_sockets: &[Name("Vector")],
        ..NodeType::default()
    };

    pub static NORMAL_MAP: NodeType = NodeType {
        blender_id: "ShaderNodeNormalMap",
        size: [150.0, 152.0],
        input_sockets: &[Name("Color"), Name("Strength")],
        output_sockets: &[Name("Normal")],
        ..NodeType::default()
    };

    pub static SEPARATE_RGB: NodeType = NodeType {
        blender_id: "ShaderNodeSeparateRGB",
        size: [140.0, 119.0],
        input_sockets: &[Name("Image")],
        output_sockets: &[Name("R"), Name("G"), Name("B")],
        ..NodeType::default()
    };

    pub static COMBINE_RGB: NodeType = NodeType {
        blender_id: "ShaderNodeCombineRGB",
        size: [140.0, 119.0],
        input_sockets: &[Name("R"), Name("G"), Name("B")],
        output_sockets: &[Name("Image")],
        ..NodeType::default()
    };

    pub static MATH: NodeType = NodeType {
        blender_id: "ShaderNodeMath",
        size: [140.0, 174.0],
        input_sockets: &[Position(0), Position(1), Position(2)],
        output_sockets: &[Position(0)],
        properties: &["operation", "use_clamp"],
    };

    pub static MIX_RGB: NodeType = NodeType {
        blender_id: "ShaderNodeMixRGB",
        size: [140.0, 171.0],
        input_sockets: &[Name("Fac"), Name("Color1"), Name("Color2")],
        output_sockets: &[Name("Color")],
        properties: &["blend_type"],
    };

    pub static VERTEX_COLOR: NodeType = NodeType {
        blender_id: "ShaderNodeVertexColor",
        size: [140.0, 102.0],
        output_sockets: &[Name("Color"), Name("Alpha")],
        properties: &["layer_name"],
        ..NodeType::default()
    };

    pub static OBJECT_INFO: NodeType = NodeType {
        blender_id: "ShaderNodeObjectInfo",
        size: [140.0, 138.0],
        output_sockets: &[Name("Color")],
        ..NodeType::default()
    };

    pub static MAP_RANGE: NodeType = NodeType {
        blender_id: "ShaderNodeMapRange",
        size: [140.0, 247.0],
        input_sockets: &[
            Name("Value"),
            Name("From Min"),
            Name("From Max"),
            Name("To Min"),
            Name("To Max"),
        ],
        output_sockets: &[Position(0)],
        properties: &["interpolation_type", "clamp"],
    };

    pub static VECTOR_MATH: NodeType = NodeType {
        blender_id: "ShaderNodeVectorMath",
        size: [140.0, 191.0],
        input_sockets: &[Position(0), Position(1), Position(2)],
        output_sockets: &[Position(0)],
        properties: &["operation"],
    };

    pub static SEPARATE_XYZ: NodeType = NodeType {
        blender_id: "ShaderNodeSeparateXYZ",
        size: [140.0, 179.0],
        input_sockets: &[Name("Vector")],
        output_sockets: &[Name("X"), Name("Y"), Name("Z")],
        ..NodeType::default()
    };
}

pub mod groups {
    use super::super::nodes::{
        Node, NodeGroup,
        NodeSocketId::{Name, Position},
        NodeSocketRef, Ref, Value,
    };
    use super::nodes;

    pub static TEXTURE: NodeGroup = NodeGroup {
        nodes: &[Node {
            kind: &nodes::TEX_IMAGE,
            id: "texture",
            ..Node::default()
        }],
        properties: &[
            ("image", Ref::new("texture", "image")),
            ("interpolation", Ref::new("texture", "interpolation")),
        ],
        outputs: &[
            ("color", NodeSocketRef::new("texture", Name("Color"))),
            ("alpha", NodeSocketRef::new("texture", Name("Alpha"))),
        ],
        ..NodeGroup::default()
    };

    pub static TRANSFORMED_TEXTURE: NodeGroup = NodeGroup {
        nodes: &[
            Node {
                kind: &nodes::TEX_COORD,
                id: "coord",
                ..Node::default()
            },
            Node {
                kind: &nodes::MAPPING,
                id: "mapping",
                links: &[(Name("Vector"), NodeSocketRef::new("coord", Name("UV")))],
                ..Node::default()
            },
            Node {
                kind: &nodes::TEX_IMAGE,
                id: "texture",
                links: &[(
                    Name("Vector"),
                    NodeSocketRef::new("mapping", Name("Vector")),
                )],
                ..Node::default()
            },
        ],
        properties: &[
            ("image", Ref::new("texture", "image")),
            ("interpolation", Ref::new("texture", "interpolation")),
        ],
        inputs: &[
            ("scale", NodeSocketRef::new("mapping", Name("Scale"))),
            ("rotation", NodeSocketRef::new("mapping", Name("Rotation"))),
            ("location", NodeSocketRef::new("mapping", Name("Location"))),
        ],
        outputs: &[
            ("color", NodeSocketRef::new("texture", Name("Color"))),
            ("alpha", NodeSocketRef::new("texture", Name("Alpha"))),
        ],
    };

    pub static SPLIT_TEXTURE: NodeGroup = NodeGroup {
        nodes: &[
            Node {
                kind: &nodes::TEX_IMAGE,
                id: "texture",
                ..Node::default()
            },
            Node {
                kind: &nodes::SEPARATE_RGB,
                id: "separate",
                links: &[(Name("Image"), NodeSocketRef::new("texture", Name("Color")))],
                ..Node::default()
            },
        ],
        properties: &[
            ("image", Ref::new("texture", "image")),
            ("interpolation", Ref::new("texture", "interpolation")),
        ],
        outputs: &[
            ("r", NodeSocketRef::new("separate", Name("R"))),
            ("g", NodeSocketRef::new("separate", Name("G"))),
            ("b", NodeSocketRef::new("separate", Name("B"))),
            ("alpha", NodeSocketRef::new("texture", Name("Alpha"))),
        ],
        ..NodeGroup::default()
    };

    pub static DX_NORMAL_MAP_CONVERTER: NodeGroup = NodeGroup {
        nodes: &[
            Node {
                kind: &nodes::SEPARATE_RGB,
                id: "separate",
                ..Node::default()
            },
            Node {
                kind: &nodes::MATH,
                id: "invert",
                properties: &[("operation", Value::Enum("SUBTRACT"))],
                values: &[(Position(0), Value::Float(1.0))],
                links: &[(Position(1), NodeSocketRef::new("separate", Name("G")))],
            },
            Node {
                kind: &nodes::COMBINE_RGB,
                id: "combine",
                links: &[
                    (Name("R"), NodeSocketRef::new("separate", Name("R"))),
                    (Name("G"), NodeSocketRef::new("invert", Position(0))),
                    (Name("B"), NodeSocketRef::new("separate", Name("B"))),
                ],
                ..Node::default()
            },
        ],
        inputs: &[("image", NodeSocketRef::new("separate", Name("Image")))],
        outputs: &[("image", NodeSocketRef::new("combine", Name("Image")))],
        ..NodeGroup::default()
    };

    pub static SSBUMP_CONVERTER: NodeGroup = NodeGroup {
        nodes: &[
            Node {
                kind: &nodes::SEPARATE_XYZ,
                id: "sep",
                ..Node::default()
            },
            Node {
                kind: &nodes::VECTOR_MATH,
                id: "x_mul",
                properties: &[("operation", Value::Enum("MULTIPLY"))],
                values: &[(Position(1), Value::Vec([0.816_496_6, 0.0, 0.577_350_26]))],
                links: &[(Position(0), NodeSocketRef::new("sep", Name("X")))],
            },
            Node {
                kind: &nodes::VECTOR_MATH,
                id: "y_mul",
                properties: &[("operation", Value::Enum("MULTIPLY"))],
                values: &[(
                    Position(1),
                    Value::Vec([-0.408_248_34, 0.707_106_77, 0.577_350_26]),
                )],
                links: &[(Position(0), NodeSocketRef::new("sep", Name("Y")))],
            },
            Node {
                kind: &nodes::VECTOR_MATH,
                id: "z_mul",
                properties: &[("operation", Value::Enum("MULTIPLY"))],
                values: &[(
                    Position(1),
                    Value::Vec([-0.408_248_22, -0.707_106_77, 0.577_350_26]),
                )],
                links: &[(Position(0), NodeSocketRef::new("sep", Name("Z")))],
            },
            Node {
                kind: &nodes::VECTOR_MATH,
                id: "add_1",
                properties: &[("operation", Value::Enum("ADD"))],
                links: &[
                    (Position(0), NodeSocketRef::new("x_mul", Position(0))),
                    (Position(1), NodeSocketRef::new("y_mul", Position(0))),
                ],
                ..Node::default()
            },
            Node {
                kind: &nodes::VECTOR_MATH,
                id: "add_2",
                properties: &[("operation", Value::Enum("ADD"))],
                links: &[
                    (Position(0), NodeSocketRef::new("add_1", Position(0))),
                    (Position(1), NodeSocketRef::new("z_mul", Position(0))),
                ],
                ..Node::default()
            },
            Node {
                kind: &nodes::VECTOR_MATH,
                id: "normalize",
                properties: &[("operation", Value::Enum("NORMALIZE"))],
                links: &[(Position(0), NodeSocketRef::new("add_2", Position(0)))],
                ..Node::default()
            },
            Node {
                kind: &nodes::VECTOR_MATH,
                id: "mul",
                properties: &[("operation", Value::Enum("MULTIPLY"))],
                values: &[(Position(1), Value::Vec([0.5, 0.5, 0.5]))],
                links: &[(Position(0), NodeSocketRef::new("normalize", Position(0)))],
            },
            Node {
                kind: &nodes::VECTOR_MATH,
                id: "add",
                properties: &[("operation", Value::Enum("ADD"))],
                values: &[(Position(1), Value::Vec([0.5, 0.5, 0.5]))],
                links: &[(Position(0), NodeSocketRef::new("mul", Position(0)))],
            },
        ],
        inputs: &[("image", NodeSocketRef::new("sep", Name("Vector")))],
        outputs: &[("image", NodeSocketRef::new("add", Position(0)))],
        ..NodeGroup::default()
    };

    pub static NORMAL_MAP: NodeGroup = NodeGroup {
        nodes: &[Node {
            kind: &nodes::NORMAL_MAP,
            id: "normal_map",
            ..Node::default()
        }],
        inputs: &[
            ("image", NodeSocketRef::new("normal_map", Name("Color"))),
            (
                "strength",
                NodeSocketRef::new("normal_map", Name("Strength")),
            ),
        ],
        outputs: &[("normal", NodeSocketRef::new("normal_map", Name("Normal")))],
        ..NodeGroup::default()
    };

    pub static DETAIL_TEXTURE: NodeGroup = NodeGroup {
        nodes: &[
            Node {
                kind: &nodes::MIX_RGB,
                id: "mul",
                properties: &[("blend_type", Value::Enum("MULTIPLY"))],
                values: &[
                    (Name("Color2"), Value::Color([2.0, 2.0, 2.0, 1.0])),
                    (Name("Fac"), Value::Float(1.0)),
                ],
                ..Node::default()
            },
            Node {
                kind: &nodes::MIX_RGB,
                id: "mix",
                properties: &[("blend_type", Value::Enum("MULTIPLY"))],
                links: &[(Name("Color2"), NodeSocketRef::new("mul", Name("Color")))],
                ..Node::default()
            },
        ],
        inputs: &[
            ("color", NodeSocketRef::new("mix", Name("Color1"))),
            ("detail", NodeSocketRef::new("mul", Name("Color1"))),
            ("fac", NodeSocketRef::new("mix", Name("Fac"))),
        ],
        outputs: &[("color", NodeSocketRef::new("mix", Name("Color")))],
        ..NodeGroup::default()
    };

    pub static COLOR_TEXTURE: NodeGroup = NodeGroup {
        nodes: &[Node {
            kind: &nodes::MIX_RGB,
            id: "mul",
            properties: &[("blend_type", Value::Enum("MULTIPLY"))],
            values: &[(Name("Fac"), Value::Float(1.0))],
            ..Node::default()
        }],
        inputs: &[
            ("color", NodeSocketRef::new("mul", Name("Color1"))),
            ("mixin", NodeSocketRef::new("mul", Name("Color2"))),
            ("fac", NodeSocketRef::new("mul", Name("Fac"))),
        ],
        outputs: &[("color", NodeSocketRef::new("mul", Name("Color")))],
        ..NodeGroup::default()
    };

    pub static BLEND_TEXTURE: NodeGroup = NodeGroup {
        nodes: &[
            Node {
                kind: &nodes::MIX_RGB,
                id: "mix_color",
                properties: &[("blend_type", Value::Enum("MIX"))],
                ..Node::default()
            },
            Node {
                kind: &nodes::MAP_RANGE,
                id: "mix_alpha",
                properties: &[("clamp", Value::Bool(false))],
                values: &[
                    (Name("From Min"), Value::Float(0.0)),
                    (Name("From Max"), Value::Float(1.0)),
                ],
                ..Node::default()
            },
        ],
        inputs: &[
            ("color", NodeSocketRef::new("mix_color", Name("Color1"))),
            ("color2", NodeSocketRef::new("mix_color", Name("Color2"))),
            ("alpha", NodeSocketRef::new("mix_alpha", Name("To Min"))),
            ("alpha2", NodeSocketRef::new("mix_alpha", Name("To Max"))),
            ("fac", NodeSocketRef::new("mix_color", Name("Fac"))),
            ("fac", NodeSocketRef::new("mix_alpha", Name("Value"))),
        ],
        outputs: &[
            ("color", NodeSocketRef::new("mix_color", Name("Color"))),
            ("alpha", NodeSocketRef::new("mix_alpha", Position(0))),
        ],
        ..NodeGroup::default()
    };

    pub static VERTEX_COLOR: NodeGroup = NodeGroup {
        nodes: &[Node {
            kind: &nodes::VERTEX_COLOR,
            id: "col",
            properties: &[("layer_name", Value::Enum("Col"))],
            ..Node::default()
        }],
        outputs: &[
            ("color", NodeSocketRef::new("col", Name("Color"))),
            ("alpha", NodeSocketRef::new("col", Name("Alpha"))),
        ],
        ..NodeGroup::default()
    };

    pub static SEPARATED_VERTEX_COLOR: NodeGroup = NodeGroup {
        nodes: &[
            Node {
                kind: &nodes::VERTEX_COLOR,
                id: "col",
                properties: &[("layer_name", Value::Enum("Col"))],
                ..Node::default()
            },
            Node {
                kind: &nodes::SEPARATE_RGB,
                id: "separate",
                links: &[(Name("Image"), NodeSocketRef::new("col", Name("Color")))],
                ..Node::default()
            },
        ],
        outputs: &[
            ("r", NodeSocketRef::new("separate", Name("R"))),
            ("g", NodeSocketRef::new("separate", Name("G"))),
            ("b", NodeSocketRef::new("separate", Name("B"))),
            ("alpha", NodeSocketRef::new("col", Name("Alpha"))),
        ],
        ..NodeGroup::default()
    };

    pub static OBJECT_COLOR: NodeGroup = NodeGroup {
        nodes: &[Node {
            kind: &nodes::OBJECT_INFO,
            id: "col",
            ..Node::default()
        }],
        outputs: &[("color", NodeSocketRef::new("col", Name("Color")))],
        ..NodeGroup::default()
    };

    pub static MODULATED_FACTOR: NodeGroup = NodeGroup {
        nodes: &[
            Node {
                kind: &nodes::SEPARATE_RGB,
                id: "sep",
                ..Node::default()
            },
            Node {
                kind: &nodes::MATH,
                id: "sub",
                properties: &[
                    ("use_clamp", Value::Bool(true)),
                    ("operation", Value::Enum("SUBTRACT")),
                ],
                links: &[
                    (Position(0), NodeSocketRef::new("sep", Name("G"))),
                    (Position(1), NodeSocketRef::new("sep", Name("R"))),
                ],
                ..Node::default()
            },
            Node {
                kind: &nodes::MATH,
                id: "add",
                properties: &[
                    ("use_clamp", Value::Bool(true)),
                    ("operation", Value::Enum("ADD")),
                ],
                links: &[
                    (Position(0), NodeSocketRef::new("sep", Name("G"))),
                    (Position(1), NodeSocketRef::new("sep", Name("R"))),
                ],
                ..Node::default()
            },
            Node {
                kind: &nodes::MAP_RANGE,
                id: "map",
                properties: &[
                    ("interpolation_type", Value::Enum("SMOOTHSTEP")),
                    ("clamp", Value::Bool(false)),
                ],
                values: &[
                    (Name("To Min"), Value::Float(0.0)),
                    (Name("To Max"), Value::Float(1.0)),
                ],
                links: &[
                    (Name("From Min"), NodeSocketRef::new("sub", Position(0))),
                    (Name("From Max"), NodeSocketRef::new("add", Position(0))),
                ],
            },
        ],
        inputs: &[
            ("modulate", NodeSocketRef::new("sep", Name("Image"))),
            ("fac", NodeSocketRef::new("map", Name("Value"))),
        ],
        outputs: &[("fac", NodeSocketRef::new("map", Position(0)))],
        ..NodeGroup::default()
    };

    pub static MULTIPLY_VALUE: NodeGroup = NodeGroup {
        nodes: &[Node {
            kind: &nodes::MATH,
            id: "mul",
            properties: &[("operation", Value::Enum("MULTIPLY"))],
            ..Node::default()
        }],
        inputs: &[
            ("value", NodeSocketRef::new("mul", Position(0))),
            ("fac", NodeSocketRef::new("mul", Position(1))),
        ],
        outputs: &[("value", NodeSocketRef::new("mul", Position(0)))],
        ..NodeGroup::default()
    };

    pub static BLEND_VALUES: NodeGroup = NodeGroup {
        nodes: &[Node {
            kind: &nodes::MAP_RANGE,
            id: "map",
            values: &[
                (Name("From Min"), Value::Float(0.0)),
                (Name("From Max"), Value::Float(1.0)),
            ],
            ..Node::default()
        }],
        inputs: &[
            ("fac", NodeSocketRef::new("map", Name("Value"))),
            ("min", NodeSocketRef::new("map", Name("To Min"))),
            ("max", NodeSocketRef::new("map", Name("To Max"))),
        ],
        outputs: &[("fac", NodeSocketRef::new("map", Position(0)))],
        ..NodeGroup::default()
    };

    pub static INVERT_VALUE: NodeGroup = NodeGroup {
        nodes: &[Node {
            kind: &nodes::MATH,
            id: "sub",
            properties: &[("operation", Value::Enum("SUBTRACT"))],
            values: &[(Position(0), Value::Float(1.0))],
            ..Node::default()
        }],
        inputs: &[("value", NodeSocketRef::new("sub", Position(1)))],
        outputs: &[("value", NodeSocketRef::new("sub", Position(0)))],
        ..NodeGroup::default()
    };

    pub static FWB_FACTORS: NodeGroup = NodeGroup {
        nodes: &[
            Node {
                kind: &nodes::MAP_RANGE,
                id: "lum1ss",
                properties: &[
                    ("interpolation_type", Value::Enum("SMOOTHSTEP")),
                    ("clamp", Value::Bool(false)),
                ],
                values: &[
                    (Name("To Min"), Value::Float(0.0)),
                    (Name("To Max"), Value::Float(1.0)),
                ],
                ..Node::default()
            },
            Node {
                kind: &nodes::MAP_RANGE,
                id: "lum2ss",
                properties: &[
                    ("interpolation_type", Value::Enum("SMOOTHSTEP")),
                    ("clamp", Value::Bool(false)),
                ],
                values: &[
                    (Name("To Min"), Value::Float(0.0)),
                    (Name("To Max"), Value::Float(1.0)),
                ],
                ..Node::default()
            },
            Node {
                kind: &nodes::MAP_RANGE,
                id: "lum3ss",
                properties: &[
                    ("interpolation_type", Value::Enum("SMOOTHSTEP")),
                    ("clamp", Value::Bool(false)),
                ],
                values: &[
                    (Name("To Min"), Value::Float(0.0)),
                    (Name("To Max"), Value::Float(1.0)),
                ],
                ..Node::default()
            },
            Node {
                kind: &nodes::MAP_RANGE,
                id: "lum4ss",
                properties: &[
                    ("interpolation_type", Value::Enum("SMOOTHSTEP")),
                    ("clamp", Value::Bool(false)),
                ],
                values: &[
                    (Name("To Min"), Value::Float(0.0)),
                    (Name("To Max"), Value::Float(1.0)),
                ],
                ..Node::default()
            },
            Node {
                kind: &nodes::MATH,
                id: "lum1inv",
                properties: &[("operation", Value::Enum("SUBTRACT"))],
                values: &[(Position(0), Value::Float(1.0))],
                links: &[(Position(1), NodeSocketRef::new("lum1ss", Position(0)))],
            },
            Node {
                kind: &nodes::MAP_RANGE,
                id: "lum2blend",
                values: &[
                    (Name("From Min"), Value::Float(0.0)),
                    (Name("From Max"), Value::Float(1.0)),
                ],
                links: &[
                    (Name("To Min"), NodeSocketRef::new("lum1inv", Position(0))),
                    (Name("To Max"), NodeSocketRef::new("lum2ss", Position(0))),
                ],
                ..Node::default()
            },
            Node {
                kind: &nodes::MATH,
                id: "fac1m",
                properties: &[("operation", Value::Enum("MULTIPLY_ADD"))],
                links: &[(Position(1), NodeSocketRef::new("lum2blend", Position(0)))],
                ..Node::default()
            },
            Node {
                kind: &nodes::MAP_RANGE,
                id: "fac1ss",
                properties: &[
                    ("interpolation_type", Value::Enum("SMOOTHSTEP")),
                    ("clamp", Value::Bool(false)),
                ],
                values: &[
                    (Name("To Min"), Value::Float(0.0)),
                    (Name("To Max"), Value::Float(1.0)),
                ],
                links: &[(Name("Value"), NodeSocketRef::new("fac1m", Position(0)))],
            },
            Node {
                kind: &nodes::MAP_RANGE,
                id: "lums2",
                values: &[
                    (Name("From Min"), Value::Float(0.0)),
                    (Name("From Max"), Value::Float(1.0)),
                ],
                links: &[
                    (Name("To Min"), NodeSocketRef::new("lum1ss", Position(0))),
                    (Name("To Max"), NodeSocketRef::new("lum2ss", Position(0))),
                ],
                ..Node::default()
            },
            Node {
                kind: &nodes::MATH,
                id: "lums2inv",
                properties: &[("operation", Value::Enum("SUBTRACT"))],
                values: &[(Position(0), Value::Float(1.0))],
                links: &[(Position(1), NodeSocketRef::new("lums2", Position(0)))],
            },
            Node {
                kind: &nodes::MAP_RANGE,
                id: "lum3blend",
                values: &[
                    (Name("From Min"), Value::Float(0.0)),
                    (Name("From Max"), Value::Float(1.0)),
                ],
                links: &[
                    (Name("To Min"), NodeSocketRef::new("lums2inv", Position(0))),
                    (Name("To Max"), NodeSocketRef::new("lum3ss", Position(0))),
                ],
                ..Node::default()
            },
            Node {
                kind: &nodes::MATH,
                id: "fac2m",
                properties: &[("operation", Value::Enum("MULTIPLY_ADD"))],
                links: &[(Position(1), NodeSocketRef::new("lum3blend", Position(0)))],
                ..Node::default()
            },
            Node {
                kind: &nodes::MAP_RANGE,
                id: "fac2ss",
                properties: &[
                    ("interpolation_type", Value::Enum("SMOOTHSTEP")),
                    ("clamp", Value::Bool(false)),
                ],
                values: &[
                    (Name("To Min"), Value::Float(0.0)),
                    (Name("To Max"), Value::Float(1.0)),
                ],
                links: &[(Name("Value"), NodeSocketRef::new("fac2m", Position(0)))],
            },
            Node {
                kind: &nodes::MAP_RANGE,
                id: "lums3",
                values: &[
                    (Name("From Min"), Value::Float(0.0)),
                    (Name("From Max"), Value::Float(1.0)),
                ],
                links: &[
                    (Name("To Min"), NodeSocketRef::new("lums2", Position(0))),
                    (Name("To Max"), NodeSocketRef::new("lum3ss", Position(0))),
                ],
                ..Node::default()
            },
            Node {
                kind: &nodes::MATH,
                id: "lums3inv",
                properties: &[("operation", Value::Enum("SUBTRACT"))],
                values: &[(Position(0), Value::Float(1.0))],
                links: &[(Position(1), NodeSocketRef::new("lums3", Position(0)))],
            },
            Node {
                kind: &nodes::MAP_RANGE,
                id: "lum4blend",
                values: &[
                    (Name("From Min"), Value::Float(0.0)),
                    (Name("From Max"), Value::Float(1.0)),
                ],
                links: &[
                    (Name("To Min"), NodeSocketRef::new("lums3inv", Position(0))),
                    (Name("To Max"), NodeSocketRef::new("lum4ss", Position(0))),
                ],
                ..Node::default()
            },
            Node {
                kind: &nodes::MATH,
                id: "fac3m",
                properties: &[("operation", Value::Enum("MULTIPLY_ADD"))],
                links: &[(Position(1), NodeSocketRef::new("lum4blend", Position(0)))],
                ..Node::default()
            },
            Node {
                kind: &nodes::MAP_RANGE,
                id: "fac3ss",
                properties: &[
                    ("interpolation_type", Value::Enum("SMOOTHSTEP")),
                    ("clamp", Value::Bool(false)),
                ],
                values: &[
                    (Name("To Min"), Value::Float(0.0)),
                    (Name("To Max"), Value::Float(1.0)),
                ],
                links: &[(Name("Value"), NodeSocketRef::new("fac3m", Position(0)))],
            },
        ],
        inputs: &[
            ("fac2", NodeSocketRef::new("fac1m", Position(0))),
            ("fac2", NodeSocketRef::new("fac1m", Position(2))),
            ("fac3", NodeSocketRef::new("fac2m", Position(0))),
            ("fac3", NodeSocketRef::new("fac2m", Position(2))),
            ("fac4", NodeSocketRef::new("fac3m", Position(0))),
            ("fac4", NodeSocketRef::new("fac3m", Position(2))),
            ("lum1", NodeSocketRef::new("lum1ss", Name("Value"))),
            ("lum2", NodeSocketRef::new("lum2ss", Name("Value"))),
            ("lum3", NodeSocketRef::new("lum3ss", Name("Value"))),
            ("lum4", NodeSocketRef::new("lum4ss", Name("Value"))),
            ("lumstart1", NodeSocketRef::new("lum1ss", Name("From Min"))),
            ("lumstart2", NodeSocketRef::new("lum2ss", Name("From Min"))),
            ("lumstart3", NodeSocketRef::new("lum3ss", Name("From Min"))),
            ("lumstart4", NodeSocketRef::new("lum4ss", Name("From Min"))),
            ("lumend1", NodeSocketRef::new("lum1ss", Name("From Max"))),
            ("lumend2", NodeSocketRef::new("lum2ss", Name("From Max"))),
            ("lumend3", NodeSocketRef::new("lum3ss", Name("From Max"))),
            ("lumend4", NodeSocketRef::new("lum4ss", Name("From Max"))),
            ("lumfac2", NodeSocketRef::new("lum2blend", Name("Value"))),
            ("lumfac3", NodeSocketRef::new("lum3blend", Name("Value"))),
            ("lumfac4", NodeSocketRef::new("lum4blend", Name("Value"))),
            (
                "blendstart2",
                NodeSocketRef::new("fac1ss", Name("From Min")),
            ),
            (
                "blendstart3",
                NodeSocketRef::new("fac2ss", Name("From Min")),
            ),
            (
                "blendstart4",
                NodeSocketRef::new("fac3ss", Name("From Min")),
            ),
            ("blendend2", NodeSocketRef::new("fac1ss", Name("From Max"))),
            ("blendend3", NodeSocketRef::new("fac2ss", Name("From Max"))),
            ("blendend4", NodeSocketRef::new("fac3ss", Name("From Max"))),
        ],
        outputs: &[
            ("fac1", NodeSocketRef::new("fac1ss", Position(0))),
            ("fac2", NodeSocketRef::new("fac2ss", Position(0))),
            ("fac3", NodeSocketRef::new("fac3ss", Position(0))),
        ],
        ..NodeGroup::default()
    };

    pub static MULTIBLEND_TEXTURE: NodeGroup = NodeGroup {
        nodes: &[
            Node {
                kind: &nodes::MIX_RGB,
                id: "mix_color1",
                properties: &[("blend_type", Value::Enum("MIX"))],
                ..Node::default()
            },
            Node {
                kind: &nodes::MAP_RANGE,
                id: "mix_alpha1",
                properties: &[("clamp", Value::Bool(false))],
                values: &[
                    (Name("From Min"), Value::Float(0.0)),
                    (Name("From Max"), Value::Float(1.0)),
                ],
                ..Node::default()
            },
            Node {
                kind: &nodes::MIX_RGB,
                id: "mix_color2",
                properties: &[("blend_type", Value::Enum("MIX"))],
                links: &[(
                    Name("Color1"),
                    NodeSocketRef::new("mix_color1", Name("Color")),
                )],
                ..Node::default()
            },
            Node {
                kind: &nodes::MAP_RANGE,
                id: "mix_alpha2",
                properties: &[("clamp", Value::Bool(false))],
                values: &[
                    (Name("From Min"), Value::Float(0.0)),
                    (Name("From Max"), Value::Float(1.0)),
                ],
                links: &[(
                    Name("To Min"),
                    NodeSocketRef::new("mix_alpha1", Position(0)),
                )],
            },
            Node {
                kind: &nodes::MIX_RGB,
                id: "mix_color3",
                properties: &[("blend_type", Value::Enum("MIX"))],
                links: &[(
                    Name("Color1"),
                    NodeSocketRef::new("mix_color2", Name("Color")),
                )],
                ..Node::default()
            },
            Node {
                kind: &nodes::MAP_RANGE,
                id: "mix_alpha3",
                properties: &[("clamp", Value::Bool(false))],
                values: &[
                    (Name("From Min"), Value::Float(0.0)),
                    (Name("From Max"), Value::Float(1.0)),
                ],
                links: &[(
                    Name("To Min"),
                    NodeSocketRef::new("mix_alpha2", Position(0)),
                )],
            },
        ],
        inputs: &[
            ("color", NodeSocketRef::new("mix_color1", Name("Color1"))),
            ("color2", NodeSocketRef::new("mix_color1", Name("Color2"))),
            ("color3", NodeSocketRef::new("mix_color2", Name("Color2"))),
            ("color4", NodeSocketRef::new("mix_color3", Name("Color2"))),
            ("alpha", NodeSocketRef::new("mix_alpha1", Name("To Min"))),
            ("alpha2", NodeSocketRef::new("mix_alpha1", Name("To Max"))),
            ("alpha3", NodeSocketRef::new("mix_alpha2", Name("To Max"))),
            ("alpha4", NodeSocketRef::new("mix_alpha3", Name("To Max"))),
            ("fac1", NodeSocketRef::new("mix_color1", Name("Fac"))),
            ("fac1", NodeSocketRef::new("mix_alpha1", Name("Value"))),
            ("fac2", NodeSocketRef::new("mix_color2", Name("Fac"))),
            ("fac2", NodeSocketRef::new("mix_alpha2", Name("Value"))),
            ("fac3", NodeSocketRef::new("mix_color3", Name("Fac"))),
            ("fac3", NodeSocketRef::new("mix_alpha3", Name("Value"))),
        ],
        outputs: &[
            ("color", NodeSocketRef::new("mix_color3", Name("Color"))),
            ("alpha", NodeSocketRef::new("mix_alpha3", Position(0))),
        ],
        ..NodeGroup::default()
    };

    pub static MULTIBLEND_VALUE: NodeGroup = NodeGroup {
        nodes: &[
            Node {
                kind: &nodes::MAP_RANGE,
                id: "mix1",
                properties: &[("clamp", Value::Bool(false))],
                values: &[
                    (Name("From Min"), Value::Float(0.0)),
                    (Name("From Max"), Value::Float(1.0)),
                ],
                ..Node::default()
            },
            Node {
                kind: &nodes::MAP_RANGE,
                id: "mix2",
                properties: &[("clamp", Value::Bool(false))],
                values: &[
                    (Name("From Min"), Value::Float(0.0)),
                    (Name("From Max"), Value::Float(1.0)),
                ],
                links: &[(Name("To Min"), NodeSocketRef::new("mix1", Position(0)))],
            },
            Node {
                kind: &nodes::MAP_RANGE,
                id: "mix3",
                properties: &[("clamp", Value::Bool(false))],
                values: &[
                    (Name("From Min"), Value::Float(0.0)),
                    (Name("From Max"), Value::Float(1.0)),
                ],
                links: &[(Name("To Min"), NodeSocketRef::new("mix2", Position(0)))],
            },
        ],
        inputs: &[
            ("val1", NodeSocketRef::new("mix1", Name("To Min"))),
            ("val2", NodeSocketRef::new("mix1", Name("To Max"))),
            ("val3", NodeSocketRef::new("mix2", Name("To Max"))),
            ("val4", NodeSocketRef::new("mix3", Name("To Max"))),
            ("fac1", NodeSocketRef::new("mix1", Name("Value"))),
            ("fac2", NodeSocketRef::new("mix2", Name("Value"))),
            ("fac3", NodeSocketRef::new("mix3", Name("Value"))),
        ],
        outputs: &[("val", NodeSocketRef::new("mix3", Position(0)))],
        ..NodeGroup::default()
    };

    pub static BLEND_3_VALUES: NodeGroup = NodeGroup {
        nodes: &[
            Node {
                kind: &nodes::MAP_RANGE,
                id: "mix1",
                properties: &[("clamp", Value::Bool(false))],
                values: &[
                    (Name("From Min"), Value::Float(0.0)),
                    (Name("From Max"), Value::Float(1.0)),
                ],
                ..Node::default()
            },
            Node {
                kind: &nodes::MAP_RANGE,
                id: "mix2",
                properties: &[("clamp", Value::Bool(false))],
                values: &[
                    (Name("From Min"), Value::Float(0.0)),
                    (Name("From Max"), Value::Float(1.0)),
                ],
                links: &[(Name("To Min"), NodeSocketRef::new("mix1", Position(0)))],
            },
        ],
        inputs: &[
            ("val1", NodeSocketRef::new("mix1", Name("To Min"))),
            ("val2", NodeSocketRef::new("mix1", Name("To Max"))),
            ("val3", NodeSocketRef::new("mix2", Name("To Max"))),
            ("fac1", NodeSocketRef::new("mix1", Name("Value"))),
            ("fac2", NodeSocketRef::new("mix2", Name("Value"))),
        ],
        outputs: &[("val", NodeSocketRef::new("mix2", Position(0)))],
        ..NodeGroup::default()
    };

    pub static CLIP_ALPHA: NodeGroup = NodeGroup {
        nodes: &[Node {
            kind: &nodes::MATH,
            id: "clip",
            properties: &[("operation", Value::Enum("GREATER_THAN"))],
            ..Node::default()
        }],
        inputs: &[
            ("value", NodeSocketRef::new("clip", Position(0))),
            ("ref", NodeSocketRef::new("clip", Position(1))),
        ],
        outputs: &[("value", NodeSocketRef::new("clip", Position(0)))],
        ..NodeGroup::default()
    };

    pub static MOD2X: NodeGroup = NodeGroup {
        nodes: &[Node {
            kind: &nodes::MIX_RGB,
            id: "multiply",
            properties: &[("blend_type", Value::Enum("MULTIPLY"))],
            values: &[
                (Name("Color2"), Value::Color([2.0, 2.0, 2.0, 1.0])),
                (Name("Fac"), Value::Float(1.0)),
            ],
            ..Node::default()
        }],
        inputs: &[("color", NodeSocketRef::new("multiply", Name("Color1")))],
        outputs: &[("color", NodeSocketRef::new("multiply", Name("Color")))],
        ..NodeGroup::default()
    };
}

#[cfg(test)]
mod tests {
    use std::collections::BTreeSet;

    use super::super::nodes::{NodeGroup, NodeSocketRef, NodeType};

    use super::*;

    static NODES: &[&NodeType] = &[
        &shaders::PRINCIPLED,
        &shaders::TRANSPARENT,
        &shaders::GLASS,
        &nodes::TEX_IMAGE,
        &nodes::TEX_COORD,
        &nodes::MAPPING,
        &nodes::NORMAL_MAP,
        &nodes::SEPARATE_RGB,
        &nodes::COMBINE_RGB,
        &nodes::MATH,
        &nodes::MIX_RGB,
        &nodes::VERTEX_COLOR,
        &nodes::OBJECT_INFO,
        &nodes::MAP_RANGE,
        &nodes::VECTOR_MATH,
        &nodes::SEPARATE_XYZ,
    ];

    static NODE_GROUPS: &[&NodeGroup] = &[
        &groups::TEXTURE,
        &groups::TRANSFORMED_TEXTURE,
        &groups::SPLIT_TEXTURE,
        &groups::DX_NORMAL_MAP_CONVERTER,
        &groups::SSBUMP_CONVERTER,
        &groups::NORMAL_MAP,
        &groups::DETAIL_TEXTURE,
        &groups::COLOR_TEXTURE,
        &groups::BLEND_TEXTURE,
        &groups::VERTEX_COLOR,
        &groups::SEPARATED_VERTEX_COLOR,
        &groups::OBJECT_COLOR,
        &groups::MODULATED_FACTOR,
        &groups::MULTIPLY_VALUE,
        &groups::BLEND_VALUES,
        &groups::INVERT_VALUE,
        &groups::FWB_FACTORS,
        &groups::MULTIBLEND_TEXTURE,
        &groups::MULTIBLEND_VALUE,
        &groups::BLEND_3_VALUES,
        &groups::CLIP_ALPHA,
        &groups::MOD2X,
    ];

    #[test]
    fn check_nodes() {
        for node in NODES {
            eprintln!("checking `{}`", node.blender_id);
            check_node(node);
        }
    }

    #[test]
    fn check_node_groups() {
        for group in NODE_GROUPS {
            check_node_group(group);
        }
    }

    fn check_node(node: &'static NodeType) {
        let mut input_socket_ids = BTreeSet::new();

        for input_socket in node.input_sockets {
            assert!(
                input_socket_ids.insert(input_socket),
                "duplicate input sockets"
            );
        }

        let mut output_socket_ids = BTreeSet::new();

        for output_socket in node.output_sockets {
            assert!(
                output_socket_ids.insert(output_socket),
                "duplicate output sockets"
            );
        }

        let mut properties = BTreeSet::new();

        for &property in node.properties {
            assert!(properties.insert(property), "duplicate property");
        }
    }

    fn check_node_group(node_group: &'static NodeGroup) {
        let mut node_ids = BTreeSet::new();
        let mut outputs = BTreeSet::new();

        for node in node_group.nodes {
            assert!(node_ids.insert(node.id), "duplicate node id");

            for (target, src) in node.links {
                assert!(
                    node.kind.input_sockets.iter().any(|s| s == target),
                    "invalid node link target `{target:?}`"
                );

                assert!(outputs.contains(src), "invalid node link source `{src:?}`");
            }

            for (target, _) in node.values {
                assert!(
                    node.kind.input_sockets.iter().any(|s| s == target),
                    "invalid node value target `{target:?}`"
                );
            }

            for (target, _) in node.properties {
                assert!(
                    node.kind.properties.contains(target),
                    "invalid node property target `{target:?}`"
                );
            }

            for &output in node.kind.output_sockets {
                outputs.insert(NodeSocketRef::new(node.id, output));
            }
        }

        let mut properties = BTreeSet::new();

        for (name, target) in node_group.properties {
            assert!(properties.insert(*name), "duplicate node group property");

            let node = node_group
                .nodes
                .iter()
                .find(|n| n.id == target.target)
                .expect("invalid node group property target");

            assert!(
                node.kind.properties.contains(&target.name),
                "invalid node group property target"
            );
        }

        for (_name, target) in node_group.inputs {
            let node = node_group
                .nodes
                .iter()
                .find(|n| n.id == target.target)
                .expect("invalid node group property target");
            assert!(
                node.kind.input_sockets.iter().any(|&s| s == target.socket),
                "invalid node group input target `{target:?}`"
            );
        }

        let mut outputs = BTreeSet::new();

        for (name, target) in node_group.outputs {
            assert!(outputs.insert(*name), "duplicate node group output");

            let node = node_group
                .nodes
                .iter()
                .find(|n| n.id == target.target)
                .expect("invalid node group property target");
            assert!(
                node.kind.output_sockets.iter().any(|&s| s == target.socket),
                "invalid node group output target `{target:?}`"
            );
        }
    }
}
