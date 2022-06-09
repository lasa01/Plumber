use std::{collections::BTreeMap, iter, mem, ptr};

use float_ord::FloatOrd;
use itertools::{Either, Itertools};
use log::debug;
use pyo3::prelude::*;

use super::{
    definitions::NODE_MARGIN,
    nodes::{
        BuiltNode, BuiltNodeSocketLink, BuiltNodeSocketRef, NodeGroup, NodeGroupRef, NodeSocketId,
        NodeType, Ref, Value,
    },
};

#[derive(Debug)]
pub(crate) struct Input {
    id: &'static str,
    pipeline: Vec<&'static NodeGroup>,
    links: BTreeMap<NodeGroupRef, InputLink>,
    properties: BTreeMap<NodeGroupRef, Value>,
}

impl Input {
    fn is_dependency_free(&self) -> bool {
        self.links.values().all(InputLink::is_dependency_free)
    }

    fn depends_on(&self, other: &Self) -> bool {
        for link in self.links.values() {
            if link.depends_on(other.id) {
                return true;
            }
        }
        false
    }

    fn dependents<'a>(
        &'a self,
        inputs: &'a BTreeMap<&'static str, Input>,
    ) -> impl Iterator<Item = &'a Input> + 'a {
        inputs
            .values()
            .filter(|other_input| other_input.depends_on(self))
    }

    pub fn pipeline(&mut self, pipeline: Vec<&'static NodeGroup>) -> &mut Self {
        self.pipeline = pipeline;
        self
    }

    pub fn push(&mut self, node_group: &'static NodeGroup) -> &mut Self {
        self.pipeline.push(node_group);
        self
    }

    pub fn link(
        &mut self,
        target: &'static NodeGroup,
        socket: &'static str,
        source: impl Into<InputLink>,
    ) -> &mut Self {
        self.links
            .insert(NodeGroupRef::new(target, socket), source.into());
        self
    }

    pub fn property(
        &mut self,
        target: &'static NodeGroup,
        property: &'static str,
        value: Value,
    ) -> &mut Self {
        self.properties
            .insert(NodeGroupRef::new(target, property), value);
        self
    }

    pub fn socket(&self, socket: &'static str) -> Ref {
        Ref::new(self.id, socket)
    }

    fn build(&self, inputs: &mut BTreeMap<&'static str, BuiltInput>, nodes: &mut Vec<BuiltNode>) {
        debug!("building input {}", self.id);

        let mut outputs = BTreeMap::new();
        let mut x_min = 0.0f32;
        let mut y_min = 0.0f32;

        // find a free position for this input
        for target in self.links.values() {
            if let Some(input) = target.evaluate_input_only(inputs) {
                // the input should be placed onto the next column of it's rightmost dependency
                x_min = x_min.max(input.next_column());
                debug!(
                    "input {} placed onto the next column of dependency {}, new x: {}",
                    self.id, input.id, x_min
                );
            }
        }

        // make sure the position doesn't overlap any previous input
        for input in inputs.values() {
            if !input.x_overlaps(x_min) {
                continue;
            }

            // place the input below any previous inputs in this column
            y_min = y_min.max(input.next_row());
            debug!(
                "input {} placed below overlapping input {}, new y: {}",
                self.id, input.id, y_min
            );
        }

        let [x_max, y_max] = build_pipeline(
            &self.pipeline,
            [x_min, y_min],
            &self.links,
            &self.properties,
            inputs,
            &mut outputs,
            nodes,
        );

        inputs.insert(
            self.id,
            BuiltInput {
                id: self.id,
                outputs,
                x_max,
                y_max,
            },
        );
    }
}

pub(crate) struct BuiltInput {
    id: &'static str,
    pub outputs: BTreeMap<&'static str, BuiltNodeSocketRef>,
    x_max: f32,
    y_max: f32,
}

impl BuiltInput {
    pub fn next_column(&self) -> f32 {
        self.x_max + NODE_MARGIN
    }

    pub fn next_row(&self) -> f32 {
        self.y_max + NODE_MARGIN
    }

    pub fn x_overlaps(&self, min: f32) -> bool {
        min < self.x_max
    }
}

