use std::{cmp::Ordering, collections::BTreeMap, mem, ptr};

use log::debug;
use plumber_core::fs::GamePathBuf;
use pyo3::prelude::*;

use super::{builder_base::BuiltInput, definitions::NODE_MARGIN};

#[derive(Debug, PartialEq, Eq, PartialOrd, Ord, Clone, Copy)]
pub enum NodeSocketId {
    Position(u32),
    Name(&'static str),
}

impl IntoPy<PyObject> for NodeSocketId {
    fn into_py(self, py: Python) -> PyObject {
        match self {
            NodeSocketId::Position(p) => p.into_py(py),
            NodeSocketId::Name(n) => n.into_py(py),
        }
    }
}

impl From<u32> for NodeSocketId {
    fn from(i: u32) -> Self {
        Self::Position(i)
    }
}

impl From<&'static str> for NodeSocketId {
    fn from(s: &'static str) -> Self {
        Self::Name(s)
    }
}

#[derive(Debug)]
pub struct NodeType {
    pub blender_id: &'static str,
    pub size: [f32; 2],
    pub input_sockets: &'static [NodeSocketId],
    pub output_sockets: &'static [NodeSocketId],
    pub properties: &'static [&'static str],
}

impl NodeType {
    pub const fn default() -> Self {
        Self {
            blender_id: "",
            size: [0.0, 0.0],
            input_sockets: &[],
            output_sockets: &[],
            properties: &[],
        }
    }

    pub fn build(
        &'static self,
        properties: BTreeMap<&'static str, Value>,
        socket_values: BTreeMap<NodeSocketId, Value>,
        socket_links: BTreeMap<NodeSocketId, BuiltNodeSocketRef>,
        position: [f32; 2],
    ) -> BuiltNode {
        BuiltNode {
            kind: self,
            position,
            properties,
            socket_values,
            socket_links,
        }
    }
}

#[derive(Debug, Clone)]
pub enum Value {
    Bool(bool),
    Float(f32),
    Color([f32; 4]),
    Vec([f32; 3]),
    Enum(&'static str),
    Texture(GamePathBuf),
}

#[pyclass(module = "plumber")]
pub struct TextureRef(String);

#[pymethods]
impl TextureRef {
    fn path(&self) -> &str {
        &self.0
    }
}

impl IntoPy<PyObject> for Value {
    fn into_py(self, py: Python) -> PyObject {
        match self {
            Value::Bool(b) => b.into_py(py),
            Value::Float(f) => f.into_py(py),
            Value::Color(c) => c.into_py(py),
            Value::Vec(v) => v.into_py(py),
            Value::Enum(e) => e.into_py(py),
            Value::Texture(t) => TextureRef(t.into_string()).into_py(py),
        }
    }
}

#[derive(Debug, PartialEq, Eq, PartialOrd, Ord)]
pub struct NodeSocketRef {
    pub target: &'static str,
    pub socket: NodeSocketId,
}

impl NodeSocketRef {
    pub const fn new(target: &'static str, socket: NodeSocketId) -> Self {
        Self { target, socket }
    }

    pub fn depends_on(&self, target: &'static str) -> bool {
        self.target == target
    }
}

#[derive(Debug, Clone, Copy, PartialEq, Eq, PartialOrd, Ord)]
pub struct Ref {
    pub target: &'static str,
    pub name: &'static str,
}

impl Ref {
    pub const fn new(target: &'static str, name: &'static str) -> Self {
        Self { target, name }
    }

    pub fn depends_on(&self, target: &'static str) -> bool {
        self.target == target
    }

    pub(crate) fn evaluate_input(
        &self,
        inputs: &BTreeMap<&'static str, BuiltInput>,
    ) -> BuiltNodeSocketRef {
        let input = self.evaluate_input_only(inputs);
        if let Some(socket) = input.outputs.get(self.name) {
            *socket
        } else {
            panic!("could not find input link target socket {}", self.name)
        }
    }

    pub(crate) fn evaluate_input_only<'a>(
        &self,
        inputs: &'a BTreeMap<&'static str, BuiltInput>,
    ) -> &'a BuiltInput {
        if let Some(input) = inputs.get(self.target) {
            input
        } else {
            panic!("could not find input link target input {}", self.target)
        }
    }
}

#[derive(Debug)]
pub struct Node {
    pub kind: &'static NodeType,
    pub id: &'static str,
    pub properties: &'static [(&'static str, Value)],
    pub values: &'static [(NodeSocketId, Value)],
    pub links: &'static [(NodeSocketId, NodeSocketRef)],
}

