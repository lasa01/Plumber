use std::{
    collections::{BTreeMap, BTreeSet},
    mem,
};

use glam::{Affine3A, EulerRot, Quat, Vec3};
use log::warn;
use pyo3::{prelude::*, types::PyList};

use plumber_core::{
    fs::GamePathBuf,
    model::{
        self,
        loader::{LoadedAnimation, LoadedBone, LoadedMesh, LoadedModel},
        AnimationData, AnimationDescFlags, BoneAnimationData,
    },
};

#[pyclass(module = "plumber", name = "Model")]
pub struct PyModel {
    name: String,
    meshes: Vec<PyLoadedMesh>,
    materials: Vec<Option<String>>,
    bones: Vec<PyLoadedBone>,
    animations: Vec<PyLoadedAnimation>,
    rest_positions: BTreeMap<usize, PyBoneRestData>,
}

#[pymethods]
impl PyModel {
    fn name(&self) -> &str {
        &self.name
    }

    fn meshes(&mut self) -> Vec<PyLoadedMesh> {
        mem::take(&mut self.meshes)
    }

    fn materials(&mut self) -> Vec<Option<String>> {
        mem::take(&mut self.materials)
    }

    fn bones(&mut self) -> Vec<PyLoadedBone> {
        mem::take(&mut self.bones)
    }

    fn animations(&mut self) -> Vec<PyLoadedAnimation> {
        mem::take(&mut self.animations)
    }

    fn rest_positions(&mut self) -> BTreeMap<usize, PyBoneRestData> {
        mem::take(&mut self.rest_positions)
    }
}

impl PyModel {
    pub fn new(m: LoadedModel, target_fps: f32, remove_animations: bool) -> Self {
        let bones = if m.info.static_prop {
            Vec::new()
        } else {
            m.bones.into_iter().map(PyLoadedBone::new).collect()
        };

        let animations;
        let rest_positions;

        if remove_animations {
            if let Some(animation) = m.animations.first() {
                rest_positions = apply_animation_first_frame(animation, &bones);
            } else {
                rest_positions = BTreeMap::new();
            }

            animations = Vec::new();
        } else {
            animations = m
                .animations
                .into_iter()
                .filter_map(|a| PyLoadedAnimation::new(a, &bones, target_fps))
                .collect();

            rest_positions = BTreeMap::new();
        };

        let mut meshes: Vec<_> = m.meshes.into_iter().map(PyLoadedMesh::new).collect();

        let mut used_mesh_names = BTreeSet::new();

        for mesh in &mut meshes {
            // prevent duplicate names
            if used_mesh_names.contains(&mesh.name) {
                let mut counter = 1;
                mesh.name.push_str(".1");

                while used_mesh_names.contains(&mesh.name) {
                    counter += 1;

                    if let Some(c) = char::from_digit(counter, 10) {
                        mesh.name.pop();
                        mesh.name.push(c);
                    } else {
                        // could not find unique name here,
                        // highly unlikely that a model has over 10 meshes with the same name...
                        warn!("model `{}`: too many meshes with the same name", m.name);
                        break;
                    }
                }
            } else {
                used_mesh_names.insert(&mesh.name);
            }
        }

        Self {
            name: m.name.into_string(),
            meshes,
            materials: m
                .materials
                .into_iter()
                .map(|mat| mat.map(GamePathBuf::into_string))
                .collect(),
            bones,
            animations,
            rest_positions,
        }
    }
}

fn apply_animation_first_frame(
    animation: &LoadedAnimation,
    bones: &[PyLoadedBone],
) -> BTreeMap<usize, PyBoneRestData> {
    if let Some(data) = &animation.data {
        let mut output = BTreeMap::new();

        for (&bone, data) in data {
            let position = match &data.position {
                AnimationData::Constant(pos) => pos.to_array(),
                AnimationData::Animated(vec) => {
                    vec.first().map_or(bones[bone].position, Vec3::to_array)
                }
                AnimationData::None => bones[bone].position,
            };

            let rotation = match &data.rotation {
                AnimationData::Constant(rot) => rot_to_euler(rot),
                AnimationData::Animated(vec) => {
                    vec.first().map_or(bones[bone].rotation, rot_to_euler)
                }
                AnimationData::None => bones[bone].rotation,
            };

            output.insert(bone, PyBoneRestData { rotation, position });
        }

        output
    } else {
        BTreeMap::new()
    }
}

