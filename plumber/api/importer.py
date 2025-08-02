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

    def __init__(
        self, asset_type: AssetType, path: str, from_game: bool = True, **options
    ):
        """
        Initialize an import job.

        Args:
            asset_type: Type of asset to import
            path: Path to the asset file
            from_game: Whether to load from game file system or OS file system
            **options: Additional import options specific to asset type
        """
        self.asset_type = asset_type
        self.path = path
        self.from_game = from_game
        self.options = options


class ParallelImportBuilder:
    """
    Builder for creating custom parallel import processes.

    Allows mixing different asset types for parallel import using the Rust-side executor.
    """

    def __init__(
        self,
        file_system: GameFileSystem,
        # Material options (applied to all imports in this builder)
        simple_materials: bool = False,
        texture_format: str = "Png",
        texture_interpolation: str = "Linear",
        allow_culling: bool = False,
        editor_materials: bool = False,
    ):
        """
        Initialize the builder.

        Args:
            file_system: GameFileSystem to use for imports
            simple_materials: Import simple, exporter-friendly materials
            texture_format: Texture format ("Png", "Tga")
            texture_interpolation: Texture interpolation ("Linear", "Closest", "Cubic", "Smart")
            allow_culling: Enable backface culling
            editor_materials: Import editor materials instead of invisible ones
        """
        self._file_system = file_system
        self._jobs: List[ImportJob] = []

        # Store material settings to be used for all imports
        self._material_settings = {
            "simple_materials": simple_materials,
            "texture_format": texture_format,
            "texture_interpolation": texture_interpolation,
            "allow_culling": allow_culling,
            "editor_materials": editor_materials,
        }

    def add_vmf(
        self, path: str, from_game: bool = True, **options
    ) -> "ParallelImportBuilder":
        """
        Add a VMF import job.

        Args:
            path: Path to VMF file
            from_game: Whether to load from game file system
            **options: VMF import options (see import_vmf for details)

        Returns:
            Self for method chaining
        """
        self._jobs.append(ImportJob(AssetType.VMF, path, from_game, **options))
        return self

    def add_mdl(
        self, path: str, from_game: bool = True, **options
    ) -> "ParallelImportBuilder":
        """
        Add an MDL import job.

        Args:
            path: Path to MDL file
            from_game: Whether to load from game file system
            **options: MDL import options (see import_mdl for details)

        Returns:
            Self for method chaining
        """
        self._jobs.append(ImportJob(AssetType.MDL, path, from_game, **options))
        return self

    def add_vmt(
        self, path: str, from_game: bool = True, **options
    ) -> "ParallelImportBuilder":
        """
        Add a VMT import job.

        Args:
            path: Path to VMT file
            from_game: Whether to load from game file system
            **options: VMT import options (see import_vmt for details)

        Returns:
            Self for method chaining
        """
        self._jobs.append(ImportJob(AssetType.VMT, path, from_game, **options))
        return self

    def add_vtf(
        self, path: str, from_game: bool = True, **options
    ) -> "ParallelImportBuilder":
        """
        Add a VTF import job.

        Args:
            path: Path to VTF file
            from_game: Whether to load from game file system
            **options: VTF import options (see import_vtf for details)

        Returns:
            Self for method chaining
        """
        self._jobs.append(ImportJob(AssetType.VTF, path, from_game, **options))
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

            callbacks = _create_asset_callbacks(context)
            threads = _get_threads_suggestion(context)

            # Create API importer with material settings
            api_importer = plumber.ApiImporter(
                self._file_system._fs,
                callbacks,
                threads,
                **self._material_settings,
            )

            # Add all jobs to the API importer
            for job in self._jobs:
                if job.asset_type == AssetType.VMF:
                    # VMF jobs don't pass material options since they're already in the importer
                    non_material_options = {
                        k: v
                        for k, v in job.options.items()
                        if k not in self._material_settings
                    }
                    api_importer.add_vmf_job(
                        job.path, job.from_game, **non_material_options
                    )
                elif job.asset_type == AssetType.MDL:
                    # MDL jobs don't pass material options since they're already in the importer
                    non_material_options = {
                        k: v
                        for k, v in job.options.items()
                        if k not in self._material_settings
                    }
                    api_importer.add_mdl_job(
                        job.path, job.from_game, **non_material_options
                    )
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
    # VMF-specific options
    map_data_path: str = "",
    import_brushes: bool = True,
    import_overlays: bool = True,
    import_props: bool = True,
    import_lights: bool = True,
    import_sky_camera: bool = True,
    import_materials: bool = True,
    merge_solids: str = "PER_ENTITY",
    invisible_solids: str = "IMPORT_VISIBLE",
    optimize_props: bool = True,
    # Material options
    simple_materials: bool = False,
    texture_format: str = "Png",
    texture_interpolation: str = "Linear",
    allow_culling: bool = False,
    editor_materials: bool = False,
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

        # VMF-specific options
        map_data_path: Path to embedded files (empty for auto-detect)
        import_brushes: Import brush geometry
        import_overlays: Import overlay geometry
        import_props: Import props
        import_lights: Import lighting
        import_sky_camera: Import sky camera
        import_materials: Import materials
        merge_solids: How to merge brush solids ("PER_ENTITY", "PER_MATERIAL", "NONE")
        invisible_solids: How to handle invisible solids ("IMPORT_VISIBLE", "IMPORT_ALL", "IMPORT_INVISIBLE")
        optimize_props: Optimize prop instances

        # Material options (when import_materials=True)
        simple_materials: Import simple, exporter-friendly materials
        texture_format: Texture format ("Png", "Tga")
        texture_interpolation: Texture interpolation ("Linear", "Closest", "Cubic", "Smart")
        allow_culling: Enable backface culling
        editor_materials: Import editor materials instead of invisible ones

        # Collection options
        main_collection: Main collection for imports
        brush_collection: Collection for brushes
        overlay_collection: Collection for overlays
        prop_collection: Collection for props
        light_collection: Collection for lights
        entity_collection: Collection for entities
        apply_armatures: Apply armatures to models

    Raises:
        AssetImportError: If import fails
    """
    if context is None:
        import bpy

        context = bpy.context

    try:
        from ..plumber import Importer

        callbacks = _create_asset_callbacks(context, **options)
        threads = _get_threads_suggestion(context)

        importer = Importer(
            file_system._fs,
            callbacks,
            threads,
            simple_materials=simple_materials,
            texture_format=texture_format,
            texture_interpolation=texture_interpolation,
            allow_culling=allow_culling,
            editor_materials=editor_materials,
        )

        importer.import_vmf(
            path,
            from_game,
            map_data_path=map_data_path,
            import_brushes=import_brushes,
            import_overlays=import_overlays,
            import_props=import_props,
            import_lights=import_lights,
            import_sky_camera=import_sky_camera,
            import_materials=import_materials,
            merge_solids=merge_solids,
            invisible_solids=invisible_solids,
            optimize_props=optimize_props,
        )

    except Exception as e:
        raise AssetImportError(f"VMF import failed: {e}") from e


def import_mdl(
    file_system: GameFileSystem,
    path: str,
    from_game: bool = True,
    context=None,
    # MDL-specific options
    import_animations: bool = True,
    import_materials: bool = True,
    # Material options
    simple_materials: bool = False,
    texture_format: str = "Png",
    texture_interpolation: str = "Linear",
    allow_culling: bool = False,
    editor_materials: bool = False,
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

        # MDL-specific options
        import_animations: Import model animations
        import_materials: Import materials

        # Material options (when import_materials=True)
        simple_materials: Import simple, exporter-friendly materials
        texture_format: Texture format ("Png", "Tga")
        texture_interpolation: Texture interpolation ("Linear", "Closest", "Cubic", "Smart")
        allow_culling: Enable backface culling
        editor_materials: Import editor materials instead of invisible ones

        # Collection options
        main_collection: Main collection for imports
        prop_collection: Collection for models
        apply_armatures: Apply armatures to models

    Raises:
        AssetImportError: If import fails
    """
    if context is None:
        import bpy

        context = bpy.context

    try:
        from ..plumber import Importer

        callbacks = _create_asset_callbacks(context, **options)
        threads = _get_threads_suggestion(context)

        importer = Importer(
            file_system._fs,
            callbacks,
            threads,
            simple_materials=simple_materials,
            texture_format=texture_format,
            texture_interpolation=texture_interpolation,
            allow_culling=allow_culling,
            editor_materials=editor_materials,
        )

        importer.import_mdl(
            path,
            from_game,
            import_animations=import_animations,
            import_materials=import_materials,
        )

    except Exception as e:
        raise AssetImportError(f"MDL import failed: {e}") from e


