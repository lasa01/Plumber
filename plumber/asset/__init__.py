from typing import Optional
from bpy.types import Context, Collection

from ..plumber import (
    BuiltBrushEntity,
    BuiltOverlay,
    LoadedProp,
    Material,
    Model,
    Light,
    EnvLight,
    SkyCamera,
    SpotLight,
    SkyEqui,
    Texture,
)
from .material import import_material, import_texture
from .model import ModelTracker
from .brush import import_brush
from .overlay import import_overlay
from .prop import apply_armatures, import_prop
from .light import import_light, import_spot_light, import_env_light
from .sky_camera import import_sky_camera
from .sky_equi import import_sky_equi


class AssetCallbacks:
    def __init__(
        self,
        context: Context,
        main_collection: Optional[Collection] = None,
        brush_collection: Optional[Collection] = None,
        overlay_collection: Optional[Collection] = None,
        prop_collection: Optional[Collection] = None,
        light_collection: Optional[Collection] = None,
        apply_armatures: bool = False,
    ) -> None:
        self.context = context
        self.model_tracker = ModelTracker()
        self.armatures_to_apply = []

        self.main_collection = main_collection or context.collection
        self.brush_collection = brush_collection or self.main_collection
        self.overlay_collection = overlay_collection or self.main_collection
        self.prop_collection = prop_collection or self.main_collection
        self.light_collection = light_collection or self.main_collection

        self.apply_armatures = apply_armatures

    def material(self, material: Material) -> None:
        import_material(material)

    def texture(self, texture: Texture) -> None:
        import_texture(texture)

    def model(self, model: Model) -> None:
        self.model_tracker.import_model(model, self.prop_collection)

    def brush(self, brush: BuiltBrushEntity) -> None:
        import_brush(brush, self.brush_collection)

    def overlay(self, overlay: BuiltOverlay) -> None:
        import_overlay(overlay, self.overlay_collection)

    def prop(self, prop: LoadedProp) -> None:
        import_prop(
            prop,
            self.prop_collection,
            self.model_tracker,
            self.apply_armatures,
            self.armatures_to_apply,
        )

    def light(self, light: Light) -> None:
        import_light(light, self.light_collection)

    def spot_light(self, light: SpotLight) -> None:
        import_spot_light(light, self.light_collection)

    def env_light(self, light: EnvLight) -> None:
        import_env_light(light, self.context, self.light_collection)

    def sky_camera(self, sky_camera: SkyCamera) -> None:
        import_sky_camera(sky_camera, self.context, self.main_collection)

    def sky_equi(self, sky_equi: SkyEqui) -> None:
        import_sky_equi(sky_equi, self.context)

    def finish(self) -> None:
        apply_armatures(self.armatures_to_apply)