fn rot_to_euler(rot: &Quat) -> [f32; 3] {
    let (z, y, x) = rot.to_euler(EulerRot::ZYX);
    [x, y, z]
}

#[pyclass(module = "plumber", name = "LoadedMesh")]
pub struct PyLoadedMesh {
    name: String,
    vertices: Vec<model::Vertex>,
    faces: Vec<model::Face>,
    flat_vertices: Vec<f32>,
    flat_polygon_vertice_indices: Vec<usize>,
    flat_loop_uvs: Vec<f32>,
    weight_groups: BTreeMap<u8, BTreeMap<usize, f32>>,
}

#[pymethods]
impl PyLoadedMesh {
    fn name(&self) -> &str {
        &self.name
    }

    fn vertices(&mut self) -> Vec<f32> {
        mem::take(&mut self.flat_vertices)
    }

    fn loops_len(&self) -> usize {
        self.faces.len() * 3
    }

    fn polygons_len(&self) -> usize {
        self.faces.len()
    }

    fn polygon_loop_totals<'p>(&self, py: Python<'p>) -> &'p PyList {
        PyList::new(py, itertools::repeat_n(3, self.faces.len()))
    }

    fn polygon_loop_starts<'p>(&self, py: Python<'p>) -> &'p PyList {
        PyList::new(py, (0..self.faces.len()).map(|i| i * 3))
    }

    fn polygon_vertices(&mut self) -> Vec<usize> {
        mem::take(&mut self.flat_polygon_vertice_indices)
    }

    fn polygon_material_indices<'p>(&self, py: Python<'p>) -> &'p PyList {
        PyList::new(py, self.faces.iter().map(|f| f.material_index))
    }

    fn loop_uvs(&mut self) -> Vec<f32> {
        mem::take(&mut self.flat_loop_uvs)
    }

    fn normals<'p>(&mut self, py: Python<'p>) -> &'p PyList {
        PyList::new(py, self.vertices.iter().map(|v| v.normal.as_ref()))
    }

    fn weight_groups(&mut self) -> BTreeMap<u8, BTreeMap<usize, f32>> {
        mem::take(&mut self.weight_groups)
    }
}

impl PyLoadedMesh {
    fn new(mesh: LoadedMesh) -> Self {
        let flat_vertices = mesh.vertices.iter().flat_map(|v| v.position).collect();

        let flat_polygon_vertice_indices = mesh
            .faces
            .iter()
            // face vertices in Blender are in opposite winding order compared to Source
            .flat_map(|f| f.vertice_indices.iter().rev())
            .copied()
            .collect();

        let flat_loop_uvs = mesh
            .faces
            .iter()
            .flat_map(|f| {
                f.vertice_indices.iter().rev().flat_map(|&i| {
                    let uv = mesh.vertices[i].tex_coord;
                    [uv[0], 1.0 - uv[1]]
                })
            })
            .collect();

        let mut weight_groups: BTreeMap<u8, BTreeMap<usize, f32>> = BTreeMap::new();

        for (vertex_index, vertex) in mesh.vertices.iter().enumerate() {
            let bone_count = vertex.bone_weight.bone_count.min(3);
            for i in 0..bone_count {
                let bone_index = vertex.bone_weight.bones[i as usize];
                let weight = vertex.bone_weight.weights[i as usize];

                weight_groups
                    .entry(bone_index)
                    .or_default()
                    .insert(vertex_index, weight);
            }
        }

        let name = if mesh.name.is_empty() {
            mesh.body_part_name
        } else {
            mesh.name
        };

        Self {
            name,
            vertices: mesh.vertices,
            faces: mesh.faces,
            flat_vertices,
            flat_polygon_vertice_indices,
            flat_loop_uvs,
            weight_groups,
        }
    }
}

#[derive(Default)]
#[pyclass(module = "plumber", name = "QuaternionData")]
pub struct QuaternionData {
    flat_x_points: Vec<f32>,
    flat_y_points: Vec<f32>,
    flat_z_points: Vec<f32>,
    flat_w_points: Vec<f32>,
}