impl Node {
    pub const fn default() -> Self {
        const DEFAULT: &NodeType = &NodeType::default();

        Self {
            kind: DEFAULT,
            id: "",
            properties: &[],
            values: &[],
            links: &[],
        }
    }

    pub fn build(
        &self,
        nodes: &mut Vec<BuiltNode>,
        outputs: &mut BTreeMap<NodeSocketRef, BuiltNodeSocketRef>,
        outside_links: impl Iterator<Item = (NodeSocketId, BuiltNodeSocketLink)> + Clone,
        outside_properties: impl Iterator<Item = (&'static str, Value)>,
        base_position: [f32; 2],
        check_previous: bool,
    ) -> [f32; 2] {
        debug!(
            "building node {} at base position {:?}",
            self.id, base_position
        );

        let outside_ref_links = outside_links.clone().filter_map(|(socket, link)| {
            if let BuiltNodeSocketLink::Link(r) = link {
                Some((socket, r))
            } else {
                None
            }
        });

        let outside_ref_values = outside_links.filter_map(|(socket, link)| {
            if let BuiltNodeSocketLink::Value(v) = link {
                Some((socket, v))
            } else {
                None
            }
        });

        let [mut x, mut y] = base_position;

        let links = self
            .links
            .iter()
            .map(|(socket, r)| {
                let built_ref = outputs.get(r).expect("link ref target should exist");

                // this node should be placed on the right side of it's rightmost dependency
                let next_column = built_ref.evaluate_node(nodes).next_column();
                x = x.max(next_column);
                debug!(
                    "node {} placed onto next column of dependency {}, new x: {}",
                    self.id, r.target, x
                );

                (*socket, *built_ref)
            })
            .chain(outside_ref_links)
            .collect();

        let values = self
            .values
            .iter()
            .cloned()
            .chain(outside_ref_values)
            .collect();

        if check_previous {
            if let Some(built) = nodes.last() {
                let [x_min, x_max] = built.x_bounds();

                let self_x_min = x;

                // if the previous node is on the right side of this node, it should just be placed directly below it
                if x_min >= self_x_min {
                    x = built.position[0];
                    y = built.next_row();
                    debug!(
                        "placing node {} below previous node with same x, new position: [{}, {}]",
                        self.id, x, y
                    );
                }
                // otherwise this node should be placed below the previous node, if it would overlap the same column
                else if self_x_min < x_max {
                    y = built.next_row();
                    debug!(
                        "placing node {} below previous node, new position: [{}, {}]",
                        self.id, x, y
                    );
                }
            }
        }

        let built = self.kind.build(
            self.properties
                .iter()
                .cloned()
                .chain(outside_properties)
                .collect(),
            values,
            links,
            [x, y],
        );

        let index = nodes.len();
        nodes.push(built);

        // register outputs
        for &socket in self.kind.output_sockets {
            outputs.insert(
                NodeSocketRef {
                    target: self.id,
                    socket,
                },
                BuiltNodeSocketRef {
                    node_index: index,
                    socket,
                },
            );
        }

        [x + self.kind.size[0], y + self.kind.size[1]]
    }
}

#[derive(Debug, Clone, Copy)]
#[pyclass(module = "plumber")]
pub struct BuiltNodeSocketRef {
    node_index: usize,
    socket: NodeSocketId,
}

impl BuiltNodeSocketRef {
    pub(crate) fn evaluate_node<'a>(&self, built_nodes: &'a [BuiltNode]) -> &'a BuiltNode {
        &built_nodes[self.node_index]
    }
}

#[pymethods]
impl BuiltNodeSocketRef {
    fn node_index(&self) -> usize {
        self.node_index
    }

    fn socket(&self) -> NodeSocketId {
        self.socket
    }
}

#[derive(Debug, Clone)]
pub enum BuiltNodeSocketLink {
    Link(BuiltNodeSocketRef),
    Value(Value),
}

#[pyclass(module = "plumber")]
pub struct BuiltNode {
    kind: &'static NodeType,
    position: [f32; 2],
    properties: BTreeMap<&'static str, Value>,
    socket_values: BTreeMap<NodeSocketId, Value>,
    socket_links: BTreeMap<NodeSocketId, BuiltNodeSocketRef>,
}

impl BuiltNode {
    pub(crate) fn next_column(&self) -> f32 {
        self.position[0] + self.kind.size[0] + NODE_MARGIN
    }

