use std::str::FromStr;

use glam::{Vec2, Vec3};
use log::warn;
use plumber_core::{
    asset::vmt::LoadedVmt,
    uncased::AsUncased,
    vmt::{TexturePath, Transform},
};
use pyo3::{exceptions::PyValueError, PyErr};
use rgb::RGB;

use super::{
    builder_base::{ColorSpace, InputLink, MaterialBuilder},
    definitions::{groups, shaders},
    nodes::{NodeSocketId, Ref, Value},
    BuiltMaterialData,
};

#[derive(Debug, Clone, Copy)]
pub enum TextureInterpolation {
    Linear,
    Closest,
    Cubic,
    Smart,
}

impl FromStr for TextureInterpolation {
    type Err = PyErr;

    fn from_str(s: &str) -> Result<Self, Self::Err> {
        match s {
            "Linear" => Ok(Self::Linear),
            "Closest" => Ok(Self::Closest),
            "Cubic" => Ok(Self::Cubic),
            "Smart" => Ok(Self::Smart),
            _ => Err(PyValueError::new_err("invalid texture interpolation")),
        }
    }
}

impl Default for TextureInterpolation {
    fn default() -> Self {
        Self::Linear
    }
}

impl TextureInterpolation {
    fn to_str(self) -> &'static str {
        match self {
            TextureInterpolation::Linear => "Linear",
            TextureInterpolation::Closest => "Closest",
            TextureInterpolation::Cubic => "Cubic",
            TextureInterpolation::Smart => "Smart",
        }
    }
}

#[derive(Debug, Clone, Default)]
pub struct Settings {
    pub simple_materials: bool,
    pub allow_culling: bool,
    pub editor_materials: bool,
    pub texture_interpolation: TextureInterpolation,
}

impl MaterialBuilder {
    fn handle_texture(
        &mut self,
        vmt: &mut LoadedVmt,
        parameter: &'static str,
        transform_parameter: Option<&'static str>,
        color_space: ColorSpace,
        interpolation: TextureInterpolation,
    ) -> bool {
        self.handle_texture_inner(vmt, parameter, color_space, interpolation, |vmt| {
            if let Some(transform_parameter) = transform_parameter {
                vmt.extract_param_or_default(transform_parameter)
            } else {
                Transform::default()
            }
        })
    }

    fn handle_texture_scaled(
        &mut self,
        vmt: &mut LoadedVmt,
        parameter: &'static str,
        transform_parameter: &'static str,
        scale_parameter: &'static str,
        color_space: ColorSpace,
        interpolation: TextureInterpolation,
    ) -> bool {
        self.handle_texture_inner(vmt, parameter, color_space, interpolation, |vmt| {
            let mut transform: Transform = vmt.extract_param_or_default(transform_parameter);

            let scale = vmt
                .try_extract_param::<Vec3>(scale_parameter)
                .map(|o| o.map(Vec3::truncate))
                .or_else(|_| vmt.try_extract_param::<Vec2>(scale_parameter))
                .unwrap_or_else(|_| vmt.extract_param::<f32>(scale_parameter).map(Vec2::splat));

            if let Some(scale) = scale {
                transform.scale *= scale;
            }

            transform
        })
    }

    fn handle_texture_4wayblend(
        &mut self,
        vmt: &mut LoadedVmt,
        parameter: &'static str,
        uv_scale_parameter: &'static str,
        color_space: ColorSpace,
        interpolation: TextureInterpolation,
    ) -> bool {
        self.handle_texture_inner(vmt, parameter, color_space, interpolation, |vmt| {
            let mut transform = Transform::default();

            let base_uv_scale = vmt.extract_param("$texture1_uvscale").unwrap_or(Vec2::ONE);
            let uv_scale = vmt.extract_param(uv_scale_parameter).unwrap_or(Vec2::ONE);

            transform.scale = base_uv_scale * uv_scale;

            transform
        })
    }

    fn handle_texture_split(
        &mut self,
        vmt: &mut LoadedVmt,
        parameter: &'static str,
        interpolation: TextureInterpolation,
    ) -> bool {
        let shader = vmt.shader();

        if let Some(texture) = shader.extract_param::<TexturePath>(parameter, vmt.material_path()) {
            let texture_path = texture.absolute_path();

            match vmt.load_texture(texture_path.clone()) {
                Ok(_) => {
                    self.texture_color_spaces
                        .insert(texture_path.clone().into_string(), ColorSpace::NonColor);

                    self.input(parameter)
                        .pipeline(vec![&groups::SPLIT_TEXTURE])
                        .property(
                            &groups::SPLIT_TEXTURE,
                            "image",
                            Value::Texture(texture_path),
                        )
                        .property(
                            &groups::SPLIT_TEXTURE,
                            "interpolation",
                            Value::Enum(interpolation.to_str()),
                        );

                    true
                }
                Err(err) => {
                    warn!(
                        "material `{}`: parameter `{}`: error loading texture `{}`: {}",
                        vmt.material_path(),
                        parameter,
                        texture_path,
                        err
                    );

                    false
                }
            }
        } else {
            false
        }
    }

