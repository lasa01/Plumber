pub mod brush;
pub mod entities;
pub mod material;
pub mod model;
pub mod overlay;
pub mod sky;
mod utils;

use std::panic::{catch_unwind, AssertUnwindSafe};

use crossbeam_channel::Sender;
use log::error;

use plumber_core::{
    asset::{self},
    model::loader::LoadedModel,
    vmf::{
        entities::{BaseEntity, EntityParseError, TypedEntity},
        loader::{BuiltBrushEntity, BuiltOverlay, LoadedProp},
        Entity,
    },
    vmt::loader::{LoadedMaterial, LoadedTexture, LoadedVmt, MaterialLoadError, SkyBox},
};

use self::{
    brush::PyBuiltBrushEntity,
    entities::{LightSettings, PyEnvLight, PyLight, PyLoadedProp, PySkyCamera, PySpotLight},
    material::{
        build_material, BuiltMaterialData, Material, Settings as MaterialSettings, Texture,
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
}

#[derive(Debug, Clone)]
pub struct HandlerSettings {
    pub import_lights: bool,
    pub light: LightSettings,
    pub import_sky_camera: bool,
    pub sky_equi_height: Option<u32>,
    pub scale: f32,
    pub target_fps: f32,
    pub remove_animations: bool,
    pub material: MaterialSettings,
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

impl asset::Handler for BlenderAssetHandler {
    type MaterialData = BuiltMaterialData;

    fn handle_error(&mut self, error: asset::Error) {
        error!("{}", error);
    }

    fn build_material(
        &mut self,
        mut vmt: LoadedVmt,
    ) -> Result<Self::MaterialData, MaterialLoadError> {
        catch_unwind(AssertUnwindSafe(|| {
            build_material(&mut vmt, &self.settings.material)
        }))
        .map_err(|e| {
            if let Some(s) = e.downcast_ref::<&'static str>() {
                MaterialLoadError::Custom(s)
            } else {
                MaterialLoadError::Custom("material load panicked")
            }
        })
    }

    fn handle_material(&mut self, material: LoadedMaterial<Self::MaterialData>) {
        self.send_asset(Message::Material(Material::new(material)));
    }

    fn handle_texture(&mut self, texture: LoadedTexture) {
        self.send_asset(Message::Texture(Texture::new(texture)));
    }

    fn handle_model(&mut self, model: LoadedModel) {
        self.send_asset(Message::Model(PyModel::new(
            model,
            self.settings.target_fps,
            self.settings.remove_animations,
        )));
    }

    fn handle_entity(&mut self, entity: TypedEntity) {
        match entity {
            TypedEntity::Light(light) if self.settings.import_lights => {
                match PyLight::new(light, &self.settings.light, self.settings.scale) {
                    Ok(light) => self.send_asset(Message::Light(light)),
                    Err(error) => log_entity_error(light.entity(), error),
                }
            }
            TypedEntity::SpotLight(spot_light) if self.settings.import_lights => {
                match PySpotLight::new(spot_light, &self.settings.light, self.settings.scale) {
                    Ok(light) => self.send_asset(Message::SpotLight(light)),
                    Err(error) => log_entity_error(spot_light.entity(), error),
                }
            }
            TypedEntity::EnvLight(env_light) if self.settings.import_lights => {
                match PyEnvLight::new(env_light, &self.settings.light, self.settings.scale) {
                    Ok(light) => self.send_asset(Message::EnvLight(light)),
                    Err(error) => log_entity_error(env_light.entity(), error),
                }
            }
            TypedEntity::SkyCamera(sky_camera) if self.settings.import_sky_camera => {
                match PySkyCamera::new(sky_camera, self.settings.scale) {
                    Ok(sky_camera) => self.send_asset(Message::SkyCamera(sky_camera)),
                    Err(error) => log_entity_error(sky_camera.entity(), error),
                }
            }
            _ => {}
        }
    }

    fn handle_brush(&mut self, brush: BuiltBrushEntity) {
        self.send_asset(Message::Brush(PyBuiltBrushEntity::new(brush)));
    }

    fn handle_overlay(&mut self, overlay: BuiltOverlay) {
        self.send_asset(Message::Overlay(PyBuiltOverlay::new(overlay)));
    }

    fn handle_prop(&mut self, prop: LoadedProp) {
        self.send_asset(Message::Prop(PyLoadedProp::new(prop)));
    }

    fn handle_skybox(&mut self, skybox: SkyBox) {
        self.send_asset(Message::SkyEqui(PySkyEqui::new(
            skybox,
            self.settings.sky_equi_height,
        )));
    }
}

fn log_entity_error(entity: &Entity, error: EntityParseError) {
    let id = entity.id;
    let class_name = entity.class_name.clone();

    error!(
        "{}",
        asset::Error::Entity {
            id,
            class_name,
            error,
        }
    );
}
