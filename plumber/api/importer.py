"""
Asset import functionality for individual and batch imports.
"""

from typing import Any, Dict, List, Optional, Union, Callable
from enum import Enum

from .exceptions import AssetImportError
from .filesystem import GameFileSystem


class AssetType(Enum):
    """Types of assets that can be imported."""

    VMF = "vmf"
    MDL = "mdl"
    VMT = "vmt"
    VTF = "vtf"


class ImportJob:
    """Represents a single import job for parallel processing."""

    def __init__(self, asset_type: AssetType, path: str, from_game: bool = True):
        """
        Initialize an import job.

        Args:
            asset_type: Type of asset to import
            path: Path to the asset file
            from_game: Whether to load from game file system or OS file system
        """
        self.asset_type = asset_type
        self.path = path
        self.from_game = from_game


class ParallelImportBuilder:
    """
    Builder for creating custom parallel import processes.

    Ensures that each asset is imported only once during the process, even if there are
    dependencies between assets (e.g., a material depends on a texture) or if duplicate
    imports are requested. This deduplication happens automatically across all queued
    import jobs.
    """

    def __init__(
        self,
        file_system: GameFileSystem,
        # Material settings
        material_import_materials: bool = True,
        material_simple_materials: bool = False,
        material_texture_format: str = "Png",
        material_texture_interpolation: str = "Linear",
        material_allow_culling: bool = False,
        material_editor_materials: bool = False,
        # VMF settings
        vmf_import_lights: bool = True,
        vmf_light_factor: float = 1.0,
        vmf_sun_factor: float = 1.0,
        vmf_ambient_factor: float = 1.0,
        vmf_import_sky_camera: bool = True,
        vmf_sky_equi_height: int = 1024,
        vmf_import_unknown_entities: bool = False,
        vmf_import_brushes: bool = True,
        vmf_import_overlays: bool = True,
        vmf_epsilon: float = 0.01,
        vmf_cut_threshold: float = 0.1,
        vmf_merge_solids: str = "MERGE",
        vmf_invisible_solids: str = "SKIP",
        vmf_import_props: bool = True,
        vmf_import_entities: bool = True,
        vmf_import_sky: bool = True,
        vmf_scale: float = 1.0,
        vmf_brush_collection=None,
        vmf_overlay_collection=None,
        vmf_prop_collection=None,
        vmf_light_collection=None,
        vmf_entity_collection=None,
        # MDL settings
        mdl_scale: float = 1.0,
        mdl_target_fps: float = 30.0,
        mdl_remove_animations: bool = False,
        mdl_import_animations: bool = True,
        mdl_apply_armatures: bool = False,
        # Collection settings
        main_collection=None,
    ):
        """
        Initialize the builder with all import settings.

        Args:
            file_system: GameFileSystem to use for imports

            # Material settings
            material_import_materials: Import materials
            material_simple_materials: Import simple, exporter-friendly materials
            material_texture_format: Texture format ("Png", "Tga")
            material_texture_interpolation: Texture interpolation ("Linear", "Closest", "Cubic", "Smart")
            material_allow_culling: Enable backface culling
            material_editor_materials: Import editor materials instead of invisible ones

            # VMF settings
            vmf_import_lights: Import lighting
            vmf_light_factor: Light brightness multiplier
            vmf_sun_factor: Sunlight brightness multiplier
            vmf_ambient_factor: Ambient light brightness multiplier
            vmf_import_sky_camera: Import sky camera
            vmf_sky_equi_height: Sky equirectangular texture height
            vmf_import_unknown_entities: Import unknown entities as empties
            vmf_import_brushes: Import brush geometry
            vmf_import_overlays: Import overlay geometry
            vmf_epsilon: Geometry epsilon for calculations
            vmf_cut_threshold: Cut threshold for geometry
            vmf_merge_solids: How to merge solids ("MERGE", "SEPARATE")
            vmf_invisible_solids: How to handle invisible solids ("IMPORT", "SKIP")
            vmf_import_props: Import props
            vmf_import_entities: Import entities
            vmf_import_sky: Import skybox
            vmf_scale: VMF-specific scale factor
            vmf_brush_collection: Collection for brushes (VMF imports)
            vmf_overlay_collection: Collection for overlays (VMF imports)
            vmf_prop_collection: Collection for props (VMF imports)
            vmf_light_collection: Collection for lights (VMF imports)
            vmf_entity_collection: Collection for entities (VMF imports)

            # MDL settings
            mdl_scale: Global scale factor for models
            mdl_target_fps: Target FPS for animations
            mdl_remove_animations: Remove animations from imported models
            mdl_import_animations: Import model animations
            mdl_apply_armatures: Apply armatures to models

            # Collection settings
            main_collection: Main collection for imports
        """
        self._file_system = file_system
        self._jobs: List[ImportJob] = []

        # Store all settings to be used for all imports
        self._all_settings = {
            # Material settings (using API prefixed names)
            "material_import_materials": material_import_materials,
            "material_simple_materials": material_simple_materials,
            "material_texture_format": material_texture_format,
            "material_texture_interpolation": material_texture_interpolation,
            "material_allow_culling": material_allow_culling,
            "material_editor_materials": material_editor_materials,
            # VMF settings (using API prefixed names)
            "vmf_import_lights": vmf_import_lights,
            "vmf_light_factor": vmf_light_factor,
            "vmf_sun_factor": vmf_sun_factor,
            "vmf_ambient_factor": vmf_ambient_factor,
            "vmf_import_sky_camera": vmf_import_sky_camera,
            "vmf_sky_equi_height": vmf_sky_equi_height,
            "vmf_import_unknown_entities": vmf_import_unknown_entities,
            "vmf_import_brushes": vmf_import_brushes,
            "vmf_import_overlays": vmf_import_overlays,
            "vmf_epsilon": vmf_epsilon,
            "vmf_cut_threshold": vmf_cut_threshold,
            "vmf_merge_solids": vmf_merge_solids,
            "vmf_invisible_solids": vmf_invisible_solids,
            "vmf_import_props": vmf_import_props,
            "vmf_import_entities": vmf_import_entities,
            "vmf_import_sky": vmf_import_sky,
            "vmf_scale": vmf_scale,
            # MDL settings (using API prefixed names)
            "mdl_scale": mdl_scale,
            "mdl_target_fps": mdl_target_fps,
            "mdl_remove_animations": mdl_remove_animations,
            "mdl_import_animations": mdl_import_animations,
            "mdl_apply_armatures": mdl_apply_armatures,
        }

        # Store collection settings
        self._collection_settings = {
            "main_collection": main_collection,
            "brush_collection": vmf_brush_collection,
            "overlay_collection": vmf_overlay_collection,
            "prop_collection": vmf_prop_collection,
            "light_collection": vmf_light_collection,
            "entity_collection": vmf_entity_collection,
        }

    def add_vmf(self, path: str, from_game: bool = True) -> "ParallelImportBuilder":
        """
        Add a VMF import job.

        Args:
            path: Path to VMF file
            from_game: Whether to load from game file system

        Returns:
            Self for method chaining
        """
        self._jobs.append(ImportJob(AssetType.VMF, path, from_game))
        return self

    def add_mdl(self, path: str, from_game: bool = True) -> "ParallelImportBuilder":
        """
        Add an MDL import job.

        Args:
            path: Path to MDL file
            from_game: Whether to load from game file system

        Returns:
            Self for method chaining
        """
        self._jobs.append(ImportJob(AssetType.MDL, path, from_game))
        return self

    def add_vmt(self, path: str, from_game: bool = True) -> "ParallelImportBuilder":
        """
        Add a VMT import job.

        Args:
            path: Path to VMT file
            from_game: Whether to load from game file system

        Returns:
            Self for method chaining
        """
        self._jobs.append(ImportJob(AssetType.VMT, path, from_game))
        return self

    def add_vtf(self, path: str, from_game: bool = True) -> "ParallelImportBuilder":
        """
        Add a VTF import job.

        Args:
            path: Path to VTF file
            from_game: Whether to load from game file system

        Returns:
            Self for method chaining
        """
        self._jobs.append(ImportJob(AssetType.VTF, path, from_game))
        return self

    def execute(self, context=None) -> None:
        """
        Execute all import jobs in parallel.

        Args:
            context: Blender context (uses bpy.context if None)

        Raises:
            AssetImportError: If parallel import execution fails
        """
        if not self._jobs:
            return

        if context is None:
            import bpy

            context = bpy.context

        try:
            # Use the new Rust API importer for better performance
            import plumber

            callbacks = _create_asset_callbacks(context, **self._collection_settings)
            threads = _get_threads_suggestion(context)

            # Create API importer with all settings
            api_importer = plumber.ApiImporter(
                self._file_system._fs,
                callbacks,
                threads,
                **self._all_settings,
            )

            # Add all jobs to the API importer (only path and from_game)
            for job in self._jobs:
                if job.asset_type == AssetType.VMF:
                    api_importer.add_vmf_job(job.path, job.from_game)
                elif job.asset_type == AssetType.MDL:
                    api_importer.add_mdl_job(job.path, job.from_game)
                elif job.asset_type == AssetType.VMT:
                    api_importer.add_vmt_job(job.path, job.from_game)
                elif job.asset_type == AssetType.VTF:
                    api_importer.add_vtf_job(job.path, job.from_game)

            # Execute all jobs
            api_importer.execute_jobs()

            # Clear jobs after execution
            self._jobs.clear()

        except Exception as e:
            raise AssetImportError(f"Parallel import execution failed: {e}") from e

    def clear(self) -> "ParallelImportBuilder":
        """Clear all import jobs."""
        self._jobs.clear()
        return self

    @property
    def job_count(self) -> int:
        """Get the number of queued import jobs."""
        return len(self._jobs)