    fn handle_texture_inner(
        &mut self,
        vmt: &mut LoadedVmt,
        parameter: &'static str,
        color_space: ColorSpace,
        interpolation: TextureInterpolation,
        get_transform: impl Fn(&mut LoadedVmt) -> Transform,
    ) -> bool {
        let shader = vmt.shader();

        if let Some(texture) = shader.extract_param::<TexturePath>(parameter, vmt.material_path()) {
            let texture_path = texture.absolute_path();

            match vmt.load_texture(texture_path.clone()) {
                Ok(_) => {
                    self.texture_color_spaces
                        .insert(texture_path.clone().into_string(), color_space);
                    let transform: Transform = get_transform(vmt);

                    if transform == Transform::default() {
                        self.input(parameter)
                            .pipeline(vec![&groups::TEXTURE])
                            .property(&groups::TEXTURE, "image", Value::Texture(texture_path))
                            .property(
                                &groups::TEXTURE,
                                "interpolation",
                                Value::Enum(interpolation.to_str()),
                            );
                    } else {
                        let scale = transform.scale.extend(1.0).to_array();
                        let rotation = [0.0, 0.0, transform.rotate];
                        let location = transform.translate.extend(0.0).to_array();

                        self.input(parameter)
                            .pipeline(vec![&groups::TRANSFORMED_TEXTURE])
                            .property(
                                &groups::TRANSFORMED_TEXTURE,
                                "image",
                                Value::Texture(texture_path),
                            )
                            .property(
                                &groups::TRANSFORMED_TEXTURE,
                                "interpolation",
                                Value::Enum(interpolation.to_str()),
                            )
                            .link(&groups::TRANSFORMED_TEXTURE, "scale", Value::Vec(scale))
                            .link(
                                &groups::TRANSFORMED_TEXTURE,
                                "rotation",
                                Value::Vec(rotation),
                            )
                            .link(
                                &groups::TRANSFORMED_TEXTURE,
                                "location",
                                Value::Vec(location),
                            );
                    }

                    true
                }
                Err(err) => {
                    warn!(
                        "material `{}`: parameter `{}`: error loading texture `{}`: {}",
                        vmt.material_path(),
                        parameter,
                        texture_path,
                        err
                    );

                    false
                }
            }
        } else {
            false
        }
    }
}

fn build_nodraw_material() -> BuiltMaterialData {
    let mut builder = MaterialBuilder::new(&shaders::TRANSPARENT);

    builder
        .property("blend_method", Value::Enum("CLIP"))
        .property("shadow_method", Value::Enum("CLIP"));

    builder.build()
}

fn build_water_material(vmt: &mut LoadedVmt, settings: &Settings) -> BuiltMaterialData {
    let mut builder = MaterialBuilder::new(&shaders::GLASS);

    builder
        .property("blend_method", Value::Enum("BLEND"))
        .property("shadow_method", Value::Enum("HASHED"))
        .socket_value("IOR", Value::Float(1.333))
        .socket_value("Roughness", Value::Float(0.3));

    if vmt.extract_param_or_default("$fogenable") {
        if let Some(color) = vmt.extract_param::<RGB<f32>>("$fogcolor") {
            builder.socket_value(
                NodeSocketId::Name("Color"),
                Value::Color(color.alpha(1.0).into()),
            );
        }
    }

    if builder.handle_texture(
        vmt,
        "$normalmap",
        Some("$bumptransform"),
        ColorSpace::NonColor,
        settings.texture_interpolation,
    ) {
        let output = builder.output("Normal", "$normalmap", "color");

        if settings.simple_materials {
            output
                .push(&groups::NORMAL_MAP)
                .link_input(&groups::NORMAL_MAP, "image")
                .link(&groups::NORMAL_MAP, "strength", Value::Float(1.0));
        } else {
            output
                .push(&groups::DX_NORMAL_MAP_CONVERTER)
                .link_input(&groups::DX_NORMAL_MAP_CONVERTER, "image")
                .push(&groups::NORMAL_MAP)
                .link(&groups::NORMAL_MAP, "strength", Value::Float(1.0));
        }
    }

    builder.build()
}

struct FwbBlendData {
    lum_start: [f32; 4],
    lum_end: [f32; 4],
    blend_start: [f32; 3],
    blend_end: [f32; 3],
    bump_fac: [f32; 3],
    detail_fac: [f32; 4],
    lum_fac: [f32; 3],
}

fn phong_exponent_to_roughness(exponent: f32) -> f32 {
    0.66 * (150.0 - exponent) / 150.0
}

struct NormalMaterialBuilder<'a, 'b> {
    builder: MaterialBuilder,
    vmt: &'a mut LoadedVmt<'b>,
    settings: &'a Settings,
}

// Common methods
impl<'a, 'b> NormalMaterialBuilder<'a, 'b> {
    fn new(vmt: &'a mut LoadedVmt<'b>, settings: &'a Settings) -> Self {
        Self {
            builder: MaterialBuilder::new(&shaders::PRINCIPLED),
            vmt,
            settings,
        }
    }

    fn handle_texture(
        &mut self,
        parameter: &'static str,
        transform_parameter: Option<&'static str>,
        color_space: ColorSpace,
    ) -> bool {
        self.builder.handle_texture(
            self.vmt,
            parameter,
            transform_parameter,
            color_space,
            self.settings.texture_interpolation,
        )
    }

    fn handle_texture_scaled(
        &mut self,
        parameter: &'static str,
        transform_parameter: &'static str,
        scale_parameter: &'static str,
        color_space: ColorSpace,
    ) -> bool {
        self.builder.handle_texture_scaled(
            self.vmt,
            parameter,
            transform_parameter,
            scale_parameter,
            color_space,
            self.settings.texture_interpolation,
        )
    }

    fn handle_texture_split(&mut self, parameter: &'static str) -> bool {
        self.builder
            .handle_texture_split(self.vmt, parameter, self.settings.texture_interpolation)
    }

    fn handle_cull(&mut self) {
        if !self.settings.allow_culling
            || self.vmt.extract_param_or_default("$nocull")
            || self.vmt.extract_param_or_default("$decal")
        {
            self.builder
                .property("use_backface_culling", Value::Bool(false));
        } else {
            self.builder
                .property("use_backface_culling", Value::Bool(true));
        }
    }

    fn handle_color(&mut self) -> bool {
        if let Some(color) = self.vmt.extract_param::<RGB<f32>>("$color") {
            let color = color.alpha(1.0).into();
            self.builder.socket_value("Base Color", Value::Color(color));

            true
        } else {
            false
        }
    }

    fn handle_alpha(&mut self) {
        if let Some(alpha) = self.vmt.extract_param("$alpha") {
            self.builder.socket_value("Alpha", Value::Float(alpha));
        }
    }

    fn handle_unlit(&mut self) {
        if self.vmt.shader().shader.as_uncased_str() == "unlitgeneric".as_uncased()
            || self.vmt.extract_param_or_default("%compilenolight")
        {
            self.builder
                .socket_value("Specular", Value::Float(0.0))
                .socket_value("Roughness", Value::Float(1.0));
        }
    }