#[derive(Debug)]
pub(crate) enum InputLink {
    Input(Ref),
    Value(Value),
}

impl InputLink {
    fn is_dependency_free(&self) -> bool {
        match self {
            InputLink::Input(_) => false,
            InputLink::Value(_) => true,
        }
    }

    fn depends_on(&self, target: &'static str) -> bool {
        match self {
            InputLink::Input(r) => r.depends_on(target),
            InputLink::Value(_) => false,
        }
    }

    fn evaluate(&self, inputs: &BTreeMap<&'static str, BuiltInput>) -> BuiltNodeSocketLink {
        match self {
            InputLink::Input(r) => BuiltNodeSocketLink::Link(r.evaluate_input(inputs)),
            InputLink::Value(v) => BuiltNodeSocketLink::Value(v.clone()),
        }
    }

    fn evaluate_input_only<'a>(
        &self,
        inputs: &'a BTreeMap<&'static str, BuiltInput>,
    ) -> Option<&'a BuiltInput> {
        match self {
            InputLink::Input(r) => Some(r.evaluate_input_only(inputs)),
            InputLink::Value(_) => None,
        }
    }
}

impl From<Ref> for InputLink {
    fn from(r: Ref) -> Self {
        Self::Input(r)
    }
}

impl From<Value> for InputLink {
    fn from(v: Value) -> Self {
        Self::Value(v)
    }
}

pub(crate) struct Output {
    input: Ref,
    pipeline: Vec<&'static NodeGroup>,
    links: BTreeMap<NodeGroupRef, InputLink>,
    properties: BTreeMap<NodeGroupRef, Value>,
    shader_socket: NodeSocketId,
}

impl Output {
    pub fn push(&mut self, node_group: &'static NodeGroup) -> &mut Self {
        self.pipeline.push(node_group);
        self
    }

    pub fn link_input(&mut self, target: &'static NodeGroup, socket: &'static str) -> &mut Self {
        self.links
            .insert(NodeGroupRef::new(target, socket), self.input.into());
        self
    }

    pub fn link(
        &mut self,
        target: &'static NodeGroup,
        socket: &'static str,
        source: impl Into<InputLink>,
    ) -> &mut Self {
        self.links
            .insert(NodeGroupRef::new(target, socket), source.into());
        self
    }

    fn dependencies(&self) -> impl Iterator<Item = &'static str> + '_ {
        if self.pipeline.is_empty() {
            Either::Left(iter::once(self.input.target))
        } else {
            Either::Right(self.links.values().filter_map(|l| {
                if let InputLink::Input(r) = l {
                    Some(r.target)
                } else {
                    None
                }
            }))
        }
    }

    fn build(
        &self,
        inputs: &BTreeMap<&'static str, BuiltInput>,
        nodes: &mut Vec<BuiltNode>,
        position: [f32; 2],
        x_max: &mut f32,
        y_max: &mut f32,
    ) -> (NodeSocketId, BuiltNodeSocketRef) {
        if self.pipeline.is_empty() {
            let input_socket = self.input.evaluate_input(inputs);
            return (self.shader_socket, input_socket);
        }

        let mut outputs = BTreeMap::new();

        let [x_max_local, y_max_local] = build_pipeline(
            &self.pipeline,
            position,
            &self.links,
            &self.properties,
            inputs,
            &mut outputs,
            nodes,
        );

        *x_max = x_max.max(x_max_local);
        *y_max = y_max.max(y_max_local);

        let last_group = self.pipeline.last().unwrap();
        assert!(
            last_group.outputs.len() == 1,
            "output pipeline last nodegroup must have only exactly output"
        );
        let output_name = last_group.outputs.first().unwrap().0;

        let output = outputs
            .get(output_name)
            .expect("output output should exist");
        (self.shader_socket, *output)
    }
}

