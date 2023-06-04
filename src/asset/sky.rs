use std::f32::consts::{FRAC_PI_2, PI};
use std::io::Cursor;

use float_ord::FloatOrd;
use image::{ImageBuffer, ImageOutputFormat, Pixel, Rgba32FImage, RgbaImage};
use pyo3::prelude::*;

use plumber_core::asset_vmt::skybox::{SkyBox, SkyBoxData};

#[pyclass(module = "plumber", name = "SkyEqui")]
pub struct PySkyEqui {
    name: String,
    width: u32,
    height: u32,
    format: &'static str,
    data: Vec<u8>,
}

#[pymethods]
impl PySkyEqui {
    fn name(&self) -> &str {
        &self.name
    }

    fn width(&self) -> u32 {
        self.width
    }

    fn height(&self) -> u32 {
        self.height
    }

    fn format(&self) -> &str {
        self.format
    }

    fn bytes(&self) -> &[u8] {
        &self.data
    }
}

impl PySkyEqui {
    pub fn new(skybox: SkyBox, out_height: Option<u32>) -> Self {
        let equi = to_equi(skybox.data, out_height);

        let mut data = Vec::new();
        let format;
        let width;
        let height;

        match equi {
            Equi::Hdr(image) => {
                width = image.width();
                height = image.height();

                image
                    .write_to(&mut Cursor::new(&mut data), ImageOutputFormat::OpenExr)
                    .unwrap();
                format = "exr";
            }
            Equi::Sdr(image) => {
                width = image.width();
                height = image.height();

                image
                    .write_to(&mut Cursor::new(&mut data), ImageOutputFormat::Tga)
                    .unwrap();
                format = "tga";
            }
        }

        Self {
            name: skybox.name.into_string(),
            width,
            height,
            format,
            data,
        }
    }
}

/// Returns a 3D vector pointing to the corresponding pixel location inside a sphere.
fn spherical_vector(x: u32, y: u32, width: u32, height: u32) -> [f32; 3] {
    let theta = (2.0 * x as f32 / width as f32 - 1.0) * PI;
    let phi = (2.0 * y as f32 / height as f32 - 1.0) * FRAC_PI_2;

    let (phi_sin, phi_cos) = phi.sin_cos();
    let (theta_sin, theta_cos) = theta.sin_cos();

    [phi_cos * theta_cos, phi_sin, phi_cos * theta_sin]
}

/// Maps skybox faces to indices
#[repr(usize)]
#[derive(Clone, Copy)]
enum SkyboxFace {
    Left = 0,
    Right = 1,
    Top = 2,
    Bottom = 3,
    Front = 4,
    Back = 5,
}

impl SkyboxFace {
    /// Returns the face which the given vector lies on
    fn from_vector(vec: [f32; 3]) -> SkyboxFace {
        let (largest_magnitude_index, _) = vec
            .into_iter()
            .map(f32::abs)
            .enumerate()
            .max_by_key(|(_i, magn)| FloatOrd(*magn))
            .expect("iterator cannot be empty");

        let positive = vec[largest_magnitude_index] > 0.0;

        match largest_magnitude_index {
            0 if positive => SkyboxFace::Right,
            0 => SkyboxFace::Left,
            1 if positive => SkyboxFace::Bottom,
            1 => SkyboxFace::Top,
            2 if positive => SkyboxFace::Front,
            2 => SkyboxFace::Back,
            _ => unreachable!("index cannot be larger than 2"),
        }
    }

    /// Returns the vector's 2D coordinates on the face
    fn raw_coordinates(self, vec: [f32; 3]) -> [f32; 2] {
        let [x, y, z] = vec;

        let (xc, yc, ma) = match self {
            SkyboxFace::Left => (-z, y, x),
            SkyboxFace::Right => (z, y, x),
            SkyboxFace::Top => (z, x, y),
            SkyboxFace::Bottom => (z, -x, y),
            SkyboxFace::Front => (-x, y, z),
            SkyboxFace::Back => (x, y, z),
        };

        [(xc / ma.abs() + 1.0) / 2.0, (yc / ma.abs() + 1.0) / 2.0]
    }
}