    fn handle_envmap(&mut self, base_texture: &'static str) -> bool {
        if self.vmt.extract_param::<TexturePath>("$envmap").is_none() {
            return false;
        }

        if self.builder.has_input(base_texture)
            && (self
                .vmt
                .extract_param_or_default::<bool>("$basealphaenvmapmask")
                || self
                    .vmt
                    .extract_param_or_default::<bool>("$basealphaenvmask"))
        {
            self.builder
                .output("Specular", base_texture, "alpha")
                .push(&groups::INVERT_VALUE)
                .link_input(&groups::INVERT_VALUE, "value");
        } else if self.builder.has_input("$bumpmap")
            && self
                .vmt
                .extract_param_or_default("$normalmapalphaenvmapmask")
        {
            self.builder.output("Specular", "$bumpmap", "alpha");
        } else if self.builder.has_input("$tintmasktexture")
            && self
                .vmt
                .extract_param_or_default("$envmapmaskintintmasktexture")
        {
            self.builder.output("Specular", "$tintmasktexture", "r");
        } else if self.handle_texture(
            "$envmapmask",
            Some("$envmapmasktransform"),
            ColorSpace::NonColor,
        ) {
            let output = self.builder.output("Specular", "$envmapmask", "color");

            if let Some(tint) = self.vmt.extract_param::<RGB<f32>>("$envmaptint") {
                output
                    .push(&groups::MULTIPLY_VALUE)
                    .link_input(&groups::MULTIPLY_VALUE, "value")
                    .link(
                        &groups::MULTIPLY_VALUE,
                        "fac",
                        Value::Float(tint.iter().sum::<f32>() / 3.0),
                    );
            }
        } else if let Some(tint) = self.vmt.extract_param::<RGB<f32>>("$envmaptint") {
            let tint = tint.iter().sum::<f32>() / 3.0;
            self.builder.socket_value("Specular", Value::Float(tint));
        } else {
            self.builder.socket_value("Specular", Value::Float(0.8));
        }

        true
    }

    fn handle_ssbump_detail(&mut self) {
        if self.vmt.extract_param_or_default::<u8>("$detailblendmode") != 10
            || !self.handle_texture("$detail", Some("$detailtexturetransform"), ColorSpace::Srgb)
        {
            return;
        }

        self.builder
            .output("Normal", "$detail", "color")
            .push(&groups::SSBUMP_CONVERTER)
            .link_input(&groups::SSBUMP_CONVERTER, "image")
            .push(&groups::NORMAL_MAP)
            .link(&groups::NORMAL_MAP, "strength", Value::Float(1.0));
    }

    fn build(mut self) -> BuiltMaterialData {
        if self.settings.simple_materials {
            self.build_simple();
        } else if &self.vmt.shader().shader == "Lightmapped_4WayBlend" {
            self.build_fwb();
        } else {
            self.build_normal();
        }

        self.builder.build()
    }
}

// Normal material building
impl<'a, 'b> NormalMaterialBuilder<'a, 'b> {
    fn handle_blendmodulatetexture(&mut self) -> Ref {
        let vertex_blend_input = Ref::new("vertex_color", "color");

        if self.handle_texture(
            "$blendmodulatetexture",
            Some("$blendmasktransform"),
            ColorSpace::NonColor,
        ) {
            self.builder
                .input("blend")
                .pipeline(vec![&groups::MODULATED_FACTOR])
                .link(
                    &groups::MODULATED_FACTOR,
                    "modulate",
                    Ref::new("$blendmodulatetexture", "color"),
                )
                .link(&groups::MODULATED_FACTOR, "fac", vertex_blend_input)
                .socket("fac")
        } else {
            vertex_blend_input
        }
    }

    fn handle_basetexture(&mut self, blend_input: Ref) -> bool {
        if !self.handle_texture(
            "$basetexture",
            Some("$basetexturetransform"),
            ColorSpace::Srgb,
        ) {
            return false;
        }

        self.handle_detail(
            "$basetexture",
            "$detail",
            "$detailtexturetransform",
            "$detailscale",
            "$detailblendfactor",
        );

        if let Some(color) = self.vmt.extract_param::<RGB<f32>>("$layertint1") {
            let color = color.alpha(1.0).into();

            self.builder
                .input("$basetexture")
                .push(&groups::COLOR_TEXTURE)
                .link(&groups::COLOR_TEXTURE, "mixin", Value::Color(color))
                .link(&groups::COLOR_TEXTURE, "fac", Value::Float(1.0));
        }

        self.handle_basetexture2(blend_input);

        let color_result = self.handle_basetexture_color();

        let output = self.builder.output("Base Color", "$basetexture", "color");

        if let Some((color, factor)) = color_result {
            output
                .push(&groups::COLOR_TEXTURE)
                .link_input(&groups::COLOR_TEXTURE, "color")
                .link(&groups::COLOR_TEXTURE, "mixin", color)
                .link(&groups::COLOR_TEXTURE, "fac", factor);
        }

        true
    }

    fn handle_basetexture2(&mut self, blend_input: Ref) {
        if !self.handle_texture(
            "$basetexture2",
            Some("$basetexturetransform2"),
            ColorSpace::Srgb,
        ) {
            return;
        }

        self.handle_detail(
            "$basetexture2",
            "$detail2",
            "$detailtexturetransform2",
            "$detailscale2",
            "$detailblendfactor2",
        );

        if let Some(color) = self.vmt.extract_param::<RGB<f32>>("$layertint2") {
            let color = color.alpha(1.0).into();

            self.builder
                .input("$basetexture2")
                .push(&groups::COLOR_TEXTURE)
                .link(&groups::COLOR_TEXTURE, "mixin", Value::Color(color))
                .link(&groups::COLOR_TEXTURE, "fac", Value::Float(1.0));
        }

        self.builder
            .input("$basetexture")
            .push(&groups::BLEND_TEXTURE)
            .link(
                &groups::BLEND_TEXTURE,
                "color2",
                Ref::new("$basetexture2", "color"),
            )
            .link(
                &groups::BLEND_TEXTURE,
                "alpha2",
                Ref::new("$basetexture2", "alpha"),
            )
            .link(&groups::BLEND_TEXTURE, "fac", blend_input);
    }