fn build_pipeline(
    pipeline: &[&'static NodeGroup],
    position: [f32; 2],
    links: &BTreeMap<NodeGroupRef, InputLink>,
    properties: &BTreeMap<NodeGroupRef, Value>,
    inputs: &BTreeMap<&'static str, BuiltInput>,
    outputs: &mut BTreeMap<&'static str, BuiltNodeSocketRef>,
    nodes: &mut Vec<BuiltNode>,
) -> [f32; 2] {
    let [mut x, y] = position;
    let mut y_max = y;

    for node_group in pipeline {
        let group_links = links
            .iter()
            .filter(|(r, _)| r.depends_on(node_group))
            .map(|(r, l)| {
                let evaluated = l.evaluate(inputs);

                (r.name, evaluated)
            })
            .collect();

        let group_properties = properties
            .iter()
            .filter(|(r, _)| r.depends_on(node_group))
            .map(|(r, v)| (r.name, v.clone()))
            .collect();

        let [x_max_group, y_max_group] =
            node_group.build(nodes, outputs, &group_links, &group_properties, [x, y]);

        x = x_max_group + NODE_MARGIN;
        y_max = y_max.max(y_max_group);
    }

    let x_max = x - NODE_MARGIN;

    [x_max, y_max]
}

/// Topological sort based on Kahn's algorithm. Returns None on cyclic references.
fn topological_sort_inputs<'a>(
    inputs: &'a BTreeMap<&'static str, Input>,
) -> Option<Vec<&'a Input>> {
    let mut remaining_edges = inputs
        .values()
        .flat_map(|node| node.dependents(inputs).map(|dependent| (&*node, dependent)))
        .collect_vec();

    let mut start_nodes = inputs
        .values()
        .filter(|i| i.is_dependency_free())
        .collect_vec();

    let mut sorted = Vec::with_capacity(inputs.len());

    let mut removed_edge_targets = Vec::with_capacity(remaining_edges.len());
    while let Some(node) = start_nodes.pop() {
        // start nodes don't depend on anything, so they can be anywhere in the sorted list
        sorted.push(node);

        // remove all edges which are coming from this start node
        remaining_edges.retain(|&(source, target)| {
            if ptr::eq(source, node) {
                removed_edge_targets.push(target);
                false
            } else {
                true
            }
        });

        // check if any of the removed edges' targets are now "start nodes"
        for &target in &removed_edge_targets {
            // if no more edges connected from something to this target, this is a "start node"
            if remaining_edges
                .iter()
                .all(|&(_, remaining_target)| !ptr::eq(remaining_target, target))
            {
                start_nodes.push(target);
            }
        }

        removed_edge_targets.clear();
    }

    // if all edges couldn't be removed, there must be a cycle somewhere
    if remaining_edges.is_empty() {
        Some(sorted)
    } else {
        None
    }
}

pub(crate) enum ColorSpace {
    Srgb,
    NonColor,
}

impl IntoPy<PyObject> for ColorSpace {
    fn into_py(self, py: Python) -> PyObject {
        match self {
            ColorSpace::Srgb => "sRGB".into_py(py),
            ColorSpace::NonColor => "Non-Color".into_py(py),
        }
    }
}

pub(crate) struct MaterialBuilder {
    properties: BTreeMap<&'static str, Value>,
    shader: &'static NodeType,
    shader_socket_values: BTreeMap<NodeSocketId, Value>,
    inputs: BTreeMap<&'static str, Input>,
    outputs: Vec<Output>,
    pub(crate) texture_color_spaces: BTreeMap<String, ColorSpace>,
}

impl MaterialBuilder {
    pub fn new(shader: &'static NodeType) -> Self {
        Self {
            properties: BTreeMap::new(),
            shader,
            shader_socket_values: BTreeMap::new(),
            inputs: BTreeMap::new(),
            outputs: Vec::new(),
            texture_color_spaces: BTreeMap::new(),
        }
    }

    pub fn property(&mut self, name: &'static str, value: Value) -> &mut Self {
        self.properties.insert(name, value);
        self
    }

    pub fn socket_value(&mut self, socket: impl Into<NodeSocketId>, value: Value) -> &mut Self {
        self.shader_socket_values.insert(socket.into(), value);
        self
    }

    pub fn has_input(&self, id: &'static str) -> bool {
        self.inputs.contains_key(id)
    }

    pub fn input(&mut self, id: &'static str) -> &mut Input {
        self.inputs.entry(id).or_insert_with(|| Input {
            id,
            pipeline: Vec::new(),
            links: BTreeMap::new(),
            properties: BTreeMap::new(),
        })
    }