def _create_asset_callbacks(context, **options) -> Any:
    from ..asset import AssetCallbacks

    # Extract collection options - default to main collection if not specified
    main_collection = options.get("main_collection")
    if main_collection is None:
        main_collection = context.scene.collection

    brush_collection = options.get("brush_collection")
    if brush_collection is None:
        brush_collection = main_collection

    overlay_collection = options.get("overlay_collection")
    if overlay_collection is None:
        overlay_collection = main_collection

    prop_collection = options.get("prop_collection")
    if prop_collection is None:
        prop_collection = main_collection

    light_collection = options.get("light_collection")
    if light_collection is None:
        light_collection = main_collection

    entity_collection = options.get("entity_collection")
    if entity_collection is None:
        entity_collection = main_collection

    apply_armatures = options.get("apply_armatures", False)

    return AssetCallbacks(
        context,
        main_collection=main_collection,
        brush_collection=brush_collection,
        overlay_collection=overlay_collection,
        prop_collection=prop_collection,
        light_collection=light_collection,
        entity_collection=entity_collection,
        apply_armatures=apply_armatures,
    )


def _get_threads_suggestion(context) -> int:
    """Get thread count suggestion from preferences."""
    try:
        from .. import __package__ as ADDON_NAME

        preferences = context.preferences.addons[ADDON_NAME].preferences
        return max(1, preferences.threads - 1)  # Leave room for Blender's thread
    except (KeyError, AttributeError):
        return 1