    fn handle_detail(
        &mut self,
        base: &'static str,
        detail: &'static str,
        transform: &'static str,
        scale: &'static str,
        blend_factor: &'static str,
    ) {
        let detail_mode_supported =
            self.vmt.extract_param_or_default::<u8>("$detailblendmode") == 0;

        if !detail_mode_supported
            || !self.handle_texture_scaled(detail, transform, scale, ColorSpace::NonColor)
        {
            return;
        }

        let blend_fac = self.vmt.extract_param(blend_factor).unwrap_or(1.0);

        self.builder
            .input(base)
            .push(&groups::DETAIL_TEXTURE)
            .link(&groups::DETAIL_TEXTURE, "detail", Ref::new(detail, "color"))
            .link(&groups::DETAIL_TEXTURE, "fac", Value::Float(blend_fac));
    }

    fn handle_basetexture_color(&mut self) -> Option<(InputLink, InputLink)> {
        if self.vmt.shader().shader.as_uncased_str() == "vertexlitgeneric".as_uncased()
            && !self
                .vmt
                .extract_param_or_default::<bool>("$allowdiffusemodulation")
            && !self.vmt.extract_param_or_default::<bool>("$notint")
        {
            let color = if let Some(color) = self.vmt.extract_param::<RGB<f32>>("$color2") {
                let color = color.alpha(1.0).into();
                InputLink::Value(Value::Color(color))
            } else {
                let input = self
                    .builder
                    .input("object_color")
                    .pipeline(vec![&groups::OBJECT_COLOR]);

                InputLink::Input(input.socket("color"))
            };

            let factor = if self.handle_texture_split("$tintmasktexture") {
                InputLink::Input(Ref::new("$tintmasktexture", "g"))
            } else if self.vmt.extract_param_or_default("$blendtintbybasealpha") {
                InputLink::Input(Ref::new("$basetexture", "alpha"))
            } else {
                InputLink::Value(Value::Float(1.0))
            };

            Some((color, factor))
        } else if let Some(color) = self.vmt.extract_param::<RGB<f32>>("$color") {
            let color = color.alpha(1.0).into();

            Some((Value::Color(color).into(), Value::Float(1.0).into()))
        } else {
            None
        }
    }

    fn handle_vertex_color(&mut self) -> bool {
        if !self.vmt.extract_param_or_default::<bool>("$vertexcolor") {
            return false;
        }

        self.builder.output("Base Color", "vertex_color", "color");

        true
    }

    fn handle_bumpmap(&mut self, blend_input: Ref) -> bool {
        if !self.handle_texture("$bumpmap", Some("$bumptransform"), ColorSpace::NonColor) {
            return false;
        }

        self.handle_bumpmap2(blend_input);

        let output = self.builder.output("Normal", "$bumpmap", "color");

        if self.vmt.extract_param_or_default("$ssbump") {
            output
                .push(&groups::SSBUMP_CONVERTER)
                .link_input(&groups::SSBUMP_CONVERTER, "image");
        } else {
            output
                .push(&groups::DX_NORMAL_MAP_CONVERTER)
                .link_input(&groups::DX_NORMAL_MAP_CONVERTER, "image");
        }

        output
            .push(&groups::NORMAL_MAP)
            .link(&groups::NORMAL_MAP, "strength", Value::Float(1.0));

        true
    }

    fn handle_bumpmap2(&mut self, blend_input: Ref) {
        if !self.handle_texture("$bumpmap2", Some("$bumptransform2"), ColorSpace::NonColor) {
            return;
        }

        let blend_input = if self.vmt.extract_param_or_default("$addbumpmaps") {
            let bump_amount_1 = self.vmt.extract_param("$bumpdetailscale1").unwrap_or(1.0);
            let bump_amount_2 = self.vmt.extract_param("$bumpdetailscale2").unwrap_or(1.0);

            let factor = bump_amount_2 / (bump_amount_1 + bump_amount_2);
            InputLink::Value(Value::Float(factor))
        } else {
            InputLink::Input(blend_input)
        };

        self.builder
            .input("$bumpmap")
            .push(&groups::BLEND_TEXTURE)
            .link(
                &groups::BLEND_TEXTURE,
                "color2",
                Ref::new("$bumpmap2", "color"),
            )
            .link(
                &groups::BLEND_TEXTURE,
                "alpha2",
                Ref::new("$bumpmap2", "alpha"),
            )
            .link(&groups::BLEND_TEXTURE, "fac", blend_input);
    }

    fn handle_translucent(&mut self) -> bool {
        if !self.vmt.extract_param_or_default::<bool>("$translucent") {
            return false;
        }

        self.builder
            .property("blend_method", Value::Enum("BLEND"))
            .property("shadow_method", Value::Enum("HASHED"));

        if self.builder.has_input("$basetexture") {
            let output = self.builder.output("Alpha", "$basetexture", "alpha");

            if let Some(alpha) = self.vmt.extract_param("$alpha") {
                output
                    .push(&groups::MULTIPLY_VALUE)
                    .link_input(&groups::MULTIPLY_VALUE, "value")
                    .link(&groups::MULTIPLY_VALUE, "fac", Value::Float(alpha));
            }
        } else {
            self.handle_alpha();
        }

        true
    }

