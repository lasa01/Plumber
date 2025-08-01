## Project Overview
- **Purpose:** Blender addon for importing Source 1 engine maps, models, materials, and textures (e.g., CS:GO, TF2, CS:S) into Blender.
- **Languages:** Python (addon logic), Rust (performance-critical backend, via PyO3), with build integration.
- **Key Directories:**
  - `plumber/`: Main Python addon code (entry: `addon.py`, logic: `importer/`, `asset/`, `tools.py`, etc.)
  - `src/`: Rust backend (mirrors asset/importer structure)
  - `build/`, `target/`: Build outputs (Python and Rust)
  - `setup.py`, `setup_trace.py`: Build scripts for Python/Rust extension

## Required before each commit
- Run `black .` for Python code formatting.
- Run `cargo fmt` for Rust code formatting.
- Run `cargo clippy` for Rust code linting and fix all warnings or build errors. Dependency related warnings don't need to be fixed.

## Developer Workflows
- **Before starting work on an issue**
  - The repository does not have a lot of activity, so new Rust clippy warnings may be introduced.
  - Always run `cargo clippy` first for Rust code, and fix all the warnings with `cargo clippy --fix` in a separate commit before starting work on the issue. This must be included in the same pull request as the issue fix. Dependency related warnings don't need to be fixed.
- **Testing**
  - You will be unable to test the Blender addon as an AI coding agent. Instead, let the pull request reviewer know that they will need to test the addon manually.
  - Run Rust unit tests with `cargo test`.
  - For now, new Rust tests do not need to be added as this would require a thoughtful testing design process.
- **Formatting**
  - Run `black .` for Python code formatting.
  - Run `cargo fmt` for Rust code formatting.
- **Linting**
  - Run `cargo clippy` for Rust code. No linters or type checkers have been used for Python code, as they give false positives with the Blender API.
- **Build Rust:**
  - Standard debug build: `python setup.py build_rust --inplace`
  - Output: `plumber.pyd` in `build/lib.../plumber/`
- **Manual Checklist in addition to automated tests**
  - Whenever modifying the interface between Rust and Python, ensure that the corresponding changes are made in both the Rust and Python codebases, as well as the explicit interface definition in `plumber/plumber.pyi`.
  - Make sure that code is written to work on all 3 platforms: Windows, macOS (x64 and arm64), and Linux.
  - Search the code for patterns related to the changes being made, and use similar ones or update them if necessary.

## Architecture & Data Flow
- **Python <-> Rust:** Python code calls into Rust via a compiled extension (`plumber.pyd`), built with PyO3.
- **Importers:** Each file type (`.vmf`, `.mdl`, `.vmt`, `.vtf`) has a dedicated importer operator in Python which handles the asset type specific user interface and interaction (see `plumber/importer/`), and a corresponding import function in Rust.
- **Asset Handling:** Import functions defined in Rust call into dependency code in "plumber_core" repository, which does the heavy lifting of most of the asset loading logic (except materials, see below). Finally, "plumber_core" provides us with assets in a general format, for which the Rust code calls a Python method on "AssetCallbacks" class, which then does the actual importing into Blender with the logic split by asset type (see `plumber/asset/` and `src/asset/`).
- **Asset Import Tree:** Importing a map (e.g., a `.vmf` file) triggers the import of multiple asset types—such as props, solids, and entities. For example, importing a prop results in importing its model and associated materials, and each material may require importing one or more textures. The "plumber_core" backend manages this asset dependency tree: it ensures that assets are imported in dependency order (e.g., textures before materials, materials before models), prevents duplicate imports, and enables code reuse between different importers (e.g., material import logic is shared between VMF and MDL imports). This tree-based approach guarantees correct and efficient asset loading.
- **Material Asset Loading:** Unlike other asset types with the loading logic mostly in "plumber_core", the Rust code here implements most of the material logic in `src/asset/material`, since materials are very Blender-specific. There is a framework in place for easily constructing node-based Blender materials with reusable node groups. `builder_base.rs` and `nodes.rs` contain the framework logic with automatic ordering, connecting and pretty-placement of nodes. `definitions.rs` defines the various material node types and their properties directly as they are in Blender API, and node groups that act as usable higher level components useful for the material logic. The actual Source-specific material building is implemented in `builder.rs`, with different logic paths for different material types including a large generic path handling most of the material types.
- **Preferences & addon entrypoint:** User options and addon entrypoint logic are in `preferences.py` and `addon.py` respectively.

## Project-Specific Conventions
- **File Structure:** Mirrors between Python and Rust for maintainability.
- **Import Options:** Exposed via Blender UI, mapped to importer logic.
- **Error Handling:** Most errors during import are non-fatal and are logged while the import process continues.

## Integration Points
- **External:**
  - Steam game detection (auto/manual)
  - Rust backend (`plumber_core` repo) checked out for reference in CI
  - Blender API (via `bpy` module)
- **Internal:**
  - Custom Blender properties for imported metadata (see README)

## Examples
- To add a new import option, update Blender UI in the corresponding operator and propagate to Rust importer logic. In many cases, the "plumber_core" backend will need to be updated as well to handle the new option. You are unable to do this from this repository directly, but you can check if the required changes have been made in the "plumber_core" repository and inform the user if not.
- To modify the material loading logic, in most cases it is sufficient to update the Rust code in `src/asset/material/builder.rs` (and possibly `definitions.rs`) to accommodate new material properties by adjusting the node construction logic, and handling of parameters from the material source ".vmt" file. The Python code can usually handle importing any node tree the Rust code produces.

## References
- See `README.md` for user-facing instructions.