def import_vmf(
    file_system: GameFileSystem,
    path: str,
    from_game: bool = True,
    context=None,
    # Material settings
    material_import_materials: bool = True,
    material_simple_materials: bool = False,
    material_texture_format: str = "Png",
    material_texture_interpolation: str = "Linear",
    material_allow_culling: bool = False,
    material_editor_materials: bool = False,
    # VMF settings
    vmf_import_lights: bool = True,
    vmf_light_factor: float = 1.0,
    vmf_sun_factor: float = 1.0,
    vmf_ambient_factor: float = 1.0,
    vmf_import_sky_camera: bool = True,
    vmf_sky_equi_height: int = 1024,
    vmf_import_unknown_entities: bool = False,
    vmf_import_brushes: bool = True,
    vmf_import_overlays: bool = True,
    vmf_epsilon: float = 0.01,
    vmf_cut_threshold: float = 0.1,
    vmf_merge_solids: str = "MERGE",
    vmf_invisible_solids: str = "SKIP",
    vmf_import_props: bool = True,
    vmf_import_entities: bool = True,
    vmf_import_sky: bool = True,
    vmf_scale: float = 1.0,
    # MDL settings
    mdl_scale: float = 1.0,
    mdl_target_fps: float = 30.0,
    mdl_remove_animations: bool = False,
    mdl_import_animations: bool = True,
    mdl_apply_armatures: bool = False,
    # Collection options
    **options,
) -> None:
    """
    Import a VMF (Valve Map Format) file.

    Args:
        file_system: GameFileSystem to use for asset loading
        path: Path to VMF file
        from_game: Whether to load from game file system or OS file system
        context: Blender context (uses bpy.context if None)

        # Material settings
        material_import_materials: Import materials
        material_simple_materials: Import simple, exporter-friendly materials
        material_texture_format: Texture format ("Png", "Tga")
        material_texture_interpolation: Texture interpolation ("Linear", "Closest", "Cubic", "Smart")
        material_allow_culling: Enable backface culling
        material_editor_materials: Import editor materials instead of invisible ones

        # VMF settings
        vmf_import_lights: Import lighting
        vmf_light_factor: Light brightness multiplier
        vmf_sun_factor: Sunlight brightness multiplier
        vmf_ambient_factor: Ambient light brightness multiplier
        vmf_import_sky_camera: Import sky camera
        vmf_sky_equi_height: Sky equirectangular texture height
        vmf_import_unknown_entities: Import unknown entities as empties
        vmf_import_brushes: Import brush geometry
        vmf_import_overlays: Import overlay geometry
        vmf_epsilon: Geometry epsilon for calculations
        vmf_cut_threshold: Cut threshold for geometry
        vmf_merge_solids: How to merge solids ("MERGE", "SEPARATE")
        vmf_invisible_solids: How to handle invisible solids ("IMPORT", "SKIP")
        vmf_import_props: Import props
        vmf_import_entities: Import entities
        vmf_import_sky: Import skybox
        vmf_scale: VMF-specific scale factor

        # MDL settings
        mdl_scale: Global scale factor for models
        mdl_target_fps: Target FPS for animations
        mdl_remove_animations: Remove animations from imported models
        mdl_import_animations: Import model animations
        mdl_apply_armatures: Apply armatures to models

        # Collection options
        main_collection: Main collection for imports
        vmf_brush_collection: Collection for brushes (VMF imports)
        vmf_overlay_collection: Collection for overlays (VMF imports)
        vmf_prop_collection: Collection for props (VMF imports)
        vmf_light_collection: Collection for lights (VMF imports)
        vmf_entity_collection: Collection for entities (VMF imports)

    Raises:
        AssetImportError: If import fails
    """
    if context is None:
        import bpy

        context = bpy.context

    try:
        import plumber

        callbacks = _create_asset_callbacks(context, **options)
        threads = _get_threads_suggestion(context)

        api_importer = plumber.ApiImporter(
            file_system._fs,
            callbacks,
            threads,
            # Material settings
            material_import_materials=material_import_materials,
            material_simple_materials=material_simple_materials,
            material_texture_format=material_texture_format,
            material_texture_interpolation=material_texture_interpolation,
            material_allow_culling=material_allow_culling,
            material_editor_materials=material_editor_materials,
            # VMF settings
            vmf_import_lights=vmf_import_lights,
            vmf_light_factor=vmf_light_factor,
            vmf_sun_factor=vmf_sun_factor,
            vmf_ambient_factor=vmf_ambient_factor,
            vmf_import_sky_camera=vmf_import_sky_camera,
            vmf_sky_equi_height=vmf_sky_equi_height,
            vmf_import_unknown_entities=vmf_import_unknown_entities,
            vmf_import_brushes=vmf_import_brushes,
            vmf_import_overlays=vmf_import_overlays,
            vmf_epsilon=vmf_epsilon,
            vmf_cut_threshold=vmf_cut_threshold,
            vmf_merge_solids=vmf_merge_solids,
            vmf_invisible_solids=vmf_invisible_solids,
            vmf_import_props=vmf_import_props,
            vmf_import_entities=vmf_import_entities,
            vmf_import_sky=vmf_import_sky,
            vmf_scale=vmf_scale,
            # MDL settings
            mdl_scale=mdl_scale,
            mdl_target_fps=mdl_target_fps,
            mdl_remove_animations=mdl_remove_animations,
            mdl_import_animations=mdl_import_animations,
            mdl_apply_armatures=mdl_apply_armatures,
        )

        api_importer.add_vmf_job(path, from_game)
        api_importer.execute_jobs()

    except Exception as e:
        raise AssetImportError(f"VMF import failed: {e}") from e