    pub fn output(
        &mut self,
        socket: impl Into<NodeSocketId>,
        input: &'static str,
        source: &'static str,
    ) -> &mut Output {
        self.outputs.push(Output {
            input: Ref::new(input, source),
            pipeline: Vec::new(),
            shader_socket: socket.into(),
            links: BTreeMap::new(),
            properties: BTreeMap::new(),
        });

        self.outputs
            .last_mut()
            .expect("cannot be empty, just pushed")
    }

    pub fn build(self) -> BuiltMaterialData {
        let mut nodes = Vec::new();
        let mut built_inputs = BTreeMap::new();

        let sorted_inputs_initial =
            topological_sort_inputs(&self.inputs).expect("inputs must not have cyclic references");

        let mut sorted_inputs_reversed: Vec<&Input> =
            Vec::with_capacity(sorted_inputs_initial.len());
        let mut sorted_outputs_reversed = Vec::with_capacity(self.outputs.len());

        // resort inputs and outputs based on shader socket orders,
        // also removes unused inputs
        for socket in self.shader.input_sockets.iter().rev() {
            if let Some(output) = self.outputs.iter().find(|o| &o.shader_socket == socket) {
                sorted_outputs_reversed.push(output);

                for dependency in output.dependencies() {
                    let evaluated_input = self
                        .inputs
                        .get(dependency)
                        .expect("output dependency should exist");

                    sort_dependencies_recursive(
                        sorted_inputs_initial.iter().copied().rev(),
                        &mut sorted_inputs_reversed,
                        evaluated_input,
                    );
                }
            }
        }

        for input in sorted_inputs_reversed.into_iter().rev() {
            if built_inputs.contains_key(input.id) {
                continue;
            }

            input.build(&mut built_inputs, &mut nodes);
        }

        let mut x_max = built_inputs
            .values()
            .map(|i| i.x_max)
            .max_by_key(|&f| FloatOrd(f))
            .unwrap_or_default();

        let output_x = x_max + NODE_MARGIN;
        let mut output_y = 0.0;

        let shader_socket_links = sorted_outputs_reversed
            .into_iter()
            .rev()
            .map(|output| {
                let ret = output.build(
                    &built_inputs,
                    &mut nodes,
                    [output_x, output_y],
                    &mut x_max,
                    &mut output_y,
                );

                output_y += NODE_MARGIN;

                ret
            })
            .collect();

        let shader_x = x_max + NODE_MARGIN;

        let shader_node = self.shader.build(
            BTreeMap::new(),
            self.shader_socket_values,
            shader_socket_links,
            [shader_x, 0.0],
        );

        nodes.push(shader_node);

        // offset nodes so that the shader node is at (0, 0)
        // invert y-axis since it's from top to bottom to make node placement simpler
        for node in &mut nodes {
            node.offset_x(-shader_x);
            node.invert_y();
        }

        BuiltMaterialData {
            properties: self.properties,
            nodes,
            texture_color_spaces: self.texture_color_spaces,
        }
    }
}

fn sort_dependencies_recursive<'a>(
    mut inputs_to_check: impl Iterator<Item = &'a Input> + Clone,
    sorted_inputs_reversed: &mut Vec<&'a Input>,
    dependent: &'a Input,
) {
    sorted_inputs_reversed.push(dependent);

    if dependent.is_dependency_free() {
        return;
    }

    while let Some(input) = inputs_to_check.next() {
        if dependent.depends_on(input) {
            // inputs are already topologically sorted,
            // so no need to check all inputs for dependencies of dependencies,
            // just clone the iterator at it's current progress
            sort_dependencies_recursive(inputs_to_check.clone(), sorted_inputs_reversed, input);
        }
    }
}

#[pyclass(module = "plumber")]
pub struct BuiltMaterialData {
    properties: BTreeMap<&'static str, Value>,
    nodes: Vec<BuiltNode>,
    texture_color_spaces: BTreeMap<String, ColorSpace>,
}