#[pymethods]
impl QuaternionData {
    fn x_points(&mut self) -> Vec<f32> {
        mem::take(&mut self.flat_x_points)
    }

    fn y_points(&mut self) -> Vec<f32> {
        mem::take(&mut self.flat_y_points)
    }

    fn z_points(&mut self) -> Vec<f32> {
        mem::take(&mut self.flat_z_points)
    }

    fn w_points(&mut self) -> Vec<f32> {
        mem::take(&mut self.flat_w_points)
    }
}

impl QuaternionData {
    #[allow(clippy::similar_names)]
    fn new(quats: &[Quat], time_factor: f32) -> Self {
        let flat_x_points = quats
            .iter()
            .enumerate()
            .flat_map(|(i, v)| [(i as f32 * time_factor) + 1.0, v.x])
            .collect();

        let flat_y_points = quats
            .iter()
            .enumerate()
            .flat_map(|(i, v)| [(i as f32 * time_factor) + 1.0, v.y])
            .collect();

        let flat_z_points = quats
            .iter()
            .enumerate()
            .flat_map(|(i, v)| [(i as f32 * time_factor) + 1.0, v.z])
            .collect();

        let flat_w_points = quats
            .iter()
            .enumerate()
            .flat_map(|(i, v)| [(i as f32 * time_factor) + 1.0, v.w])
            .collect();

        Self {
            flat_x_points,
            flat_y_points,
            flat_z_points,
            flat_w_points,
        }
    }
}

#[derive(Default)]
#[pyclass(module = "plumber", name = "VectorData")]
pub struct VectorData {
    flat_x_points: Vec<f32>,
    flat_y_points: Vec<f32>,
    flat_z_points: Vec<f32>,
}

#[pymethods]
impl VectorData {
    fn x_points(&mut self) -> Vec<f32> {
        mem::take(&mut self.flat_x_points)
    }

    fn y_points(&mut self) -> Vec<f32> {
        mem::take(&mut self.flat_y_points)
    }

    fn z_points(&mut self) -> Vec<f32> {
        mem::take(&mut self.flat_z_points)
    }
}

impl VectorData {
    #[allow(clippy::similar_names)]
    fn new(vecs: &[Vec3], time_factor: f32) -> Self {
        let flat_x_points = vecs
            .iter()
            .enumerate()
            .flat_map(|(i, v)| [(i as f32 * time_factor) + 1.0, v.x])
            .collect();

        let flat_y_points = vecs
            .iter()
            .enumerate()
            .flat_map(|(i, v)| [(i as f32 * time_factor) + 1.0, v.y])
            .collect();

        let flat_z_points = vecs
            .iter()
            .enumerate()
            .flat_map(|(i, v)| [(i as f32 * time_factor) + 1.0, v.z])
            .collect();

        Self {
            flat_x_points,
            flat_y_points,
            flat_z_points,
        }
    }
}

enum PyAnimationRotationData {
    Constant([f32; 4]),
    Animated(QuaternionData),
    None,
}

enum PyAnimationPositionData {
    Constant([f32; 3]),
    Animated(VectorData),
    None,
}

#[pyclass(module = "plumber", name = "BoneAnimationData")]
pub struct PyBoneAnimationData {
    rotation: PyAnimationRotationData,
    position: PyAnimationPositionData,
}

impl PyBoneAnimationData {
    fn new(mut data: BoneAnimationData, bone: &PyLoadedBone, time_factor: f32) -> Self {
        // Animations in MDL replace the bone's initial position and rotation.
        // In Blender, animations are applied on top of the bone's initial position and rotation.
        //
        // Therefore, we need to modify the animation data such that it represents
        // the difference from the bone's initial transformation, not the absolute transformation.

        let rotation = match &mut data.rotation {
            AnimationData::Constant(quaternion) => {
                rotation_to_delta(quaternion, bone);
                PyAnimationRotationData::Constant((*quaternion).into())
            }
            AnimationData::Animated(quaternions) => {
                for quaternion in &mut *quaternions {
                    rotation_to_delta(quaternion, bone);
                }
                PyAnimationRotationData::Animated(QuaternionData::new(quaternions, time_factor))
            }
            AnimationData::None => PyAnimationRotationData::None,
        };

        let position = match &mut data.position {
            AnimationData::Constant(position) => {
                position_to_delta(position, bone);
                PyAnimationPositionData::Constant((*position).into())
            }
            AnimationData::Animated(positions) => {
                for position in &mut *positions {
                    position_to_delta(position, bone);
                }
                PyAnimationPositionData::Animated(VectorData::new(positions, time_factor))
            }
            AnimationData::None => PyAnimationPositionData::None,
        };

        Self { rotation, position }
    }
}