def import_mdl(
    file_system: GameFileSystem,
    path: str,
    from_game: bool = True,
    context=None,
    # Material settings
    material_import_materials: bool = True,
    material_simple_materials: bool = False,
    material_texture_format: str = "Png",
    material_texture_interpolation: str = "Linear",
    material_allow_culling: bool = False,
    material_editor_materials: bool = False,
    # VMF settings (used for models that reference other assets)
    vmf_import_lights: bool = True,
    vmf_light_factor: float = 1.0,
    vmf_sun_factor: float = 1.0,
    vmf_ambient_factor: float = 1.0,
    vmf_import_sky_camera: bool = True,
    vmf_sky_equi_height: int = 1024,
    vmf_import_unknown_entities: bool = False,
    # MDL settings
    mdl_scale: float = 1.0,
    mdl_target_fps: float = 30.0,
    mdl_remove_animations: bool = False,
    mdl_import_animations: bool = True,
    mdl_apply_armatures: bool = False,
    # Collection options
    **options,
) -> None:
    """
    Import an MDL (Source Model) file.

    Args:
        file_system: GameFileSystem to use for asset loading
        path: Path to MDL file
        from_game: Whether to load from game file system or OS file system
        context: Blender context (uses bpy.context if None)

        # Material settings
        material_import_materials: Import materials
        material_simple_materials: Import simple, exporter-friendly materials
        material_texture_format: Texture format ("Png", "Tga")
        material_texture_interpolation: Texture interpolation ("Linear", "Closest", "Cubic", "Smart")
        material_allow_culling: Enable backface culling
        material_editor_materials: Import editor materials instead of invisible ones

        # VMF settings (used for models that reference other assets)
        vmf_import_lights: Import lighting
        vmf_light_factor: Light brightness multiplier
        vmf_sun_factor: Sunlight brightness multiplier
        vmf_ambient_factor: Ambient light brightness multiplier
        vmf_import_sky_camera: Import sky camera
        vmf_sky_equi_height: Sky equirectangular texture height
        vmf_import_unknown_entities: Import unknown entities as empties

        # MDL settings
        mdl_scale: Global scale factor for models
        mdl_target_fps: Target FPS for animations
        mdl_remove_animations: Remove animations from imported models
        mdl_import_animations: Import model animations
        mdl_apply_armatures: Apply armatures to models

        # Collection options
        main_collection: Main collection for imports
        prop_collection: Collection for models

    Raises:
        AssetImportError: If import fails
    """
    if context is None:
        import bpy

        context = bpy.context

    try:
        import plumber

        callbacks = _create_asset_callbacks(context, **options)
        threads = _get_threads_suggestion(context)

        api_importer = plumber.ApiImporter(
            file_system._fs,
            callbacks,
            threads,
            # Material settings
            material_import_materials=material_import_materials,
            material_simple_materials=material_simple_materials,
            material_texture_format=material_texture_format,
            material_texture_interpolation=material_texture_interpolation,
            material_allow_culling=material_allow_culling,
            material_editor_materials=material_editor_materials,
            # VMF settings
            vmf_import_lights=vmf_import_lights,
            vmf_light_factor=vmf_light_factor,
            vmf_sun_factor=vmf_sun_factor,
            vmf_ambient_factor=vmf_ambient_factor,
            vmf_import_sky_camera=vmf_import_sky_camera,
            vmf_sky_equi_height=vmf_sky_equi_height,
            vmf_import_unknown_entities=vmf_import_unknown_entities,
            # MDL settings
            mdl_scale=mdl_scale,
            mdl_target_fps=mdl_target_fps,
            mdl_remove_animations=mdl_remove_animations,
            mdl_import_animations=mdl_import_animations,
            mdl_apply_armatures=mdl_apply_armatures,
            # VMF settings (using defaults for model imports)
            vmf_import_brushes=True,
            vmf_import_overlays=True,
            vmf_epsilon=0.01,
            vmf_cut_threshold=0.1,
            vmf_merge_solids="MERGE",
            vmf_invisible_solids="SKIP",
            vmf_import_props=True,
            vmf_import_entities=True,
            vmf_import_sky=True,
            vmf_scale=1.0,
        )

        api_importer.add_mdl_job(path, from_game)
        api_importer.execute_jobs()

    except Exception as e:
        raise AssetImportError(f"MDL import failed: {e}") from e


