pub fn srgb_to_linear(srgb: f32) -> f32 {
    if srgb <= 0.040_448_237 {
        srgb / 12.92
    } else {
        ((srgb + 0.055) / 1.055).powf(2.4)
    }
}

pub fn linear_to_srgb(linear: f32) -> f32 {
    if linear <= 0.003_130_668_5 {
        linear * 12.92
    } else {
        1.055 * linear.powf(1.0 / 2.4) - 0.055
    }
}