    fn handle_alphatest(&mut self) -> bool {
        if !self.vmt.extract_param_or_default::<bool>("$alphatest") {
            return false;
        }

        self.builder
            .property("blend_method", Value::Enum("CLIP"))
            .property("shadow_method", Value::Enum("CLIP"));

        let reference = self.vmt.extract_param("$alphatestreference").unwrap_or(0.7);
        self.builder
            .property("alpha_threshold", Value::Float(reference));

        if self.vmt.extract_param_or_default("$allowalphatocoverage") {
            self.builder.property("blend_method", Value::Enum("HASHED"));
        }

        if self.builder.has_input("$basetexture") {
            let output = self.builder.output("Alpha", "$basetexture", "alpha");

            if let Some(alpha) = self.vmt.extract_param("$alpha") {
                output
                    .push(&groups::MULTIPLY_VALUE)
                    .link_input(&groups::MULTIPLY_VALUE, "value")
                    .link(&groups::MULTIPLY_VALUE, "fac", Value::Float(alpha));
            }
        } else {
            self.handle_alpha();
        }

        true
    }

    fn handle_vertexalpha(&mut self) -> bool {
        if !self.vmt.extract_param_or_default::<bool>("$vertexalpha") {
            return false;
        }

        self.builder
            .property("blend_method", Value::Enum("BLEND"))
            .property("shadow_method", Value::Enum("HASHED"));

        let output = self.builder.output("Alpha", "vertex_color", "alpha");

        if let Some(alpha) = self.vmt.extract_param("$alpha") {
            output
                .push(&groups::MULTIPLY_VALUE)
                .link_input(&groups::MULTIPLY_VALUE, "value")
                .link(&groups::MULTIPLY_VALUE, "fac", Value::Float(alpha));
        }

        true
    }

    fn handle_phong(&mut self, blend_input: Ref) -> bool {
        if !self.vmt.extract_param_or_default::<bool>("$phong")
            && self.vmt.shader().shader.as_uncased_str() != "character".as_uncased()
        {
            return false;
        }

        if self
            .vmt
            .extract_param_or_default("$basemapluminancephongmask")
        {
            self.builder.output("Specular", "$basetexture", "color");
        } else if self.vmt.extract_param_or_default("$basemapalphaphongmask") {
            self.builder.output("Specular", "$basetexture", "alpha");
        } else if self.builder.has_input("$masks1") {
            self.builder.output("Specular", "$masks1", "g");
        } else if self.builder.has_input("$bumpmap") {
            self.builder.output("Specular", "$bumpmap", "alpha");
        }

        if let Some(exponent) = self.vmt.extract_param::<f32>("$phongexponent") {
            let roughness = phong_exponent_to_roughness(exponent);

            if let Some(exponent_2) = self.vmt.extract_param::<f32>("$phongexponent2") {
                let roughness_2 = phong_exponent_to_roughness(exponent_2);

                self.builder
                    .output("Roughness", blend_input.target, blend_input.name)
                    .push(&groups::BLEND_VALUES)
                    .link_input(&groups::BLEND_VALUES, "fac")
                    .link(&groups::BLEND_VALUES, "min", Value::Float(roughness))
                    .link(&groups::BLEND_VALUES, "max", Value::Float(roughness_2));
            } else {
                self.builder
                    .socket_value("Roughness", Value::Float(roughness));
            }
        } else if self.handle_texture_split("$phongexponenttexture") {
            self.builder
                .output("Roughness", "$phongexponenttexture", "r");

            if self.vmt.extract_param_or_default("$phongalbedotint") {
                self.builder
                    .output("Specular Tint", "$phongexponenttexture", "g");
            }
        } else {
            self.builder.socket_value("Roughness", Value::Float(0.6));
        }

        true
    }

    fn handle_metal(&mut self) {
        if self.builder.has_input("$masks1") {
            self.builder
                .output("Metallic", "$masks1", "b")
                .push(&groups::INVERT_VALUE)
                .link_input(&groups::INVERT_VALUE, "value");
        } else if let Some(metalness) = self.vmt.extract_param("$metalness") {
            self.builder
                .socket_value("Metallic", Value::Float(metalness));
        }
    }

    fn handle_selfillum(&mut self) {
        let mut selfillum_input = None;

        if self.builder.has_input("$envmapmask")
            && self
                .vmt
                .extract_param_or_default::<bool>("$selfillum_envmapmask_alpha")
        {
            selfillum_input = Some(("$envmapmask", "alpha"));
        } else if self.vmt.extract_param_or_default("$selfillum") {
            if self.handle_texture("$selfillummask", None, ColorSpace::NonColor) {
                selfillum_input = Some(("$selfillummask", "color"));
            } else if self.builder.has_input("$basetexture") {
                selfillum_input = Some(("$basetexture", "alpha"));
            }
        }

        if let Some((input, source)) = selfillum_input {
            if self.builder.has_input("$basetexture") {
                self.builder
                    .output("Emission", "$basetexture", "color")
                    .push(&groups::COLOR_TEXTURE)
                    .link_input(&groups::COLOR_TEXTURE, "color")
                    .link(&groups::COLOR_TEXTURE, "mixin", Ref::new(input, source))
                    .link(&groups::COLOR_TEXTURE, "fac", Value::Float(1.0));
            } else {
                self.builder.output("Emission", input, source);
            }
        }
    }

    fn build_normal(&mut self) {
        self.builder
            .property("blend_method", Value::Enum("OPAQUE"))
            .property("shadow_method", Value::Enum("OPAQUE"))
            .socket_value("Specular", Value::Float(0.1))
            .socket_value("Roughness", Value::Float(0.9));

        self.builder
            .input("vertex_color")
            .pipeline(vec![&groups::VERTEX_COLOR]);

        self.handle_cull();

        let blend_input = self.handle_blendmodulatetexture();

        if !self.handle_basetexture(blend_input) && !self.handle_color() {
            self.handle_vertex_color();
        }

        if !self.handle_bumpmap(blend_input) {
            self.handle_ssbump_detail();
        }

        if !self.handle_translucent() && !self.handle_alphatest() && !self.handle_vertexalpha() {
            self.handle_alpha();
        }

        self.handle_texture_split("$masks1");

        if !self.handle_phong(blend_input) && !self.handle_envmap("$basetexture") {
            self.handle_unlit();
        }

        self.handle_metal();

        self.handle_selfillum();
    }
}

