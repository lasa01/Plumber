use std::{
    path::{Path as StdPath, PathBuf as StdPathBuf},
    str::FromStr,
    time::Instant,
};

use crossbeam_channel::Receiver;
use pyo3::{
    exceptions::{PyIOError, PyRuntimeError, PyTypeError},
    prelude::*,
    types::PyDict,
};
use tracing::{debug, debug_span, error, info};

use plumber_core::{
    asset_core::Executor,
    asset_mdl::MdlConfig,
    asset_vmf::{BrushSetting, VmfConfig},
    asset_vtf::VtfConfig,
    fs::{GamePathBuf, OpenFileSystem, OpenSearchPath, PathBuf},
    vmf::{
        builder::{GeometrySettings, InvisibleSolids, MergeSolids},
        vmf::Vmf,
    },
};

use crate::{
    asset::{
        material::{MaterialConfig, TextureInterpolation},
        BlenderAssetHandler, HandlerSettings, Message,
    },
    filesystem::PyFileSystem,
};

#[pyclass(module = "plumber", name = "Importer")]
pub struct PyImporter {
    material_config: MaterialConfig,
    executor: Option<Executor<BlenderAssetHandler>>,
    receiver: Receiver<Message>,
    callback_obj: PyObject,
}

#[pymethods]
impl PyImporter {
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
            "opening file system of game `{}`...",
            file_system.file_system.name
        );

        let mut opened = file_system
            .file_system
            .open()
            .map_err(|e| PyIOError::new_err(e.to_string()))?;

        info!(
            "file system opened in {:.2} s",
            start.elapsed().as_secs_f32()
        );

        let mut settings = HandlerSettings::default();

        if let Some(kwargs) = kwargs {
            for (key, value) in kwargs.iter() {
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
                    "texture_interpolation" => {
                        settings.material.texture_interpolation =
                            TextureInterpolation::from_str(value.extract()?)?;
                    }
                    "import_unknown_entities" => {
                        settings.import_unknown_entities = value.extract()?;
                    }
                    "vmf_path" => {
                        // Map data path is detected here since when opening a vmf
                        // from game files, it needs to be determined after
                        // opening the filesystem to know where the vmf file actually is.
                        // On the other hand, it needs to be done before passing the file system
                        // to the importer.

                        let file_path_string: &str = value.extract()?;
                        detect_embedded_files_path(file_path_string, &mut opened);
                    }
                    "map_data_path" => {
                        let map_data_path: &str = value.extract()?;
                        let map_data_path = StdPathBuf::from(map_data_path);

                        info!(
                            "using specified vmf embedded files path `{}`",
                            map_data_path.display()
                        );

                        opened.add_open_search_path(OpenSearchPath::Directory(map_data_path));
                    }
                    "root_search" => {
                        // If an asset was imported from the os file system, tries to detect
                        // if the directory structure matches a typical Source game asset directory structure
                        // to use the root of the directory structure as an additional search path.

                        let (asset_path, target_path): (&str, &str) = value.extract()?;

                        if let Some(search_path) = detect_local_search_path(asset_path, target_path)
                        {
                            info!(
                                "detected local asset searh path `{}`",
                                search_path.display()
                            );

                            opened.add_open_search_path(OpenSearchPath::Directory(
                                search_path.to_path_buf(),
                            ));
                        } else {
                            debug!("local asset search path not found");
                        }
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
            callback_obj,
        })
    }

    #[args(path, from_game, kwargs = "**")]
    fn import_vmf(
        &mut self,
        py: Python,
        path: &str,
        from_game: bool,
        kwargs: Option<&PyDict>,
    ) -> PyResult<()> {
        let executor = self.consume()?;

        let mut import_brushes = true;
        let mut geometry_settings = GeometrySettings::default();

        let mut settings = VmfConfig::new(self.material_config);

        if let Some(kwargs) = kwargs {
            for (key, value) in kwargs.iter() {
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

                settings.brushes = if import_brushes {
                    BrushSetting::Import(geometry_settings)
                } else {
                    BrushSetting::Skip
                };
            }
        }

        let start = Instant::now();
        info!("importing vmf `{}`...", path);

        let path: PathBuf = if from_game {
            GamePathBuf::from(path).into()
        } else {
            StdPathBuf::from(path).into()
        };

        let bytes = executor.fs().read(&path)?;
        let vmf = Vmf::from_bytes(&bytes).map_err(|e| PyIOError::new_err(e.to_string()))?;

        executor.process(settings, vmf, || self.process_assets(py));

        info!("vmf imported in {:.2} s", start.elapsed().as_secs_f32());

        Ok(())
    }

    #[args(path, from_game, kwargs = "**")]
    fn import_mdl(
        &mut self,
        py: Python,
        path: &str,
        from_game: bool,
        kwargs: Option<&PyDict>,
    ) -> PyResult<()> {
        let executor = self.consume()?;

        let path = if from_game {
            GamePathBuf::from(path).into()
        } else {
            StdPathBuf::from(path).into()
        };

        let settings = self.mdl_settings(kwargs)?;

        let start = Instant::now();
        info!("importing mdl `{}`...", path);

        executor
            .depend_on(settings, path, || self.process_assets(py))
            .map_err(|e| PyIOError::new_err(e.to_string()))?;

        info!("mdl imported in {:.2} s", start.elapsed().as_secs_f32());

        Ok(())
    }

    fn import_vmt(&mut self, py: Python, path: &str, from_game: bool) -> PyResult<()> {
        let executor = self.consume()?;

        let path = if from_game {
            GamePathBuf::from(path).into()
        } else {
            StdPathBuf::from(path).into()
        };

        let start = Instant::now();
        info!("importing vmt `{}`...", path);

        executor
            .depend_on(self.material_config, path, || self.process_assets(py))
            .map_err(|e| PyIOError::new_err(e.to_string()))?;

        info!("vmt imported in {:.2} s", start.elapsed().as_secs_f32());

        Ok(())
    }

    fn import_vtf(&mut self, py: Python, path: &str, from_game: bool) -> PyResult<()> {
        let executor = self.consume()?;

        let path = if from_game {
            GamePathBuf::from(path).into()
        } else {
            StdPathBuf::from(path).into()
        };

        let start = Instant::now();
        info!("importing vtf `{}`...", path);

        executor.process(VtfConfig, path, || self.process_assets(py));

        info!("vtf imported in {:.2} s", start.elapsed().as_secs_f32());

        Ok(())
    }

    fn import_assets(&mut self, py: Python) {
        // drop the importer, causing the asset channel to disconnect
        // if we don't do this, process_assets will hang forever waiting for new assets to be sent
        self.executor = None;

        self.process_assets(py);
    }
}

