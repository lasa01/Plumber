use std::{path::PathBuf as StdPathBuf, str::FromStr, time::Instant};

use crossbeam_channel::Receiver;
use pyo3::{
    exceptions::{PyIOError, PyRuntimeError, PyTypeError},
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
    asset::{
        material::{MaterialConfig, TextureFormat, TextureInterpolation},
        BlenderAssetHandler, HandlerSettings, Message,
    },
    filesystem::PyFileSystem,
};

/// Enum representing different types of asset import jobs for unified processing
#[derive(Debug, Clone)]
pub enum UnifiedAssetJob {
    Vtf {
        path: PathBuf,
    },
    Vmt {
        path: PathBuf,
    },
    Mdl {
        path: PathBuf,
        config: MdlConfig<MaterialConfig>,
    },
    Vmf {
        path: PathBuf,
        config: VmfConfig<MaterialConfig>,
    },
}

/// Unified asset config that can process mixed asset types
#[derive(Debug, Clone, Copy)]
pub struct UnifiedAssetConfig {
    pub material_config: MaterialConfig,
}

impl AssetConfig<BlenderAssetHandler> for UnifiedAssetConfig {
    type Input<'a> = UnifiedAssetJob;
    type Output<'a> = ();
    type Error<'a> = NoError;

    fn process<'a>(
        self,
        input: Self::Input<'a>,
        context: &mut Context<BlenderAssetHandler>,
    ) -> Result<Self::Output<'a>, Self::Error<'a>> {
        match input {
            UnifiedAssetJob::Vtf { path } => {
                context.queue(VtfConfig, path);
            }
            UnifiedAssetJob::Vmt { path } => {
                context.queue(self.material_config, path);
            }
            UnifiedAssetJob::Mdl { path, config } => {
                context.queue(config, path);
            }
            UnifiedAssetJob::Vmf { path, config } => {
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

        let mut settings = HandlerSettings::default();

        if let Some(kwargs) = kwargs {
            for (key, value) in kwargs {
                if value.is_none() {
                    continue;
                }

                match key.extract()? {
                    "import_materials" => settings.material.import_materials = value.extract()?,
                    "import_lights" => settings.import_lights = value.extract()?,
                    "light_factor" => settings.light.light_factor = value.extract()?,
                    "sun_factor" => settings.light.sun_factor = value.extract()?,
                    "ambient_factor" => settings.light.ambient_factor = value.extract()?,
                    "import_sky_camera" => settings.import_sky_camera = value.extract()?,
                    "sky_equi_height" => settings.sky_equi_height = value.extract()?,
                    "scale" => settings.scale = value.extract()?,
                    "target_fps" => settings.target_fps = value.extract()?,
                    "remove_animations" => settings.remove_animations = value.extract()?,
                    "simple_materials" => settings.material.simple_materials = value.extract()?,
                    "allow_culling" => settings.material.allow_culling = value.extract()?,
                    "editor_materials" => settings.material.editor_materials = value.extract()?,
                    "texture_format" => {
                        settings.material.texture_format =
                            TextureFormat::from_str(value.extract()?)?;
                    }
                    "texture_interpolation" => {
                        settings.material.texture_interpolation =
                            TextureInterpolation::from_str(value.extract()?)?;
                    }
                    "import_unknown_entities" => {
                        settings.import_unknown_entities = value.extract()?;
                    }
                    _ => return Err(PyTypeError::new_err("unexpected kwarg")),
                }
            }
        }

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
        })
    }

    #[args(path, from_game, kwargs = "**")]
    fn add_vmf_job(
        &mut self,
        path: &str,
        from_game: bool,
        kwargs: Option<&PyDict>,
    ) -> PyResult<()> {
        let mut import_brushes = true;
        let mut geometry_settings = GeometrySettings::default();
        let mut settings = VmfConfig::new(self.material_config);

        if let Some(kwargs) = kwargs {
            for (key, value) in kwargs {
                match key.extract()? {
                    "import_brushes" => {
                        import_brushes = value.extract()?;
                    }
                    "import_overlays" => {
                        settings.import_overlays = value.extract()?;
                    }
                    "epsilon" => {
                        geometry_settings.epsilon(value.extract()?);
                    }
                    "cut_threshold" => {
                        geometry_settings.cut_threshold(value.extract()?);
                    }
                    "merge_solids" => match value.extract()? {
                        "MERGE" => geometry_settings.merge_solids(MergeSolids::Merge),
                        "SEPARATE" => geometry_settings.merge_solids(MergeSolids::Separate),
                        _ => return Err(PyTypeError::new_err("unexpected kwarg value")),
                    },
                    "invisible_solids" => match value.extract()? {
                        "IMPORT" => geometry_settings.invisible_solids(InvisibleSolids::Import),
                        "SKIP" => geometry_settings.invisible_solids(InvisibleSolids::Skip),
                        _ => return Err(PyTypeError::new_err("unexpected kwarg value")),
                    },
                    "import_props" => {
                        settings.import_props = value.extract()?;
                    }
                    "import_entities" => {
                        settings.import_other_entities = value.extract()?;
                    }
                    "import_sky" => {
                        settings.import_skybox = value.extract()?;
                    }
                    "scale" => {
                        settings.scale = value.extract()?;
                    }
                    _ => return Err(PyTypeError::new_err("unexpected kwarg")),
                }
            }
        }

        settings.brushes = if import_brushes {
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

    #[args(path, from_game, kwargs = "**")]
    fn add_mdl_job(
        &mut self,
        path: &str,
        from_game: bool,
        kwargs: Option<&PyDict>,
    ) -> PyResult<()> {
        let settings = self.mdl_settings(kwargs)?;

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

        // Convert jobs to unified format
        let unified_jobs: Vec<UnifiedAssetJob> = self
            .jobs
            .drain(..)
            .map(|job| match job {
                AssetImportJob::Vtf { path } => UnifiedAssetJob::Vtf { path },
                AssetImportJob::Vmt { path } => UnifiedAssetJob::Vmt { path },
                AssetImportJob::Mdl { path, config } => UnifiedAssetJob::Mdl { path, config },
                AssetImportJob::Vmf { path, config } => UnifiedAssetJob::Vmf { path, config },
            })
            .collect();

        // Use single process_each call with unified config
        let unified_config = UnifiedAssetConfig {
            material_config: self.material_config,
        };

        executor.process_each(unified_config, unified_jobs, || self.process_assets(py));

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

    fn mdl_settings(&self, kwargs: Option<&PyDict>) -> PyResult<MdlConfig<MaterialConfig>> {
        let mut settings = MdlConfig::new(self.material_config);

        if let Some(kwargs) = kwargs {
            for (key, value) in kwargs {
                match key.extract()? {
                    "import_animations" => settings.import_animations = value.extract()?,
                    _ => return Err(PyTypeError::new_err("unexpected kwarg")),
                }
            }
        }

        Ok(settings)
    }
}