// Simple material building
impl<'a, 'b> NormalMaterialBuilder<'a, 'b> {
    fn handle_basetexture_simple(&mut self) -> bool {
        if !self.handle_texture(
            "$basetexture",
            Some("$basetexturetransform"),
            ColorSpace::Srgb,
        ) {
            return false;
        }

        self.builder.output("Base Color", "$basetexture", "color");

        true
    }

    fn handle_bumpmap_simple(&mut self) {
        if self.vmt.extract_param_or_default("$ssbump") {
            return;
        }

        if !self.handle_texture("$bumpmap", Some("$bumptransform"), ColorSpace::NonColor) {
            return;
        }

        self.builder
            .output("Normal", "$bumpmap", "color")
            .push(&groups::NORMAL_MAP)
            .link_input(&groups::NORMAL_MAP, "image")
            .link(&groups::NORMAL_MAP, "strength", Value::Float(1.0));
    }

    fn handle_translucent_simple(&mut self) -> bool {
        if !self.vmt.extract_param_or_default::<bool>("$translucent") {
            return false;
        }

        self.builder
            .property("blend_method", Value::Enum("BLEND"))
            .property("shadow_method", Value::Enum("HASHED"));

        if self.builder.has_input("$basetexture") {
            self.builder.output("Alpha", "$basetexture", "alpha");
        } else {
            self.handle_alpha();
        }

        true
    }

    fn handle_alphatest_simple(&mut self) -> bool {
        if !self.vmt.extract_param_or_default::<bool>("$alphatest") {
            return false;
        }

        self.builder
            .property("blend_method", Value::Enum("CLIP"))
            .property("shadow_method", Value::Enum("CLIP"));

        let reference = self.vmt.extract_param("$alphatestreference").unwrap_or(0.7);
        self.builder
            .property("alpha_threshold", Value::Float(reference));

        if self.vmt.extract_param_or_default("$allowalphatocoverage") {
            self.builder.property("blend_method", Value::Enum("HASHED"));
        }

        if self.builder.has_input("$basetexture") {
            self.builder.output("Alpha", "$basetexture", "alpha");
        } else {
            self.handle_alpha();
        }

        true
    }

    fn handle_phong_simple(&mut self) -> bool {
        if !self.vmt.extract_param_or_default::<bool>("$phong")
            && self.vmt.shader().shader.as_uncased_str() != "character".as_uncased()
        {
            return false;
        }

        if self
            .vmt
            .extract_param_or_default("$basemapluminancephongmask")
        {
            self.builder.output("Specular", "$basetexture", "color");
        }

        if let Some(exponent) = self.vmt.extract_param::<f32>("$phongexponent") {
            let roughness = phong_exponent_to_roughness(exponent);

            self.builder
                .socket_value("Roughness", Value::Float(roughness));
        } else {
            self.builder.socket_value("Roughness", Value::Float(0.6));
        }

        true
    }

    fn handle_envmap_simple(&mut self) -> bool {
        if self.vmt.extract_param::<TexturePath>("$envmap").is_none() {
            return false;
        }

        if self.handle_texture(
            "$envmapmask",
            Some("$envmapmasktransform"),
            ColorSpace::NonColor,
        ) {
            self.builder.output("Specular", "$envmapmask", "color");
        } else if let Some(tint) = self.vmt.extract_param::<RGB<f32>>("$envmaptint") {
            let tint = tint.iter().sum::<f32>() / 3.0;
            self.builder.socket_value("Specular", Value::Float(tint));
        } else {
            self.builder.socket_value("Specular", Value::Float(0.8));
        }

        true
    }

    fn handle_metal_simple(&mut self) {
        if let Some(metalness) = self.vmt.extract_param("$metalness") {
            self.builder
                .socket_value("Metallic", Value::Float(metalness));
        }
    }

    fn handle_selfillum_simple(&mut self) {
        if !self.vmt.extract_param_or_default::<bool>("$selfillum")
            || !self.handle_texture("$selfillummask", None, ColorSpace::NonColor)
        {
            return;
        }

        self.builder.output("Emission", "$selfillummask", "color");
    }

    fn build_simple(&mut self) {
        self.builder
            .property("blend_method", Value::Enum("OPAQUE"))
            .property("shadow_method", Value::Enum("OPAQUE"))
            .socket_value("Specular", Value::Float(0.1))
            .socket_value("Roughness", Value::Float(0.9));

        self.handle_cull();

        if !self.handle_basetexture_simple() {
            self.handle_color();
        }

        self.handle_bumpmap_simple();

        if !self.handle_translucent_simple() && !self.handle_alphatest_simple() {
            self.handle_alpha();
        }

        if !self.handle_phong_simple() && !self.handle_envmap_simple() {
            self.handle_unlit();
        }

        self.handle_metal_simple();

        self.handle_selfillum_simple();
    }
}

// 4WayBlend material building
impl<'a, 'b> NormalMaterialBuilder<'a, 'b> {
    fn handle_texture_4wayblend(
        &mut self,
        parameter: &'static str,
        uv_scale_parameter: &'static str,
        color_space: ColorSpace,
    ) -> bool {
        self.builder.handle_texture_4wayblend(
            self.vmt,
            parameter,
            uv_scale_parameter,
            color_space,
            self.settings.texture_interpolation,
        )
    }