impl PyImporter {
    fn consume(&mut self) -> PyResult<Executor<BlenderAssetHandler>> {
        self.executor
            .take()
            .ok_or_else(|| PyRuntimeError::new_err("Importer already consumed"))
    }

    fn process_assets(&self, py: Python) {
        let callback_ref = self.callback_obj.as_ref(py);

        for asset in self.receiver.iter() {
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
            for (key, value) in kwargs.iter() {
                match key.extract()? {
                    "import_animations" => settings.import_animations = value.extract()?,
                    _ => return Err(PyTypeError::new_err("unexpected kwarg")),
                }
            }
        }

        Ok(settings)
    }
}

fn detect_embedded_files_path(file_path_string: &str, opened: &mut OpenFileSystem) {
    let file_path: PathBuf = if StdPath::new(file_path_string).is_absolute() {
        StdPathBuf::from(file_path_string).into()
    } else {
        GamePathBuf::from(file_path_string).into()
    };

    // Ignore errors for now, the error will be shown anyway when the vmf file is actually read later.
    if let Ok(file_info) = opened.open_file_with_info(&file_path) {
        let map_data_path = if let Some(search_path) = file_info.search_path {
            // Map data path can only be added when the vmf is not in a vpk file
            if let OpenSearchPath::Directory(search_dir) = search_path {
                // Remove the extension from the vmf path to get the map data path
                if let Some((map_data_path_part, _extension)) = file_path_string.rsplit_once('.') {
                    let map_data_path = search_dir.join(map_data_path_part);
                    map_data_path.is_dir().then_some(map_data_path)
                } else {
                    None
                }
            } else {
                None
            }
        } else {
            // Vmf is being imported from the file system, just create the path directly
            if let Some((map_data_path, _extension)) = file_path_string.rsplit_once('.') {
                let map_data_path = StdPathBuf::from(map_data_path);
                map_data_path.is_dir().then_some(map_data_path)
            } else {
                None
            }
        };

        if let Some(map_data_path) = map_data_path {
            info!(
                "vmf embedded files path detected as `{}`",
                map_data_path.display()
            );

            opened.add_open_search_path(OpenSearchPath::Directory(map_data_path));
        }
    }
}

fn detect_local_search_path<'a>(asset_path: &'a str, target_path: &str) -> Option<&'a StdPath> {
    let mut asset_path = StdPath::new(asset_path);

    loop {
        asset_path = asset_path.parent()?;

        if asset_path.ends_with(target_path) {
            return asset_path.parent();
        }
    }
}