def import_vmt(
    file_system: GameFileSystem,
    path: str,
    from_game: bool = True,
    context=None,
    # Material options
    simple_materials: bool = False,
    texture_format: str = "Png",
    texture_interpolation: str = "Linear",
    allow_culling: bool = False,
    editor_materials: bool = False,
) -> None:
    """
    Import a VMT (Valve Material Type) file.

    Args:
        file_system: GameFileSystem to use for asset loading
        path: Path to VMT file
        from_game: Whether to load from game file system or OS file system
        context: Blender context (uses bpy.context if None)

        # Material options
        simple_materials: Import simple, exporter-friendly materials
        texture_format: Texture format ("Png", "Tga")
        texture_interpolation: Texture interpolation ("Linear", "Closest", "Cubic", "Smart")
        allow_culling: Enable backface culling
        editor_materials: Import editor materials instead of invisible ones

    Raises:
        AssetImportError: If import fails
    """
    if context is None:
        import bpy

        context = bpy.context

    try:
        from ..plumber import Importer

        callbacks = _create_asset_callbacks(context)
        threads = _get_threads_suggestion(context)

        importer = Importer(
            file_system._fs,
            callbacks,
            threads,
            simple_materials=simple_materials,
            texture_format=texture_format,
            texture_interpolation=texture_interpolation,
            allow_culling=allow_culling,
            editor_materials=editor_materials,
        )

        importer.import_vmt(path, from_game)

    except Exception as e:
        raise AssetImportError(f"VMT import failed: {e}") from e


def import_vtf(
    file_system: GameFileSystem,
    path: str,
    from_game: bool = True,
    context=None,
    # Texture options
    texture_format: str = "Png",
    texture_interpolation: str = "Linear",
) -> None:
    """
    Import a VTF (Valve Texture Format) file.

    Args:
        file_system: GameFileSystem to use for asset loading
        path: Path to VTF file
        from_game: Whether to load from game file system or OS file system
        context: Blender context (uses bpy.context if None)

        # Texture options
        texture_format: Texture format ("Png", "Tga")
        texture_interpolation: Texture interpolation ("Linear", "Closest", "Cubic", "Smart")

    Raises:
        AssetImportError: If import fails
    """
    if context is None:
        import bpy

        context = bpy.context

    try:
        from ..plumber import Importer

        callbacks = _create_asset_callbacks(context)
        threads = _get_threads_suggestion(context)

        importer = Importer(
            file_system._fs,
            callbacks,
            threads,
            texture_format=texture_format,
            texture_interpolation=texture_interpolation,
        )

        importer.import_vtf(path, from_game)

    except Exception as e:
        raise AssetImportError(f"VTF import failed: {e}") from e