fn rotation_to_delta(quaternion: &mut Quat, bone: &PyLoadedBone) {
    let bone_quaternion = Quat::from_euler(
        EulerRot::ZYX,
        bone.rotation[2],
        bone.rotation[1],
        bone.rotation[0],
    );
    *quaternion = bone_quaternion.inverse() * *quaternion;
}

fn position_to_delta(position: &mut Vec3, bone: &PyLoadedBone) {
    let bone_quaternion = Quat::from_euler(
        EulerRot::ZYX,
        bone.rotation[2],
        bone.rotation[1],
        bone.rotation[0],
    );

    let bone_matrix = Affine3A::from_rotation_translation(bone_quaternion, bone.position.into());

    *position = bone_matrix.inverse().transform_point3(*position);
}

#[pymethods]
impl PyBoneAnimationData {
    fn rotation(&mut self, py: Python) -> PyObject {
        match &mut self.rotation {
            PyAnimationRotationData::Constant(quat) => (*quat).into_py(py),
            PyAnimationRotationData::Animated(values) => mem::take(values).into_py(py),
            PyAnimationRotationData::None => ().into_py(py),
        }
    }

    fn position(&mut self, py: Python) -> PyObject {
        match &mut self.position {
            PyAnimationPositionData::Constant(vec) => (*vec).into_py(py),
            PyAnimationPositionData::Animated(values) => mem::take(values).into_py(py),
            PyAnimationPositionData::None => ().into_py(py),
        }
    }
}

#[pyclass(module = "plumber", name = "LoadedBone")]
pub struct PyLoadedBone {
    name: String,
    parent_bone_index: Option<usize>,
    position: [f32; 3],
    rotation: [f32; 3],
}

impl PyLoadedBone {
    fn new(bone: LoadedBone) -> Self {
        Self {
            name: bone.name,
            parent_bone_index: bone.parent_bone_index,
            position: bone.position,
            rotation: bone.rotation,
        }
    }
}

#[pymethods]
impl PyLoadedBone {
    fn name(&self) -> &str {
        &self.name
    }

    fn parent_bone_index(&self) -> Option<usize> {
        self.parent_bone_index
    }

    fn position(&self) -> [f32; 3] {
        self.position
    }

    fn rotation(&self) -> [f32; 3] {
        self.rotation
    }
}

#[pyclass(module = "plumber", name = "LoadedAnimation")]
pub struct PyLoadedAnimation {
    name: String,
    data: BTreeMap<usize, PyBoneAnimationData>,
    looping: bool,
}

impl PyLoadedAnimation {
    fn new(animation: LoadedAnimation, bones: &[PyLoadedBone], target_fps: f32) -> Option<Self> {
        let data = animation.data?;

        let time_factor = target_fps / animation.fps;

        Some(Self {
            name: animation.name,
            data: data
                .into_iter()
                .map(|(i, data)| (i, PyBoneAnimationData::new(data, &bones[i], time_factor)))
                .collect(),
            looping: animation.flags.contains(AnimationDescFlags::LOOPING),
        })
    }
}

#[pymethods]
impl PyLoadedAnimation {
    fn name(&self) -> &str {
        &self.name
    }

    fn data(&mut self) -> BTreeMap<usize, PyBoneAnimationData> {
        mem::take(&mut self.data)
    }

    fn looping(&self) -> bool {
        self.looping
    }
}

#[pyclass(module = "plumber", name = "BoneRestData")]
pub struct PyBoneRestData {
    rotation: [f32; 3],
    position: [f32; 3],
}

#[pymethods]
impl PyBoneRestData {
    fn rotation(&self) -> [f32; 3] {
        self.rotation
    }

    fn position(&self) -> [f32; 3] {
        self.position
    }
}