def import_vmt(
    file_system: GameFileSystem,
    path: str,
    from_game: bool = True,
    context=None,
    # Material settings
    material_simple_materials: bool = False,
    material_texture_format: str = "Png",
    material_texture_interpolation: str = "Linear",
    material_allow_culling: bool = False,
    material_editor_materials: bool = False,
) -> None:
    """
    Import a VMT (Valve Material Type) file.

    Args:
        file_system: GameFileSystem to use for asset loading
        path: Path to VMT file
        from_game: Whether to load from game file system or OS file system
        context: Blender context (uses bpy.context if None)

        # Material settings
        material_simple_materials: Import simple, exporter-friendly materials
        material_texture_format: Texture format ("Png", "Tga")
        material_texture_interpolation: Texture interpolation ("Linear", "Closest", "Cubic", "Smart")
        material_allow_culling: Enable backface culling
        material_editor_materials: Import editor materials instead of invisible ones

    Raises:
        AssetImportError: If import fails
    """
    if context is None:
        import bpy

        context = bpy.context

    try:
        import plumber

        callbacks = _create_asset_callbacks(context)
        threads = _get_threads_suggestion(context)

        api_importer = plumber.ApiImporter(
            file_system._fs,
            callbacks,
            threads,
            # Material settings
            material_import_materials=True,
            material_simple_materials=material_simple_materials,
            material_texture_format=material_texture_format,
            material_texture_interpolation=material_texture_interpolation,
            material_allow_culling=material_allow_culling,
            material_editor_materials=material_editor_materials,
            # VMF settings (using defaults)
            vmf_import_lights=True,
            vmf_light_factor=1.0,
            vmf_sun_factor=1.0,
            vmf_ambient_factor=1.0,
            vmf_import_sky_camera=True,
            vmf_sky_equi_height=1024,
            vmf_import_unknown_entities=False,
            vmf_import_brushes=True,
            vmf_import_overlays=True,
            vmf_epsilon=0.01,
            vmf_cut_threshold=0.1,
            vmf_merge_solids="MERGE",
            vmf_invisible_solids="SKIP",
            vmf_import_props=True,
            vmf_import_entities=True,
            vmf_import_sky=True,
            vmf_scale=1.0,
            # MDL settings (using defaults)
            mdl_scale=1.0,
            mdl_target_fps=30.0,
            mdl_remove_animations=False,
            mdl_import_animations=True,
            mdl_apply_armatures=False,
        )

        api_importer.add_vmt_job(path, from_game)
        api_importer.execute_jobs()

    except Exception as e:
        raise AssetImportError(f"VMT import failed: {e}") from e


