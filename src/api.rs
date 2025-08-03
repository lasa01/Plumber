use std::{path::PathBuf as StdPathBuf, time::Instant};

use crossbeam_channel::Receiver;
use pyo3::{
    exceptions::{PyIOError, PyRuntimeError},
    prelude::*,
    types::PyDict,
};
use tracing::{debug_span, error, info};

use plumber_core::{
    asset_core::{AssetConfig, Context, Executor, NoError},
    asset_mdl::MdlConfig,
    asset_vmf::{BrushSetting, VmfConfig},
    asset_vtf::VtfConfig,
    fs::{GamePathBuf, PathBuf},
    vmf::{
        builder::{GeometrySettings, InvisibleSolids, MergeSolids},
        vmf::Vmf,
    },
};

use crate::{
    asset::{material::MaterialConfig, BlenderAssetHandler, Message},
    filesystem::PyFileSystem,
    importer::PyImporter,
};

/// Unified asset config that can process mixed asset types
#[derive(Debug, Clone, Copy)]
pub struct UnifiedAssetConfig {
    pub material_config: MaterialConfig,
}

impl AssetConfig<BlenderAssetHandler> for UnifiedAssetConfig {
    type Input<'a> = AssetImportJob;
    type Output<'a> = ();
    type Error<'a> = NoError;

    fn process<'a>(
        self,
        input: Self::Input<'a>,
        context: &mut Context<BlenderAssetHandler>,
    ) -> Result<Self::Output<'a>, Self::Error<'a>> {
        match input {
            AssetImportJob::Vtf { path } => {
                context.queue(VtfConfig, path);
            }
            AssetImportJob::Vmt { path } => {
                context.queue(self.material_config, path);
            }
            AssetImportJob::Mdl { path, config } => {
                context.queue(config, path);
            }
            AssetImportJob::Vmf { path, config } => {
                // VMF files need special handling - read and parse first
                if let Ok(bytes) = context.fs().read(&path) {
                    if let Ok(vmf) = Vmf::from_bytes(&bytes) {
                        context.queue(config, vmf);
                    } else {
                        error!("Failed to parse VMF file: {}", path);
                    }
                } else {
                    error!("Failed to read VMF file: {}", path);
                }
            }
        }
        Ok(())
    }
}

/// Enum representing different types of assets that can be imported
#[derive(Debug, Clone)]
pub enum AssetImportJob {
    Vmf {
        path: PathBuf,
        config: VmfConfig<MaterialConfig>,
    },
    Mdl {
        path: PathBuf,
        config: MdlConfig<MaterialConfig>,
    },
    Vmt {
        path: PathBuf,
    },
    Vtf {
        path: PathBuf,
    },
}

/// Python wrapper for parallel import builder
#[pyclass(module = "plumber", name = "ApiImporter")]
pub struct PyApiImporter {
    material_config: MaterialConfig,
    executor: Option<Executor<BlenderAssetHandler>>,
    receiver: Receiver<Message>,
    jobs: Vec<AssetImportJob>,
    callback_obj: PyObject,
    // VMF-specific settings
    vmf_import_brushes: bool,
    vmf_import_overlays: bool,
    vmf_epsilon: f32,
    vmf_cut_threshold: f32,
    vmf_merge_solids: MergeSolids,
    vmf_invisible_solids: InvisibleSolids,
    vmf_import_props: bool,
    vmf_import_entities: bool,
    vmf_import_sky: bool,
    vmf_scale: f32,
    // MDL-specific settings
    mdl_import_animations: bool,
}

#[pymethods]
impl PyApiImporter {
    #[new]
    #[args(file_system, callback_obj, threads_suggestion, kwargs = "**")]
    fn new(
        file_system: &PyFileSystem,
        callback_obj: PyObject,
        threads_suggestion: usize,
        kwargs: Option<&PyDict>,
    ) -> PyResult<Self> {
        let start = Instant::now();
        info!(
            "opening file system of game `{}` for API import...",
            file_system.file_system.name
        );

        let opened = file_system
            .file_system
            .open()
            .map_err(|e| PyIOError::new_err(e.to_string()))?;

        info!(
            "file system opened in {:.2} s",
            start.elapsed().as_secs_f32()
        );

        // Extract all settings using the shared extraction methods
        let settings = PyImporter::extract_api_importer_wide_settings(kwargs)?;
        let vmf_settings = PyImporter::extract_api_vmf_settings(kwargs)?;
        let mdl_import_animations = PyImporter::extract_api_mdl_settings(kwargs)?;

        let material_config = MaterialConfig {
            settings: settings.material,
        };

        let (sender, receiver) = crossbeam_channel::bounded(256);
        let handler = BlenderAssetHandler { sender, settings };
        let executor = Some(Executor::new_with_threads(
            handler,
            opened,
            threads_suggestion,
        ));

        Ok(Self {
            material_config,
            executor,
            receiver,
            jobs: Vec::new(),
            callback_obj,
            vmf_import_brushes: vmf_settings.import_brushes,
            vmf_import_overlays: vmf_settings.import_overlays,
            vmf_epsilon: vmf_settings.epsilon,
            vmf_cut_threshold: vmf_settings.cut_threshold,
            vmf_merge_solids: vmf_settings.merge_solids,
            vmf_invisible_solids: vmf_settings.invisible_solids,
            vmf_import_props: vmf_settings.import_props,
            vmf_import_entities: vmf_settings.import_other_entities,
            vmf_import_sky: vmf_settings.import_skybox,
            vmf_scale: vmf_settings.scale,
            mdl_import_animations,
        })
    }

