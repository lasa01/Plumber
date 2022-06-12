#![deny(clippy::all, clippy::pedantic, clippy::multiple_crate_versions)]
// these are triggered by pyo3
#![allow(clippy::used_underscore_binding)]
#![allow(clippy::needless_option_as_deref)]
// this doesn't matter
#![allow(clippy::cast_precision_loss)]
// this is annoying
#![allow(clippy::module_name_repetitions)]

mod asset;
mod filesystem;
mod importer;

use std::io::Write;

use asset::model::PyBoneRestData;
use filesystem::{PyFileBrowser, PyFileBrowserEntry, PyFileSystem};

use log::{error, info, LevelFilter};
use pyo3::prelude::*;

use crate::{
    asset::{
        brush::{PyBuiltBrushEntity, PyBuiltSolid, PyMergedSolids},
        entities::{PyEnvLight, PyLight, PyLoadedProp, PySkyCamera, PySpotLight},
        material::{
            BuiltMaterialData, BuiltNode, BuiltNodeSocketRef, Material, Texture, TextureRef,
        },
        model::{
            PyBoneAnimationData, PyLoadedAnimation, PyLoadedBone, PyLoadedMesh, PyModel,
            QuaternionData, VectorData,
        },
        overlay::PyBuiltOverlay,
        sky::PySkyEqui,
    },
    importer::PyImporter,
};

#[pymodule]
fn plumber(_py: Python, m: &PyModule) -> PyResult<()> {
    m.add_class::<PyFileSystem>()?;
    m.add_class::<PyFileBrowser>()?;
    m.add_class::<PyFileBrowserEntry>()?;
    m.add_class::<PySkyEqui>()?;
    m.add_class::<Texture>()?;
    m.add_class::<Material>()?;
    m.add_class::<BuiltMaterialData>()?;
    m.add_class::<BuiltNode>()?;
    m.add_class::<BuiltNodeSocketRef>()?;
    m.add_class::<TextureRef>()?;
    m.add_class::<QuaternionData>()?;
    m.add_class::<VectorData>()?;
    m.add_class::<PyBoneAnimationData>()?;
    m.add_class::<PyBoneRestData>()?;
    m.add_class::<PyLoadedAnimation>()?;
    m.add_class::<PyLoadedBone>()?;
    m.add_class::<PyLoadedMesh>()?;
    m.add_class::<PyModel>()?;
    m.add_class::<PyMergedSolids>()?;
    m.add_class::<PyBuiltSolid>()?;
    m.add_class::<PyBuiltBrushEntity>()?;
    m.add_class::<PyBuiltOverlay>()?;
    m.add_class::<PyLoadedProp>()?;
    m.add_class::<PyLight>()?;
    m.add_class::<PySpotLight>()?;
    m.add_class::<PyEnvLight>()?;
    m.add_class::<PySkyCamera>()?;
    m.add_class::<PyImporter>()?;

    #[pyfn(m)]
    fn discover_filesystems() -> Vec<PyFileSystem> {
        filesystem::discover()
    }

    #[pyfn(m)]
    fn log_error(error: &str) {
        error!("{}", error);
    }

    #[pyfn(m)]
    fn log_info(info: &str) {
        info!("{}", info);
    }

    initialize_logger();

    Ok(())
}

fn initialize_logger() {
    let _ = env_logger::Builder::new()
        .format(|buf, record| writeln!(buf, "[Plumber] [{}] {}", record.level(), record.args()))
        .filter_level(LevelFilter::Debug)
        .try_init();
}