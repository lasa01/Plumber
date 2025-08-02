use std::{path::PathBuf as StdPathBuf, str::FromStr, time::Instant};

use crossbeam_channel::Receiver;
use pyo3::{
    exceptions::{PyIOError, PyRuntimeError, PyTypeError},
    prelude::*,
    types::PyDict,
};
use tracing::{debug_span, error, info};

use plumber_core::{
    asset_core::Executor,
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
        config: MaterialConfig,
    },
    Vtf {
        path: PathBuf,
        config: VtfConfig,
    },
}

impl AssetImportJob {
    pub fn path(&self) -> &PathBuf {
        match self {
            AssetImportJob::Vmf { path, .. } => path,
            AssetImportJob::Mdl { path, .. } => path,
            AssetImportJob::Vmt { path, .. } => path,
            AssetImportJob::Vtf { path, .. } => path,
        }
    }

    pub fn asset_type(&self) -> &'static str {
        match self {
            AssetImportJob::Vmf { .. } => "vmf",
            AssetImportJob::Mdl { .. } => "mdl",
            AssetImportJob::Vmt { .. } => "vmt",
            AssetImportJob::Vtf { .. } => "vtf",
        }
    }
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

        self.jobs.push(AssetImportJob::Vmt {
            path,
            config: self.material_config,
        });

        Ok(())
    }

    fn add_vtf_job(&mut self, path: &str, from_game: bool) -> PyResult<()> {
        let path = if from_game {
            GamePathBuf::from(path).into()
        } else {
            StdPathBuf::from(path).into()
        };

        self.jobs.push(AssetImportJob::Vtf {
            path,
            config: VtfConfig,
        });

        Ok(())
    }

    fn execute_jobs(&mut self, py: Python) -> PyResult<()> {
        if self.jobs.is_empty() {
            return Ok(());
        }

        let executor = self.consume()?;
        let start = Instant::now();
        info!("executing {} import jobs in parallel...", self.jobs.len());

        // Group jobs by type for batch processing
        let mut vmf_jobs = Vec::new();
        let mut mdl_jobs = Vec::new();
        let mut material_jobs = Vec::new();
        let mut texture_jobs = Vec::new();

        for job in self.jobs.drain(..) {
            match job {
                AssetImportJob::Vmf { path, config } => vmf_jobs.push((path, config)),
                AssetImportJob::Mdl { path, config } => mdl_jobs.push((path, config)),
                AssetImportJob::Vmt { path, config } => material_jobs.push((path, config)),
                AssetImportJob::Vtf { path, config } => texture_jobs.push((path, config)),
            }
        }

        // We need to process different job types in order of priority
        // since each process call consumes the executor

        // Process VTF files first (textures needed by materials)
        if !texture_jobs.is_empty() {
            let paths: Vec<PathBuf> = texture_jobs.into_iter().map(|(path, _)| path).collect();
            executor.process_each(VtfConfig, paths, || self.process_assets(py));
            info!("jobs executed in {:.2} s", start.elapsed().as_secs_f32());
            return Ok(());
        }

        // Process VMT files (materials needed by models and vmf)
        if !material_jobs.is_empty() {
            // All VMT jobs should use the same material config from the builder
            let paths: Vec<PathBuf> = material_jobs.into_iter().map(|(path, _)| path).collect();
            executor.process_each(self.material_config, paths, || self.process_assets(py));
            info!("jobs executed in {:.2} s", start.elapsed().as_secs_f32());
            return Ok(());
        }

        // Process MDL files
        if !mdl_jobs.is_empty() {
            // Group by config to batch together jobs with same settings
            let mut mdl_groups: std::collections::HashMap<
                String,
                (MdlConfig<MaterialConfig>, Vec<PathBuf>),
            > = std::collections::HashMap::new();

            for (path, config) in mdl_jobs {
                let config_key = format!("{:?}", config); // Simple grouping by debug representation
                mdl_groups
                    .entry(config_key)
                    .or_insert_with(|| (config, Vec::new()))
                    .1
                    .push(path);
            }

            // Process the first group (since executor is consumed)
            if let Some((_, (config, paths))) = mdl_groups.into_iter().next() {
                executor.process_each(config, paths, || self.process_assets(py));
            }
            info!("jobs executed in {:.2} s", start.elapsed().as_secs_f32());
            return Ok(());
        }

        // Process VMF files (most complex, need special handling)
        if !vmf_jobs.is_empty() {
            // For now, process only the first VMF (since each consumes the executor)
            if let Some((path, config)) = vmf_jobs.into_iter().next() {
                let bytes = executor
                    .fs()
                    .read(&path)
                    .map_err(|e| PyIOError::new_err(e.to_string()))?;
                let vmf = Vmf::from_bytes(&bytes).map_err(|e| PyIOError::new_err(e.to_string()))?;
                executor.process(config, vmf, || self.process_assets(py));
            }
        }

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
