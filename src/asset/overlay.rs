use std::mem;

use glam::Vec3;
use plumber_core::vmf::{
    builder::{BuiltOverlay, BuiltOverlayFace},
    entities::BaseEntity,
};
use pyo3::{prelude::*, types::PyList};

#[pyclass(module = "plumber", name = "BuiltOverlay")]
pub struct PyBuiltOverlay {
    pub id: i32,
    position: [f32; 3],
    scale: [f32; 3],
    faces: Vec<BuiltOverlayFace>,
    material: String,
    flat_vertices: Vec<f32>,
    flat_polygon_vertice_indices: Vec<usize>,
    flat_loop_uvs: Vec<f32>,
}

#[pymethods]
impl PyBuiltOverlay {
    fn id(&self) -> i32 {
        self.id
    }

    fn position(&self) -> [f32; 3] {
        self.position
    }

    fn scale(&self) -> [f32; 3] {
        self.scale
    }

    fn vertices(&mut self) -> Vec<f32> {
        mem::take(&mut self.flat_vertices)
    }

    fn loops_len(&self) -> usize {
        self.faces.iter().map(|f| f.vertice_indices.len()).sum()
    }

    fn polygons_len(&self) -> usize {
        self.faces.len()
    }

    fn polygon_loop_totals<'p>(&self, py: Python<'p>) -> &'p PyList {
        PyList::new(py, self.faces.iter().map(|f| f.vertice_indices.len()))
    }

    fn polygon_loop_starts<'p>(&self, py: Python<'p>) -> &'p PyList {
        let mut acc = 0;

        PyList::new(
            py,
            self.faces.iter().map(|f| {
                let acc_before = acc;
                acc += f.vertice_indices.len();
                acc_before
            }),
        )
    }

    fn polygon_vertices(&mut self) -> Vec<usize> {
        mem::take(&mut self.flat_polygon_vertice_indices)
    }

    fn loop_uvs(&mut self) -> Vec<f32> {
        mem::take(&mut self.flat_loop_uvs)
    }

    fn material(&self) -> &str {
        &self.material
    }
}

impl PyBuiltOverlay {
    pub fn new(overlay: BuiltOverlay) -> Self {
        let flat_vertices = overlay.vertices.iter().flat_map(Vec3::to_array).collect();

        let flat_polygon_vertice_indices = overlay
            .faces
            .iter()
            .flat_map(|f| &f.vertice_indices)
            .copied()
            .collect();

        let flat_loop_uvs = overlay
            .faces
            .iter()
            .flat_map(|f| {
                f.vertice_uvs
                    .iter()
                    // blender has inverted v axis compared to Source
                    .flat_map(|uv| [uv.x, 1.0 - uv.y])
            })
            .collect();

        Self {
            id: overlay.overlay.entity().id,
            position: overlay.position.into(),
            scale: [overlay.scale, overlay.scale, overlay.scale],
            faces: overlay.faces,
            material: overlay.material.into_string(),
            flat_vertices,
            flat_polygon_vertice_indices,
            flat_loop_uvs,
        }
    }
}