    fn get_blend_data(&self) -> FwbBlendData {
        let lum_starts = [
            "$texture1_lumstart",
            "$texture2_lumstart",
            "$texture3_lumstart",
            "$texture4_lumstart",
        ]
        .map(|parameter| self.vmt.extract_param(parameter).unwrap_or(0.0));

        let lum_ends = [
            "$texture1_lumend",
            "$texture2_lumend",
            "$texture3_lumend",
            "$texture4_lumend",
        ]
        .map(|parameter| self.vmt.extract_param(parameter).unwrap_or(1.0));

        let blend_starts = [
            "$texture2_blendstart",
            "$texture3_blendstart",
            "$texture4_blendstart",
        ]
        .map(|parameter| self.vmt.extract_param(parameter).unwrap_or(0.0));

        let blend_ends = [
            "$texture2_blendend",
            "$texture3_blendend",
            "$texture4_blendend",
        ]
        .map(|parameter| self.vmt.extract_param(parameter).unwrap_or(1.0));

        let bump_blend_factors = [
            "$texture2_bumpblendfactor",
            "$texture3_bumpblendfactor",
            "$texture4_bumpblendfactor",
        ]
        .map(|parameter| self.vmt.extract_param(parameter).unwrap_or(1.0));

        let detail_blend_factors = [
            "$detailblendfactor",
            "$detailblendfactor2",
            "$detailblendfactor3",
            "$detailblendfactor4",
        ]
        .map(|parameter| self.vmt.extract_param(parameter).unwrap_or(1.0));

        let lum_blend_factors = ["$lumblendfactor2", "$lumblendfactor3", "$lumblendfactor4"]
            .map(|parameter| self.vmt.extract_param(parameter).unwrap_or(1.0));

        FwbBlendData {
            lum_start: lum_starts,
            lum_end: lum_ends,
            blend_start: blend_starts,
            blend_end: blend_ends,
            bump_fac: bump_blend_factors,
            detail_fac: detail_blend_factors,
            lum_fac: lum_blend_factors,
        }
    }

    fn handle_basetextures(&mut self, d: &FwbBlendData) {
        use groups::FWB_FACTORS as FACS;
        use groups::MULTIBLEND_TEXTURE as MBT;
        use Value as V;

        for (parameter, uv_scale_parameter) in [
            ("$basetexture", "$texture1_uvscale"),
            ("$basetexture2", "$texture2_uvscale"),
            ("$basetexture3", "$texture3_uvscale"),
            ("$basetexture4", "$texture4_uvscale"),
        ] {
            if !self.handle_texture_4wayblend(parameter, uv_scale_parameter, ColorSpace::Srgb) {
                return;
            }
        }

        self.builder
            .input("factors")
            .pipeline(vec![&FACS])
            .link(&FACS, "fac2", Ref::new("vertex_color", "g"))
            .link(&FACS, "fac3", Ref::new("vertex_color", "b"))
            .link(&FACS, "fac4", Ref::new("vertex_color", "alpha"))
            .link(&FACS, "lum1", Ref::new("$basetexture", "color"))
            .link(&FACS, "lum2", Ref::new("$basetexture2", "color"))
            .link(&FACS, "lum3", Ref::new("$basetexture3", "color"))
            .link(&FACS, "lum4", Ref::new("$basetexture4", "color"))
            .link(&FACS, "lumstart1", V::Float(d.lum_start[0]))
            .link(&FACS, "lumstart2", V::Float(d.lum_start[1]))
            .link(&FACS, "lumstart3", V::Float(d.lum_start[2]))
            .link(&FACS, "lumstart4", V::Float(d.lum_start[3]))
            .link(&FACS, "lumend1", V::Float(d.lum_end[0]))
            .link(&FACS, "lumend2", V::Float(d.lum_end[1]))
            .link(&FACS, "lumend3", V::Float(d.lum_end[2]))
            .link(&FACS, "lumend4", V::Float(d.lum_end[3]))
            .link(&FACS, "lumfac2", V::Float(d.lum_fac[0]))
            .link(&FACS, "lumfac3", V::Float(d.lum_fac[1]))
            .link(&FACS, "lumfac4", V::Float(d.lum_fac[2]))
            .link(&FACS, "blendstart2", V::Float(d.blend_start[0]))
            .link(&FACS, "blendstart3", V::Float(d.blend_start[1]))
            .link(&FACS, "blendstart4", V::Float(d.blend_start[2]))
            .link(&FACS, "blendend2", V::Float(d.blend_end[0]))
            .link(&FACS, "blendend3", V::Float(d.blend_end[1]))
            .link(&FACS, "blendend4", V::Float(d.blend_end[2]));

        self.builder
            .input("base")
            .push(&MBT)
            .link(&MBT, "fac1", Ref::new("factors", "fac1"))
            .link(&MBT, "fac2", Ref::new("factors", "fac2"))
            .link(&MBT, "fac3", Ref::new("factors", "fac3"))
            .link(&MBT, "color", Ref::new("$basetexture", "color"))
            .link(&MBT, "color2", Ref::new("$basetexture2", "color"))
            .link(&MBT, "color3", Ref::new("$basetexture3", "color"))
            .link(&MBT, "color4", Ref::new("$basetexture4", "color"))
            .link(&MBT, "alpha", Ref::new("$basetexture", "alpha"))
            .link(&MBT, "alpha2", Ref::new("$basetexture2", "alpha"))
            .link(&MBT, "alpha3", Ref::new("$basetexture3", "alpha"))
            .link(&MBT, "alpha4", Ref::new("$basetexture4", "alpha"));

        self.builder.output("Base Color", "base", "color");
    }

    fn handle_bumpmaps(&mut self, d: &FwbBlendData) -> bool {
        use groups::MULTIBLEND_VALUE as MBV;

        if !self.handle_texture_4wayblend("$bumpmap", "$texture1_uvscale", ColorSpace::NonColor) {
            return false;
        }

        let bump_fac = self
            .handle_2_bumpmaps(d)
            .or_else(|| self.handle_4_bumpmaps())
            .unwrap_or_else(|| {
                self.builder
                    .input("bump_fac")
                    .pipeline(vec![&groups::MULTIBLEND_VALUE])
                    .link(&MBV, "fac1", Ref::new("factors", "fac1"))
                    .link(&MBV, "fac2", Ref::new("factors", "fac2"))
                    .link(&MBV, "fac3", Ref::new("factors", "fac3"))
                    .link(&MBV, "val1", Value::Float(1.0))
                    .link(&MBV, "val2", Value::Float(d.bump_fac[0]))
                    .link(&MBV, "val3", Value::Float(d.bump_fac[1]))
                    .link(&MBV, "val4", Value::Float(d.bump_fac[2]))
                    .socket("val")
                    .into()
            });

        let output = self.builder.output("Normal", "$bumpmap", "color");

        if self.vmt.extract_param_or_default("$ssbump") {
            output
                .push(&groups::SSBUMP_CONVERTER)
                .link_input(&groups::SSBUMP_CONVERTER, "image");
        } else {
            output
                .push(&groups::DX_NORMAL_MAP_CONVERTER)
                .link_input(&groups::DX_NORMAL_MAP_CONVERTER, "image");
        }

        output
            .push(&groups::NORMAL_MAP)
            .link(&groups::NORMAL_MAP, "strength", bump_fac);

        true
    }

