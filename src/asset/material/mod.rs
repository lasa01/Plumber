use std::io::Cursor;

use image::ImageOutputFormat;
use pyo3::{exceptions::PyRuntimeError, prelude::*};

use plumber_core::asset::vmt::{LoadedMaterial, LoadedTexture};

pub use builder::{build_material, Settings, TextureInterpolation};
pub use builder_base::BuiltMaterialData;
pub use nodes::{BuiltNode, BuiltNodeSocketRef, TextureRef};

mod builder;
mod builder_base;
mod definitions;
mod nodes;

#[pyclass(module = "plumber")]
pub struct Texture {
    name: String,
    width: u32,
    height: u32,
    data: Vec<u8>,
}

#[pymethods]
impl Texture {
    fn name(&self) -> &str {
        &self.name
    }

    fn width(&self) -> u32 {
        self.width
    }

    fn height(&self) -> u32 {
        self.height
    }

    fn bytes_tga(&self) -> &[u8] {
        &self.data
    }
}

impl Texture {
    pub fn new(texture: LoadedTexture) -> Self {
        let width = texture.data.width();
        let height = texture.data.height();

        let mut data = Vec::new();
        texture
            .data
            .write_to(&mut Cursor::new(&mut data), ImageOutputFormat::Tga)
            .unwrap();

        Self {
            name: texture.name.into_string(),
            width,
            height,
            data,
        }
    }
}

#[pyclass(module = "plumber")]
pub struct Material {
    name: String,
    data: Option<BuiltMaterialData>,
}

#[pymethods]
impl Material {
    fn name(&self) -> &str {
        &self.name
    }

    fn data(&mut self) -> PyResult<BuiltMaterialData> {
        self.data
            .take()
            .ok_or_else(|| PyRuntimeError::new_err("material data already consumed"))
    }
}

impl Material {
    pub fn new(material: LoadedMaterial<BuiltMaterialData>) -> Self {
        Self {
            name: material.name.into_string(),
            data: Some(material.data),
        }
    }
}
