"""
Asset import functionality for individual and batch imports.
"""

from typing import Any, Dict, List, Optional, Union, Callable
from enum import Enum

from .exceptions import ImportError
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

    def __init__(self, file_system: GameFileSystem):
        """
        Initialize the builder.

        Args:
            file_system: GameFileSystem to use for imports
        """
        self._file_system = file_system
        self._jobs: List[ImportJob] = []

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
            ImportError: If parallel import execution fails
        """
        if not self._jobs:
            return

        if context is None:
            import bpy
            import bpy
        context = bpy.context

        try:
            # For now, execute jobs sequentially since we need to design the Rust interface
            # for mixed parallel imports. This is a placeholder implementation.
            for job in self._jobs:
                if job.asset_type == AssetType.VMF:
                    import_vmf(
                        self._file_system,
                        job.path,
                        job.from_game,
                        context,
                        **job.options,
                    )
                elif job.asset_type == AssetType.MDL:
                    import_mdl(
                        self._file_system,
                        job.path,
                        job.from_game,
                        context,
                        **job.options,
                    )
                elif job.asset_type == AssetType.VMT:
                    import_vmt(
                        self._file_system,
                        job.path,
                        job.from_game,
                        context,
                        **job.options,
                    )
                elif job.asset_type == AssetType.VTF:
                    import_vtf(
                        self._file_system,
                        job.path,
                        job.from_game,
                        context,
                        **job.options,
                    )

        except Exception as e:
            raise ImportError(f"Parallel import execution failed: {e}") from e

    def clear(self) -> "ParallelImportBuilder":
        """Clear all import jobs."""
        self._jobs.clear()
        return self

    @property
    def job_count(self) -> int:
        """Get the number of queued import jobs."""
        return len(self._jobs)


def _create_asset_callbacks(context, **options) -> Any:
    """Create AssetCallbacks instance with options."""
    from ..asset import AssetCallbacks

    # Extract collection options
    main_collection = options.get("main_collection")
    brush_collection = options.get("brush_collection")
    overlay_collection = options.get("overlay_collection")
    prop_collection = options.get("prop_collection")
    light_collection = options.get("light_collection")
    entity_collection = options.get("entity_collection")
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
        ImportError: If import fails
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
        raise ImportError(f"VMF import failed: {e}") from e


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
        ImportError: If import fails
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
        raise ImportError(f"MDL import failed: {e}") from e


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
        ImportError: If import fails
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
        raise ImportError(f"VMT import failed: {e}") from e


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
        ImportError: If import fails
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
        raise ImportError(f"VTF import failed: {e}") from e


def batch_import(
    file_system: GameFileSystem,
    assets: List[Dict[str, Any]],
    context=None,
) -> None:
    """
    Import multiple assets with similar settings.

    Args:
        file_system: GameFileSystem to use for asset loading
        assets: List of asset definitions, each should be a dict with:
                - 'type': Asset type ('vmf', 'mdl', 'vmt', 'vtf')
                - 'path': Path to asset file
                - 'from_game': Whether to load from game file system (default True)
                - Additional options specific to asset type
        context: Blender context (uses bpy.context if None)

    Example:
        assets = [
            {'type': 'mdl', 'path': 'models/player.mdl', 'import_animations': False},
            {'type': 'vmt', 'path': 'materials/concrete.vmt'},
            {'type': 'vtf', 'path': 'materials/concrete.vtf'},
        ]
        batch_import(fs, assets)

    Raises:
        ImportError: If batch import fails
    """
    if context is None:
        import bpy

        context = bpy.context

    try:
        for i, asset in enumerate(assets):
            asset_type = asset.get("type", "").lower()
            path = asset.get("path", "")
            from_game = asset.get("from_game", True)

            if not asset_type or not path:
                raise ValueError(f"Asset {i}: 'type' and 'path' are required")

            # Remove standard keys from options
            options = {
                k: v for k, v in asset.items() if k not in ["type", "path", "from_game"]
            }

            if asset_type == "vmf":
                import_vmf(file_system, path, from_game, context, **options)
            elif asset_type == "mdl":
                import_mdl(file_system, path, from_game, context, **options)
            elif asset_type == "vmt":
                import_vmt(file_system, path, from_game, context, **options)
            elif asset_type == "vtf":
                import_vtf(file_system, path, from_game, context, **options)
            else:
                raise ValueError(f"Asset {i}: Unknown asset type '{asset_type}'")

    except Exception as e:
        raise ImportError(f"Batch import failed: {e}") from e