#[pymethods]
impl BuiltMaterialData {
    fn properties(&mut self) -> BTreeMap<&'static str, Value> {
        mem::take(&mut self.properties)
    }

    fn nodes(&mut self) -> Vec<BuiltNode> {
        mem::take(&mut self.nodes)
    }

    fn texture_color_spaces(&mut self) -> BTreeMap<String, ColorSpace> {
        mem::take(&mut self.texture_color_spaces)
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::asset::material::definitions::groups;

    #[test]
    fn topological_sort_inputs_cyclic() {
        let inputs = [
            (
                "0",
                Input {
                    id: "0",
                    pipeline: Vec::new(),
                    links: [(
                        NodeGroupRef::new(&groups::TEXTURE, "?"),
                        InputLink::Input(Ref::new("3", "?")),
                    )]
                    .into(),
                    properties: BTreeMap::new(),
                },
            ),
            (
                "1",
                Input {
                    id: "1",
                    pipeline: Vec::new(),
                    links: [(
                        NodeGroupRef::new(&groups::TEXTURE, "?"),
                        InputLink::Value(Value::Bool(false)),
                    )]
                    .into(),
                    properties: BTreeMap::new(),
                },
            ),
            (
                "2",
                Input {
                    id: "2",
                    pipeline: Vec::new(),
                    links: [(
                        NodeGroupRef::new(&groups::TEXTURE, "?"),
                        InputLink::Input(Ref::new("0", "?")),
                    )]
                    .into(),
                    properties: BTreeMap::new(),
                },
            ),
            (
                "3",
                Input {
                    id: "3",
                    pipeline: Vec::new(),
                    links: [(
                        NodeGroupRef::new(&groups::TEXTURE, "?"),
                        InputLink::Input(Ref::new("2", "?")),
                    )]
                    .into(),
                    properties: BTreeMap::new(),
                },
            ),
        ]
        .into();

        let result = topological_sort_inputs(&inputs);

        assert!(result.is_none());
    }

    #[test]
    fn topological_sort_inputs_noncyclic() {
        let inputs: BTreeMap<_, _> = [
            (
                "0",
                Input {
                    id: "0",
                    pipeline: Vec::new(),
                    links: [(
                        NodeGroupRef::new(&groups::TEXTURE, "?"),
                        InputLink::Input(Ref::new("3", "?")),
                    )]
                    .into(),
                    properties: BTreeMap::new(),
                },
            ),
            (
                "1",
                Input {
                    id: "1",
                    pipeline: Vec::new(),
                    links: [(
                        NodeGroupRef::new(&groups::TEXTURE, "?"),
                        InputLink::Value(Value::Bool(false)),
                    )]
                    .into(),
                    properties: BTreeMap::new(),
                },
            ),
            (
                "2",
                Input {
                    id: "2",
                    pipeline: Vec::new(),
                    links: [(
                        NodeGroupRef::new(&groups::TEXTURE, "?"),
                        InputLink::Input(Ref::new("1", "?")),
                    )]
                    .into(),
                    properties: BTreeMap::new(),
                },
            ),
            (
                "3",
                Input {
                    id: "3",
                    pipeline: Vec::new(),
                    links: [(
                        NodeGroupRef::new(&groups::TEXTURE, "?"),
                        InputLink::Input(Ref::new("1", "?")),
                    )]
                    .into(),
                    properties: BTreeMap::new(),
                },
            ),
        ]
        .into();

        let i0 = inputs.get("0").unwrap();
        let i1 = inputs.get("1").unwrap();
        let i2 = inputs.get("2").unwrap();
        let i3 = inputs.get("3").unwrap();

        let result = topological_sort_inputs(&inputs).unwrap();

        assert!(
            result.iter().position(|&r| ptr::eq(r, i0)).unwrap()
                > result.iter().position(|&r| ptr::eq(r, i3)).unwrap()
        );

        assert!(
            result.iter().position(|&r| ptr::eq(r, i2)).unwrap()
                > result.iter().position(|&r| ptr::eq(r, i1)).unwrap()
        );

        assert!(
            result.iter().position(|&r| ptr::eq(r, i3)).unwrap()
                > result.iter().position(|&r| ptr::eq(r, i1)).unwrap()
        );
    }
}
