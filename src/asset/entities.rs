use std::f32::consts::FRAC_PI_2;

use glam::{EulerRot, Quat};
use pyo3::prelude::*;

use plumber_core::vmf::{
    entities::{
        BaseEntity, EntityParseError, EnvLight, Light, LightEntity, PointEntity, SkyCamera,
        SpotLight,
    },
    loader::LoadedProp,
};
use rgb::ComponentMap;

#[pyclass(module = "plumber", name = "LoadedProp")]
pub struct PyLoadedProp {
    model: String,
    class_name: String,
    id: i32,
    position: [f32; 3],
    rotation: [f32; 3],
    scale: [f32; 3],
    color: [f32; 4],
}

#[pymethods]
impl PyLoadedProp {
    fn model(&self) -> &str {
        &self.model
    }

    fn class_name(&self) -> &str {
        &self.class_name
    }

    fn id(&self) -> i32 {
        self.id
    }

    fn position(&self) -> [f32; 3] {
        self.position
    }

    fn rotation(&self) -> [f32; 3] {
        self.rotation
    }

    fn scale(&self) -> [f32; 3] {
        self.scale
    }

    fn color(&self) -> [f32; 4] {
        self.color
    }
}

impl PyLoadedProp {
    pub fn new(prop: LoadedProp) -> Self {
        let rotation = prop.rotation;

        Self {
            model: prop.model_path.into_string(),
            class_name: prop.prop.entity().class_name.clone(),
            id: prop.prop.entity().id,
            position: prop.position.into(),
            rotation: [
                rotation[2].to_radians(),
                rotation[0].to_radians(),
                rotation[1].to_radians(),
            ],
            scale: [prop.scale, prop.scale, prop.scale],
            color: prop
                .color
                .map_alpha(|a| f32::from(a) / 255.)
                .map_rgb(|c| srgb_to_linear(f32::from(c) / 255.))
                .into(),
        }
    }
}

#[derive(Debug, Clone)]
pub struct LightSettings {
    pub light_factor: f32,
    pub sun_factor: f32,
    pub ambient_factor: f32,
}

impl Default for LightSettings {
    fn default() -> Self {
        Self {
            light_factor: 0.1,
            sun_factor: 0.01,
            ambient_factor: 0.001,
        }
    }
}

fn srgb_to_linear(srgb: f32) -> f32 {
    if srgb <= 0.040_448_237 {
        srgb / 12.92
    } else {
        ((srgb + 0.055) / 1.055).powf(2.4)
    }
}

#[pyclass(module = "plumber", name = "Light")]
pub struct PyLight {
    color: [f32; 3],
    energy: f32,
    position: [f32; 3],
    id: i32,
}

#[pymethods]
impl PyLight {
    fn id(&self) -> i32 {
        self.id
    }

    fn position(&self) -> [f32; 3] {
        self.position
    }

    fn color(&self) -> [f32; 3] {
        self.color
    }

    fn energy(&self) -> f32 {
        self.energy
    }
}

impl PyLight {
    pub fn new(
        light: Light,
        settings: &LightSettings,
        scale: f32,
    ) -> Result<Self, EntityParseError> {
        let (color, brightness) =
            if let Some((hdr_color, hdr_brightness)) = light.hdr_color_brightness()? {
                let hdr_scale = light.hdr_scale()?;
                (hdr_color, hdr_brightness * hdr_scale)
            } else {
                light.color_brightness()?
            };

        let id = light.entity().id;
        let position = (light.origin()? * scale).into();

        Ok(Self {
            color: color.map(|c| srgb_to_linear(f32::from(c) / 255.)).into(),
            energy: brightness * settings.light_factor,
            position,
            id,
        })
    }
}

fn get_light_rotation(rotation: [f32; 3]) -> [f32; 3] {
    let rotation_quat = Quat::from_euler(
        EulerRot::ZYX,
        rotation[1].to_radians(),
        rotation[0].to_radians(),
        rotation[2].to_radians(),
    ) * Quat::from_rotation_y(-FRAC_PI_2);
    let (z, y, x) = rotation_quat.to_euler(EulerRot::ZYX);
    [x, y, z]
}

#[pyclass(module = "plumber", name = "SpotLight")]
pub struct PySpotLight {
    color: [f32; 3],
    energy: f32,
    spot_size: f32,
    spot_blend: f32,
    position: [f32; 3],
    rotation: [f32; 3],
    id: i32,
}

#[pymethods]
impl PySpotLight {
    fn id(&self) -> i32 {
        self.id
    }

    fn position(&self) -> [f32; 3] {
        self.position
    }

    fn rotation(&self) -> [f32; 3] {
        self.rotation
    }

