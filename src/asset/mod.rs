pub mod brush;
pub mod entities;
pub mod material;
pub mod model;
pub mod overlay;
pub mod sky;
mod utils;
use crossbeam_channel::Sender;
use log::error;

use plumber_core::{
    asset_core::{Asset, Cached, Handler, NoError},
    asset_mdl::{LoadedMdl, MdlConfig, MdlError},
    asset_vmf::{
        brush::BrushConfig,
        other_entity::OtherEntityConfig,
        overlay::{OverlayConfig, OverlayError},
        prop::{LoadedProp, PropConfig, PropError},
    },
    asset_vmt::{
        skybox::{SkyBox, SkyBoxConfig, SkyBoxError},
        VmtError,
    },
    asset_vtf::{LoadedVtf, VtfConfig, VtfError},
    fs::PathBuf,
    vmf::{
        builder::{BuiltBrushEntity, BuiltOverlay},
        entities::{BaseEntity, EntityParseError, TypedEntity},
        vmf::Entity,
    },
};

use self::{
    brush::PyBuiltBrushEntity,
    entities::{
        LightSettings, PyEnvLight, PyLight, PyLoadedProp, PySkyCamera, PySpotLight, PyUnknownEntity,
    },
    material::{
        BuiltMaterialData, Material, MaterialConfig, Settings as MaterialSettings, Texture,
    },
    model::PyModel,
    overlay::PyBuiltOverlay,
    sky::PySkyEqui,
};

pub enum Message {
    Material(Material),
    Texture(Texture),
    Model(PyModel),
    Brush(PyBuiltBrushEntity),
    Overlay(PyBuiltOverlay),
    Prop(PyLoadedProp),
    Light(PyLight),
    SpotLight(PySpotLight),
    EnvLight(PyEnvLight),
    SkyCamera(PySkyCamera),
    SkyEqui(PySkyEqui),
    UnknownEntity(PyUnknownEntity),
}

#[derive(Debug, Clone)]
#[allow(clippy::struct_excessive_bools)]
pub struct HandlerSettings {
    pub import_lights: bool,
    pub light: LightSettings,
    pub import_sky_camera: bool,
    pub sky_equi_height: Option<u32>,
    pub scale: f32,
    pub target_fps: f32,
    pub remove_animations: bool,
    pub material: MaterialSettings,
    pub import_unknown_entities: bool,
}

impl Default for HandlerSettings {
    fn default() -> Self {
        Self {
            import_lights: true,
            light: LightSettings::default(),
            import_sky_camera: true,
            sky_equi_height: None,
            scale: 0.01,
            target_fps: 30.0,
            remove_animations: false,
            material: MaterialSettings::default(),
            import_unknown_entities: false,
        }
    }
}

#[derive(Debug, Clone)]
pub struct BlenderAssetHandler {
    pub sender: Sender<Message>,
    pub settings: HandlerSettings,
}

impl BlenderAssetHandler {
    fn send_asset(&self, asset: Message) {
        self.sender
            .send(asset)
            .expect("asset channel should stay connected");
    }
}

impl Handler<Cached<MaterialConfig>> for BlenderAssetHandler {
    fn handle(&self, output: Result<(PathBuf, Option<BuiltMaterialData>), VmtError>) {
        match output {
            Ok((name, material)) => {
                if let Some(material) = material {
                    self.send_asset(Message::Material(Material::new(&name, material)));
                }
            }
            Err(error) => error!("{error}"),
        }
    }
}

impl Handler<Cached<VtfConfig>> for BlenderAssetHandler {
    fn handle(&self, output: Result<LoadedVtf, VtfError>) {
        match output {
            Ok(texture) => self.send_asset(Message::Texture(Texture::new(&texture))),
            Err(error) => error!("{error}"),
        }
    }
}

impl Handler<Cached<MdlConfig<MaterialConfig>>> for BlenderAssetHandler {
    fn handle(&self, output: Result<LoadedMdl, MdlError>) {
        match output {
            Ok(model) => self.send_asset(Message::Model(PyModel::new(
                model,
                self.settings.target_fps,
                self.settings.remove_animations,
            ))),
            Err(error) => error!("{error}"),
        }
    }
}

impl Handler<Asset<OtherEntityConfig>> for BlenderAssetHandler {
    fn handle(&self, output: Result<TypedEntity<'_>, NoError>) {
        let entity = output.unwrap();

        match entity {
            TypedEntity::Light(light) if self.settings.import_lights => {
                match PyLight::new(light, &self.settings.light, self.settings.scale) {
                    Ok(light) => self.send_asset(Message::Light(light)),
                    Err(error) => log_entity_error(light.entity(), &error),
                }
            }
            TypedEntity::SpotLight(spot_light) if self.settings.import_lights => {
                match PySpotLight::new(spot_light, &self.settings.light, self.settings.scale) {
                    Ok(light) => self.send_asset(Message::SpotLight(light)),
                    Err(error) => log_entity_error(spot_light.entity(), &error),
                }
            }
            TypedEntity::EnvLight(env_light) if self.settings.import_lights => {
                match PyEnvLight::new(env_light, &self.settings.light, self.settings.scale) {
                    Ok(light) => self.send_asset(Message::EnvLight(light)),
                    Err(error) => log_entity_error(env_light.entity(), &error),
                }
            }
            TypedEntity::SkyCamera(sky_camera) if self.settings.import_sky_camera => {
                match PySkyCamera::new(sky_camera, self.settings.scale) {
                    Ok(sky_camera) => self.send_asset(Message::SkyCamera(sky_camera)),
                    Err(error) => log_entity_error(sky_camera.entity(), &error),
                }
            }
            TypedEntity::Unknown(entity) if self.settings.import_unknown_entities => {
                self.send_asset(Message::UnknownEntity(PyUnknownEntity::new(
                    entity,
                    self.settings.scale,
                )));
            }
            _ => {}
        }
    }
}

impl<'a> Handler<Asset<BrushConfig<'a, MaterialConfig>>> for BlenderAssetHandler {
    fn handle(&self, output: Result<BuiltBrushEntity<'_>, NoError>) {
        let brush = output.unwrap();

        self.send_asset(Message::Brush(PyBuiltBrushEntity::new(brush)));
    }
}

impl<'a> Handler<Asset<OverlayConfig<'a, MaterialConfig>>> for BlenderAssetHandler {
    fn handle(&self, output: Result<BuiltOverlay<'_>, OverlayError>) {
        match output {
            Ok(overlay) => self.send_asset(Message::Overlay(PyBuiltOverlay::new(overlay))),
            Err(error) => error!("{error}"),
        }
    }
}

impl Handler<Asset<PropConfig<MaterialConfig>>> for BlenderAssetHandler {
    fn handle(&self, output: Result<LoadedProp<'_>, PropError>) {
        match output {
            Ok(prop) => self.send_asset(Message::Prop(PyLoadedProp::new(prop))),
            Err(error) => error!("{error}"),
        }
    }
}

impl Handler<Asset<SkyBoxConfig>> for BlenderAssetHandler {
    fn handle(&self, output: Result<SkyBox, SkyBoxError>) {
        match output {
            Ok(skybox) => self.send_asset(Message::SkyEqui(PySkyEqui::new(
                skybox,
                self.settings.sky_equi_height,
            ))),
            Err(error) => error!("{error}"),
        }
    }
}

fn log_entity_error(entity: &Entity, error: &EntityParseError) {
    let id = entity.id;
    let class_name = entity.class_name.clone();

    error!("entity {class_name} `{id}`: {error}");
}