    fn handle_2_bumpmaps(&mut self, d: &FwbBlendData) -> Option<InputLink> {
        use groups::BLEND_3_VALUES as B3V;

        if !self.handle_texture_4wayblend("$bumpmap2", "$texture2_uvscale", ColorSpace::NonColor) {
            return None;
        }

        self.builder
            .input("$bumpmap")
            .push(&groups::BLEND_TEXTURE)
            .link(
                &groups::BLEND_TEXTURE,
                "color2",
                Ref::new("$bumpmap2", "color"),
            )
            .link(
                &groups::BLEND_TEXTURE,
                "alpha2",
                Ref::new("$bumpmap2", "alpha"),
            )
            .link(&groups::BLEND_TEXTURE, "fac", Ref::new("factors", "fac1"));

        let bump_fac = self
            .builder
            .input("bump_fac")
            .pipeline(vec![&B3V])
            .link(&B3V, "fac1", Ref::new("factors", "fac2"))
            .link(&B3V, "fac2", Ref::new("factors", "fac3"))
            .link(&B3V, "val1", Value::Float(1.0))
            .link(&B3V, "val2", Value::Float(d.bump_fac[1]))
            .link(&B3V, "val3", Value::Float(d.bump_fac[2]))
            .socket("val");

        Some(bump_fac.into())
    }

    fn handle_4_bumpmaps(&mut self) -> Option<InputLink> {
        use groups::MULTIBLEND_TEXTURE as MBT;

        let has_bumpmaps = [
            ("$basenormalmap2", "$texture2_uvscale"),
            ("$basenormalmap3", "$texture3_uvscale"),
            ("$basenormalmap4", "$texture4_uvscale"),
        ]
        .into_iter()
        .all(|(parameter, uv_scale_parameter)| {
            self.handle_texture_4wayblend(parameter, uv_scale_parameter, ColorSpace::NonColor)
        });

        if !has_bumpmaps {
            return None;
        }
        self.builder
            .input("$bumpmap")
            .push(&MBT)
            .link(&MBT, "fac1", Ref::new("factors", "fac1"))
            .link(&MBT, "fac2", Ref::new("factors", "fac2"))
            .link(&MBT, "fac3", Ref::new("factors", "fac3"))
            .link(&MBT, "color2", Ref::new("$basenormalmap2", "color"))
            .link(&MBT, "color3", Ref::new("$basenormalmap3", "color"))
            .link(&MBT, "color4", Ref::new("$basenormalmap4", "color"))
            .link(&MBT, "alpha2", Ref::new("$basenormalmap2", "alpha"))
            .link(&MBT, "alpha3", Ref::new("$basenormalmap3", "alpha"))
            .link(&MBT, "alpha4", Ref::new("$basenormalmap4", "alpha"));

        let bump_fac = Value::Float(1.0);

        Some(bump_fac.into())
    }

    fn handle_detail_fwb(&mut self, d: &FwbBlendData) {
        use groups::MULTIBLEND_VALUE as MBV;

        let detail_mode_supported =
            self.vmt.extract_param_or_default::<u8>("$detailblendmode") == 0;

        if !detail_mode_supported
            || !self.handle_texture_scaled(
                "$detail",
                "$detailtexturetransform",
                "$detailscale",
                ColorSpace::NonColor,
            )
        {
            return;
        }

        let blend_fac = self
            .builder
            .input("detail_fac")
            .pipeline(vec![&groups::MULTIBLEND_VALUE])
            .link(&MBV, "fac1", Ref::new("factors", "fac1"))
            .link(&MBV, "fac2", Ref::new("factors", "fac2"))
            .link(&MBV, "fac3", Ref::new("factors", "fac3"))
            .link(&MBV, "val1", Value::Float(d.detail_fac[0]))
            .link(&MBV, "val2", Value::Float(d.detail_fac[1]))
            .link(&MBV, "val3", Value::Float(d.detail_fac[2]))
            .link(&MBV, "val4", Value::Float(d.detail_fac[3]))
            .socket("val");

        self.builder
            .input("base")
            .push(&groups::DETAIL_TEXTURE)
            .link(
                &groups::DETAIL_TEXTURE,
                "detail",
                Ref::new("$detail", "color"),
            )
            .link(&groups::DETAIL_TEXTURE, "fac", blend_fac);
    }

    fn build_fwb(&mut self) {
        self.builder
            .property("blend_method", Value::Enum("OPAQUE"))
            .property("shadow_method", Value::Enum("OPAQUE"))
            .socket_value("Specular", Value::Float(0.1))
            .socket_value("Roughness", Value::Float(0.9));

        self.builder
            .input("vertex_color")
            .pipeline(vec![&groups::SEPARATED_VERTEX_COLOR]);

        let blend_data = self.get_blend_data();

        self.handle_basetextures(&blend_data);

        if !self.handle_bumpmaps(&blend_data) {
            self.handle_ssbump_detail();
        }

        self.handle_detail_fwb(&blend_data);

        self.handle_cull();

        if !self.handle_envmap("base") {
            self.handle_unlit();
        }
    }
}

pub fn build_material(vmt: &mut LoadedVmt, settings: &Settings) -> BuiltMaterialData {
    let info = vmt.info();

    if info.no_draw() && !settings.editor_materials {
        build_nodraw_material()
    } else if vmt.extract_param_or_default("%compilewater") {
        build_water_material(vmt, settings)
    } else {
        NormalMaterialBuilder::new(vmt, settings).build()
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn build_nodraw_material_no_panic() {
        build_nodraw_material();
    }
}