def import_vtf(
    file_system: GameFileSystem,
    path: str,
    from_game: bool = True,
    context=None,
    # Material settings
    material_texture_format: str = "Png",
    material_texture_interpolation: str = "Linear",
) -> None:
    """
    Import a VTF (Valve Texture Format) file.

    Args:
        file_system: GameFileSystem to use for asset loading
        path: Path to VTF file
        from_game: Whether to load from game file system or OS file system
        context: Blender context (uses bpy.context if None)

        # Material settings
        material_texture_format: Texture format ("Png", "Tga")
        material_texture_interpolation: Texture interpolation ("Linear", "Closest", "Cubic", "Smart")

    Raises:
        AssetImportError: If import fails
    """
    if context is None:
        import bpy

        context = bpy.context

    try:
        import plumber

        callbacks = _create_asset_callbacks(context)
        threads = _get_threads_suggestion(context)

        api_importer = plumber.ApiImporter(
            file_system._fs,
            callbacks,
            threads,
            # Material settings
            material_import_materials=True,
            material_simple_materials=False,
            material_texture_format=material_texture_format,
            material_texture_interpolation=material_texture_interpolation,
            material_allow_culling=False,
            material_editor_materials=False,
            # VMF settings (using defaults)
            vmf_import_lights=True,
            vmf_light_factor=1.0,
            vmf_sun_factor=1.0,
            vmf_ambient_factor=1.0,
            vmf_import_sky_camera=True,
            vmf_sky_equi_height=1024,
            vmf_import_unknown_entities=False,
            vmf_import_brushes=True,
            vmf_import_overlays=True,
            vmf_epsilon=0.01,
            vmf_cut_threshold=0.1,
            vmf_merge_solids="MERGE",
            vmf_invisible_solids="SKIP",
            vmf_import_props=True,
            vmf_import_entities=True,
            vmf_import_sky=True,
            vmf_scale=1.0,
            # MDL settings (using defaults)
            mdl_scale=1.0,
            mdl_target_fps=30.0,
            mdl_remove_animations=False,
            mdl_import_animations=True,
            mdl_apply_armatures=False,
        )

        api_importer.add_vtf_job(path, from_game)
        api_importer.execute_jobs()

    except Exception as e:
        raise AssetImportError(f"VTF import failed: {e}") from e