    pub(crate) fn next_row(&self) -> f32 {
        self.position[1] + self.kind.size[1] + NODE_MARGIN
    }

    pub(crate) fn x_bounds(&self) -> [f32; 2] {
        [self.position[0], self.position[0] + self.kind.size[0]]
    }

    pub(crate) fn offset_x(&mut self, offset: f32) {
        self.position[0] += offset;
    }

    pub(crate) fn invert_y(&mut self) {
        self.position[1] = -self.position[1];
    }
}

#[pymethods]
impl BuiltNode {
    fn blender_id(&self) -> &'static str {
        self.kind.blender_id
    }

    fn position(&self) -> [f32; 2] {
        self.position
    }

    fn properties(&mut self) -> BTreeMap<&'static str, Value> {
        mem::take(&mut self.properties)
    }

    fn socket_values(&mut self) -> BTreeMap<NodeSocketId, Value> {
        mem::take(&mut self.socket_values)
    }

    fn socket_links(&mut self) -> BTreeMap<NodeSocketId, BuiltNodeSocketRef> {
        mem::take(&mut self.socket_links)
    }
}

#[derive(Debug)]
pub struct NodeGroup {
    pub nodes: &'static [Node],
    pub properties: &'static [(&'static str, Ref)],
    pub inputs: &'static [(&'static str, NodeSocketRef)],
    pub outputs: &'static [(&'static str, NodeSocketRef)],
}

impl NodeGroup {
    pub const fn default() -> Self {
        Self {
            nodes: &[],
            properties: &[],
            inputs: &[],
            outputs: &[],
        }
    }

    pub fn build(
        &self,
        nodes: &mut Vec<BuiltNode>,
        outputs: &mut BTreeMap<&'static str, BuiltNodeSocketRef>,
        outside_links: &BTreeMap<&'static str, BuiltNodeSocketLink>,
        outside_properties: &BTreeMap<&'static str, Value>,
        position: [f32; 2],
    ) -> [f32; 2] {
        debug!("building node group");

        let mut local_outputs = BTreeMap::new();

        let mut first = true;
        let [mut x_max, mut y_max] = position;

        for node in self.nodes {
            let links = self
                .inputs
                .iter()
                .filter(|(_, r)| r.depends_on(node.id))
                .map(|(name, r)| {
                    let Some(socket) = outside_links
                        .get(name)
                        .cloned()
                        .or_else(|| outputs.get(name).map(|&l| BuiltNodeSocketLink::Link(l)))
                    else {
                        panic!("input {name} should not be unlinked");
                    };
                    (r.socket, socket)
                });

            let properties = self
                .properties
                .iter()
                .filter(|(_, r)| r.depends_on(node.id))
                .map(|(name, r)| {
                    let value = outside_properties
                        .get(name)
                        .expect("input property should not be unspecified");

                    (r.name, value.clone())
                });

            let [x_max_node, y_max_node] = node.build(
                nodes,
                &mut local_outputs,
                links,
                properties,
                position,
                !first,
            );

            x_max = x_max.max(x_max_node);
            y_max = y_max.max(y_max_node);

            first = false;
        }

        for (name, r) in self.outputs {
            let evaluated_output = local_outputs
                .get(r)
                .expect("output ref target should exist");
            outputs.insert(*name, *evaluated_output);
        }

        [x_max, y_max]
    }
}

#[derive(Debug)]
pub struct NodeGroupRef {
    pub target: &'static NodeGroup,
    pub name: &'static str,
}

impl NodeGroupRef {
    pub fn new(target: &'static NodeGroup, name: &'static str) -> Self {
        Self { target, name }
    }
}

impl NodeGroupRef {
    pub fn depends_on(&self, target: &'static NodeGroup) -> bool {
        ptr::eq(self.target, target)
    }
}

impl PartialEq for NodeGroupRef {
    fn eq(&self, other: &Self) -> bool {
        ptr::eq(self.target, other.target) && self.name == other.name
    }
}

impl Eq for NodeGroupRef {}

impl PartialOrd for NodeGroupRef {
    fn partial_cmp(&self, other: &Self) -> Option<Ordering> {
        Some(self.cmp(other))
    }
}

impl Ord for NodeGroupRef {
    fn cmp(&self, other: &Self) -> Ordering {
        match (self.target as *const NodeGroup).cmp(&(other.target as *const _)) {
            Ordering::Equal => {}
            ord => return ord,
        }
        self.name.cmp(other.name)
    }
}