    fn color(&self) -> [f32; 3] {
        self.color
    }

    fn energy(&self) -> f32 {
        self.energy
    }

    fn spot_size(&self) -> f32 {
        self.spot_size
    }

    fn spot_blend(&self) -> f32 {
        self.spot_blend
    }
}

impl PySpotLight {
    pub fn new(
        light: SpotLight,
        settings: &LightSettings,
        scale: f32,
    ) -> Result<Self, EntityParseError> {
        let (color, brightness) =
            if let Some((hdr_color, hdr_brightness)) = light.hdr_color_brightness()? {
                let hdr_scale = light.hdr_scale()?;
                (hdr_color, hdr_brightness * hdr_scale)
            } else {
                light.color_brightness()?
            };

        let outer_cone = light.outer_cone()?;
        let inner_cone = light.inner_cone()?;

        let spot_size = outer_cone.to_radians() * 2.;
        let spot_blend = 1. - inner_cone / outer_cone;

        let id = light.entity().id;
        let position = (light.origin()? * scale).into();

        let rotation = get_light_rotation(light.angles()?);

        Ok(Self {
            color: color.map(|c| srgb_to_linear(f32::from(c) / 255.)).into(),
            energy: brightness * settings.light_factor,
            spot_size,
            spot_blend,
            position,
            rotation,
            id,
        })
    }
}

#[pyclass(module = "plumber", name = "EnvLight")]
pub struct PyEnvLight {
    sun_color: [f32; 3],
    sun_energy: f32,
    ambient_color: [f32; 4],
    ambient_strength: f32,
    angle: f32,
    position: [f32; 3],
    rotation: [f32; 3],
    id: i32,
}

#[pymethods]
impl PyEnvLight {
    fn id(&self) -> i32 {
        self.id
    }

    fn position(&self) -> [f32; 3] {
        self.position
    }

    fn rotation(&self) -> [f32; 3] {
        self.rotation
    }

    fn sun_color(&self) -> [f32; 3] {
        self.sun_color
    }

    fn sun_energy(&self) -> f32 {
        self.sun_energy
    }

    fn ambient_color(&self) -> [f32; 4] {
        self.ambient_color
    }

    fn ambient_strength(&self) -> f32 {
        self.ambient_strength
    }

    fn angle(&self) -> f32 {
        self.angle
    }
}

impl PyEnvLight {
    pub fn new(
        light: EnvLight,
        settings: &LightSettings,
        scale: f32,
    ) -> Result<Self, EntityParseError> {
        let (sun_color, sun_brightness) =
            if let Some((hdr_color, hdr_brightness)) = light.hdr_color_brightness()? {
                let hdr_scale = light.hdr_scale()?;
                (hdr_color, hdr_brightness * hdr_scale)
            } else {
                light.color_brightness()?
            };

        let (ambient_color, ambient_brightness) =
            if let Some((hdr_color, hdr_brightness)) = light.ambient_hdr_color_brightness()? {
                let hdr_scale = light.ambient_hdr_scale()?;
                (hdr_color, hdr_brightness * hdr_scale)
            } else {
                light.ambient_color_brightness()?
            };

        let angle = light.sun_spread_angle()?.to_radians();

        let id = light.entity().id;
        let position = (light.origin()? * scale).into();

        let rotation = get_light_rotation(light.angles()?);

        Ok(Self {
            sun_color: sun_color
                .map(|c| srgb_to_linear(f32::from(c) / 255.))
                .into(),
            sun_energy: sun_brightness * settings.sun_factor,
            ambient_color: ambient_color
                .map(|c| srgb_to_linear(f32::from(c) / 255.))
                .alpha(1.0)
                .into(),
            ambient_strength: ambient_brightness * settings.ambient_factor,
            angle,
            position,
            rotation,
            id,
        })
    }
}

#[pyclass(module = "plumber", name = "SkyCamera")]
pub struct PySkyCamera {
    id: i32,
    position: [f32; 3],
    scale: [f32; 3],
}

#[pymethods]
impl PySkyCamera {
    fn id(&self) -> i32 {
        self.id
    }

    fn position(&self) -> [f32; 3] {
        self.position
    }

    fn scale(&self) -> [f32; 3] {
        self.scale
    }
}

impl PySkyCamera {
    pub fn new(sky_camera: SkyCamera, scale: f32) -> Result<Self, EntityParseError> {
        let id = sky_camera.entity().id;
        let position = (sky_camera.origin()? * scale).into();
        let scale = sky_camera.scale()?;

        Ok(Self {
            id,
            position,
            scale: [scale, scale, scale],
        })
    }
}
