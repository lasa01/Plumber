use std::{
    fmt::{self, Debug, Formatter},
    io::Cursor,
    panic::{catch_unwind, AssertUnwindSafe},
};

use pyo3::{exceptions::PyRuntimeError, prelude::*};

use plumber_core::{
    asset_core::{CachedAssetConfig, Context},
    asset_vmt::{VmtConfig, VmtError, VmtErrorInner, VmtHelper},
    asset_vtf::LoadedVtf,
    fs::PathBuf,
    vmt::MaterialInfo,
};

pub use builder::{build_material, Settings, TextureFormat, TextureInterpolation};
pub use builder_base::BuiltMaterialData;
pub use nodes::{BuiltNode, BuiltNodeSocketRef, TextureRef};

use super::BlenderAssetHandler;

mod builder;
mod builder_base;
mod definitions;
mod nodes;

#[pyclass(module = "plumber")]
pub struct Texture {
    pub name: String,
    width: u32,
    height: u32,
    data: Vec<u8>,
    format: TextureFormat,
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

    fn format_ext(&self) -> &'static str {
        self.format.to_ext_str()
    }

    fn bytes(&self) -> &[u8] {
        &self.data
    }
}

impl Texture {
    pub fn new(texture: &LoadedVtf, format: TextureFormat) -> Self {
        let width = texture.data.width();
        let height = texture.data.height();

        let mut data = Vec::new();
        texture
            .data
            .write_to(&mut Cursor::new(&mut data), format.to_output_format())
            .unwrap();

        Self {
            name: texture.name.to_string(),
            width,
            height,
            format,
            data,
        }
    }
}

#[pyclass(module = "plumber")]
pub struct Material {
    pub name: String,
    data: Option<BuiltMaterialData>,
    texture_format: TextureFormat,
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

    fn texture_ext(&self) -> &str {
        self.texture_format.to_ext_str()
    }
}

impl Material {
    pub fn new(name: &PathBuf, data: BuiltMaterialData, texture_format: TextureFormat) -> Self {
        Self {
            name: name.to_string(),
            data: Some(data),
            texture_format,
        }
    }
}

#[derive(Clone, Copy)]
pub struct MaterialConfig {
    pub settings: Settings,
}

impl Debug for MaterialConfig {
    fn fmt(&self, f: &mut Formatter<'_>) -> fmt::Result {
        f.write_str("MaterialConfig")
    }
}

impl VmtConfig<BlenderAssetHandler> for MaterialConfig {}

impl CachedAssetConfig<BlenderAssetHandler> for MaterialConfig {
    type Input<'a> = PathBuf;
    type Id = PathBuf;
    type Output<'a> = (PathBuf, Option<BuiltMaterialData>);
    type CachedOutput = MaterialInfo;
    type Error = VmtError;

    fn cache_id(self, input: &Self::Input<'_>) -> Self::Id {
        let mut input = input.clone();
        input.normalize_extension();
        input
    }

    fn process<'a>(
        self,
        mut input: Self::Input<'a>,
        context: &mut Context<BlenderAssetHandler>,
    ) -> Result<(Self::Output<'a>, Self::CachedOutput), Self::Error> {
        input.normalize_extension();

        let vmt_helper = VmtHelper::new(&input, context.fs())?;
        let info = vmt_helper.get_info(context.fs())?;

        let built = catch_unwind(AssertUnwindSafe(|| {
            build_material(context, &vmt_helper, &info, self.settings)
        }))
        .map_err(|e| {
            let error = if let Some(s) = e.downcast_ref::<&'static str>() {
                VmtErrorInner::Custom(s)
            } else {
                VmtErrorInner::Custom("internal error loading material")
            };

            VmtError {
                path: input.clone(),
                error,
            }
        })?;

        Ok(((input, built), info))
    }
}