    fn add_vmf_job(&mut self, path: &str, from_game: bool) -> PyResult<()> {
        let mut geometry_settings = GeometrySettings::default();
        geometry_settings.epsilon(self.vmf_epsilon);
        geometry_settings.cut_threshold(self.vmf_cut_threshold);
        geometry_settings.merge_solids(self.vmf_merge_solids);
        geometry_settings.invisible_solids(self.vmf_invisible_solids);

        let mut settings = VmfConfig::new(self.material_config);
        settings.import_overlays = self.vmf_import_overlays;
        settings.import_props = self.vmf_import_props;
        settings.import_other_entities = self.vmf_import_entities;
        settings.import_skybox = self.vmf_import_sky;
        settings.scale = self.vmf_scale;

        settings.brushes = if self.vmf_import_brushes {
            BrushSetting::Import(geometry_settings)
        } else {
            BrushSetting::Skip
        };

        let path: PathBuf = if from_game {
            GamePathBuf::from(path).into()
        } else {
            StdPathBuf::from(path).into()
        };

        self.jobs.push(AssetImportJob::Vmf {
            path,
            config: settings,
        });

        Ok(())
    }

    fn add_mdl_job(&mut self, path: &str, from_game: bool) -> PyResult<()> {
        let mut settings = MdlConfig::new(self.material_config);
        settings.import_animations = self.mdl_import_animations;

        let path = if from_game {
            GamePathBuf::from(path).into()
        } else {
            StdPathBuf::from(path).into()
        };

        self.jobs.push(AssetImportJob::Mdl {
            path,
            config: settings,
        });

        Ok(())
    }

    fn add_vmt_job(&mut self, path: &str, from_game: bool) -> PyResult<()> {
        let path = if from_game {
            GamePathBuf::from(path).into()
        } else {
            StdPathBuf::from(path).into()
        };

        self.jobs.push(AssetImportJob::Vmt { path });

        Ok(())
    }

    fn add_vtf_job(&mut self, path: &str, from_game: bool) -> PyResult<()> {
        let path = if from_game {
            GamePathBuf::from(path).into()
        } else {
            StdPathBuf::from(path).into()
        };

        self.jobs.push(AssetImportJob::Vtf { path });

        Ok(())
    }

    fn execute_jobs(&mut self, py: Python) -> PyResult<()> {
        if self.jobs.is_empty() {
            return Ok(());
        }

        let executor = self.consume()?;
        let start = Instant::now();
        info!("executing {} import jobs in parallel...", self.jobs.len());

        // Use single process_each call with unified config
        let unified_config = UnifiedAssetConfig {
            material_config: self.material_config,
        };

        let jobs: Vec<AssetImportJob> = self.jobs.drain(..).collect();
        executor.process_each(unified_config, jobs, || self.process_assets(py));

        info!("jobs executed in {:.2} s", start.elapsed().as_secs_f32());
        Ok(())
    }

    #[getter]
    fn job_count(&self) -> usize {
        self.jobs.len()
    }
}

impl PyApiImporter {
    fn consume(&mut self) -> PyResult<Executor<BlenderAssetHandler>> {
        self.executor
            .take()
            .ok_or_else(|| PyRuntimeError::new_err("Importer already consumed"))
    }

    fn process_assets(&self, py: Python) {
        let callback_ref = self.callback_obj.as_ref(py);

        for asset in &self.receiver {
            let kind = asset.kind();
            let id = asset.id();

            let _asset_span = debug_span!("asset", kind, %id).entered();

            let result = match asset {
                Message::Material(material) => callback_ref.call_method1("material", (material,)),
                Message::Texture(texture) => callback_ref.call_method1("texture", (texture,)),
                Message::Model(model) => callback_ref.call_method1("model", (model,)),
                Message::Brush(brush) => callback_ref.call_method1("brush", (brush,)),
                Message::Overlay(overlay) => callback_ref.call_method1("overlay", (overlay,)),
                Message::Prop(prop) => callback_ref.call_method1("prop", (prop,)),
                Message::Light(light) => callback_ref.call_method1("light", (light,)),
                Message::SpotLight(light) => callback_ref.call_method1("spot_light", (light,)),
                Message::EnvLight(light) => callback_ref.call_method1("env_light", (light,)),
                Message::SkyCamera(sky_camera) => {
                    callback_ref.call_method1("sky_camera", (sky_camera,))
                }
                Message::SkyEqui(sky_equi) => callback_ref.call_method1("sky_equi", (sky_equi,)),
                Message::UnknownEntity(entity) => {
                    callback_ref.call_method1("unknown_entity", (entity,))
                }
            };

            if let Err(err) = result {
                err.print(py);
                error!("Asset importing errored: {}", err);
            }
        }
    }
}