/// Converts raw coordinates into pixel coordinates
#[allow(clippy::cast_possible_truncation, clippy::cast_sign_loss)]
fn pixel_coordinates(raw_coords: [f32; 2], cubemap_dim: u32) -> [f32; 2] {
    raw_coords.map(|c| c.clamp(0.0, 1.0) * (cubemap_dim - 1) as f32)
}

/// Converts equirectangular image coordinates into a skybox face and coordinates.
fn equi_coords_to_skybox(
    x: u32,
    y: u32,
    out_width: u32,
    out_height: u32,
    cubemap_dim: u32,
) -> (SkyboxFace, [f32; 2]) {
    let vec = spherical_vector(x, y, out_width, out_height);
    let face = SkyboxFace::from_vector(vec);
    let raw_coords = face.raw_coordinates(vec);
    let pixel_coords = pixel_coordinates(raw_coords, cubemap_dim);

    (face, pixel_coords)
}

pub enum Equi {
    Hdr(Rgba32FImage),
    Sdr(RgbaImage),
}

pub fn to_equi(skybox: SkyBoxData, out_height: Option<u32>) -> Equi {
    match skybox {
        SkyBoxData::Sdr(images) => Equi::Sdr(to_equi_inner(&images, out_height)),
        SkyBoxData::Hdr(images) => Equi::Hdr(to_equi_inner(&images, out_height)),
    }
}

trait SubPixelLerp {
    fn lerp(self, other: Self, factor: f32) -> Self;
}

impl SubPixelLerp for f32 {
    fn lerp(self, other: Self, factor: f32) -> Self {
        self * (1.0 - factor) + other * factor
    }
}

impl SubPixelLerp for u8 {
    #[allow(clippy::cast_possible_truncation, clippy::cast_sign_loss)]
    fn lerp(self, other: Self, factor: f32) -> Self {
        let a = f32::from(self);
        let b = f32::from(other);

        (a * (1.0 - factor) + b * factor) as u8
    }
}

fn to_equi_inner<P: Pixel>(
    images: &[ImageBuffer<P, Vec<P::Subpixel>>; 6],
    out_height: Option<u32>,
) -> ImageBuffer<P, Vec<P::Subpixel>>
where
    P::Subpixel: SubPixelLerp,
{
    let cubemap_dim = images
        .iter()
        .flat_map(|i| [i.width(), i.height()])
        .max()
        .expect("iterator cannot be empty");

    let out_height = out_height.unwrap_or(cubemap_dim * 2);
    let out_width = out_height * 2;

    ImageBuffer::from_fn(out_width, out_height, |x, y| {
        let (face, [x, y]) = equi_coords_to_skybox(x, y, out_width, out_height, cubemap_dim);

        let image = &images[face as usize];
        bilinear_interpolate(image, x, y)
    })
}

#[allow(clippy::cast_possible_truncation, clippy::cast_sign_loss)]
fn bilinear_interpolate<P: Pixel>(image: &ImageBuffer<P, Vec<P::Subpixel>>, x: f32, y: f32) -> P
where
    P::Subpixel: SubPixelLerp,
{
    let width = image.width();
    let height = image.height();

    let x_max = width - 1;
    let y_max = height - 1;

    let x0 = (x as u32).min(x_max);
    let x1 = (x0 + 1).min(x_max);

    let y0 = (y as u32).min(y_max);
    let y1 = (y0 + 1).min(y_max);

    let x_factor = x.fract();
    let y_factor = y.fract();

    let a = lerp_pixel(image.get_pixel(x0, y0), image.get_pixel(x1, y0), x_factor);
    let b = lerp_pixel(image.get_pixel(x0, y1), image.get_pixel(x1, y1), x_factor);

    lerp_pixel(&a, &b, y_factor)
}

fn lerp_pixel<P: Pixel>(a: &P, b: &P, factor: f32) -> P
where
    P::Subpixel: SubPixelLerp,
{
    a.map2(b, |a, b| a.lerp(b, factor))
}
