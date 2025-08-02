# Plumber Python API

This module provides a clean Python API for accessing Plumber's Source engine import functionality from external scripts and addons.

## Overview

The Plumber API allows you to:
- Access game definitions from Plumber preferences
- Create and browse game file systems
- Import individual Source engine assets (VMF, MDL, VMT, VTF)
- Perform batch imports of multiple assets
- Build custom parallel import processes

## Basic Usage

### Accessing Game Definitions

```python
from plumber.api import Games, GameNotFoundError

# Get all configured games
games = Games.get_all()
for game in games:
    print(f"Game: {game.name}")
    print(f"Search paths: {len(game.search_paths)}")

# Find a specific game by name
try:
    cs_go = Games.find_by_name("Counter-Strike: Global Offensive")
except GameNotFoundError:
    print("CS:GO not found in preferences")

# Find games matching a pattern
source_games = Games.find_by_pattern("counter-strike")
```

### Working with Game File Systems

```python
from plumber.api import GameFileSystem, FileSystemError

# Create file system from a game definition
cs_go = Games.find_by_name("Counter-Strike: Global Offensive")
fs = cs_go.get_file_system()

# Or create a custom file system
fs = GameFileSystem.from_search_paths("My Game", [
    ("DIR", "/path/to/game"),
    ("VPK", "/path/to/pak01_dir.vpk"),
])

# Create empty file system for special cases
empty_fs = GameFileSystem.empty()

# Browse directories
try:
    entries = fs.browse_directory("maps")
    for entry in entries:
        if entry.is_file and entry.name.endswith('.vmf'):
            print(f"Found map: {entry.path}")
except FileSystemError as e:
    print(f"Failed to browse: {e}")

# Read files
try:
    vmf_content = fs.read_file_text("maps/de_dust2.vmf")
    vtf_data = fs.read_file_bytes("materials/concrete/concrete.vtf")
except FileSystemError as e:
    print(f"Failed to read file: {e}")
```

### Importing Individual Assets

```python
from plumber.api import import_vmf, import_mdl, import_vmt, import_vtf

# Import a VMF map with custom settings
import_vmf(
    fs, 
    "maps/de_dust2.vmf",
    import_brushes=True,
    import_props=True,
    import_materials=True,
    simple_materials=False,
    texture_format="Png"
)

# Import a model
import_mdl(
    fs,
    "models/player/ct_urban.mdl", 
    import_animations=True,
    import_materials=True
)

# Import materials and textures
import_vmt(fs, "materials/concrete/concrete.vmt")
import_vtf(fs, "materials/concrete/concrete.vtf")
```

### Batch Import

```python
from plumber.api import batch_import

# Define multiple assets to import
assets = [
    {'type': 'mdl', 'path': 'models/player.mdl', 'import_animations': False},
    {'type': 'vmt', 'path': 'materials/concrete.vmt'},
    {'type': 'vtf', 'path': 'materials/concrete.vtf'},
]

batch_import(fs, assets)
```

### Parallel Import Builder

```python
from plumber.api import ParallelImportBuilder

# Build a custom parallel import process
builder = ParallelImportBuilder(fs)

builder.add_mdl("models/player1.mdl", import_animations=True) \
       .add_mdl("models/player2.mdl", import_animations=True) \
       .add_vmt("materials/concrete.vmt") \
       .add_vtf("materials/concrete.vtf")

# Execute all imports in parallel
builder.execute()

print(f"Executed {builder.job_count} import jobs")
```

## Complete Example

Here's a comprehensive example that demonstrates finding a game, browsing for files, and performing parallel imports:

```python
from plumber.api import (
    Games, GameFileSystem, ParallelImportBuilder, 
    GameNotFoundError, FileSystemError, ImportError
)
import re

def find_and_import_models():
    \"\"\"
    Find a Source game, browse for model files matching a pattern, 
    and import them all in parallel.
    \"\"\"
    try:
        # Find Counter-Strike game
        games = Games.find_by_pattern("counter-strike")
        if not games:
            print("No Counter-Strike games found")
            return
        
        game = games[0]  # Use first match
        print(f"Using game: {game.name}")
        
        # Get file system
        fs = game.get_file_system()
        
        # Browse models directory
        models = []
        try:
            entries = fs.browse_directory("models/player")
            for entry in entries:
                if entry.is_file and entry.name.endswith('.mdl'):
                    # Check if it matches our pattern (e.g., player models)
                    if re.search(r'(ct_|t_)', entry.name):
                        models.append(entry.path)
                        print(f"Found model: {entry.path}")
        except FileSystemError:
            print("Could not browse models/player directory")
            return
        
        if not models:
            print("No matching models found")
            return
            
        # Create parallel import process
        builder = ParallelImportBuilder(fs)
        
        # Add all models to import queue
        for model_path in models:
            builder.add_mdl(
                model_path, 
                import_animations=True,
                import_materials=True,
                simple_materials=False
            )
        
        # Execute parallel import
        print(f"Starting parallel import of {builder.job_count} models...")
        builder.execute()
        print("Import completed!")
        
    except GameNotFoundError as e:
        print(f"Game not found: {e}")
    except ImportError as e:
        print(f"Import failed: {e}")
    except Exception as e:
        print(f"Unexpected error: {e}")

if __name__ == "__main__":
    find_and_import_models()
```

## API Reference

### Games and Game Definitions

- `Games.get_all()` - Get all configured games from preferences
- `Games.find_by_name(name)` - Find game by exact name  
- `Games.find_by_pattern(pattern)` - Find games matching pattern
- `Game.name` - Game name property
- `Game.search_paths` - List of (kind, path) search path tuples
- `Game.get_file_system()` - Create GameFileSystem for this game

### File System Access

- `GameFileSystem.from_search_paths(name, paths)` - Create from search paths
- `GameFileSystem.empty()` - Create empty file system
- `GameFileSystem.from_gameinfo(path)` - Create from gameinfo.txt
- `GameFileSystem.browse_directory(dir)` - Browse directory contents
- `GameFileSystem.read_file_text(path)` - Read file as text
- `GameFileSystem.read_file_bytes(path)` - Read file as bytes  
- `GameFileSystem.file_exists(path)` - Check if file exists

### Import Functions

- `import_vmf(fs, path, **options)` - Import VMF map
- `import_mdl(fs, path, **options)` - Import MDL model
- `import_vmt(fs, path, **options)` - Import VMT material
- `import_vtf(fs, path, **options)` - Import VTF texture
- `batch_import(fs, assets)` - Import multiple assets

### Parallel Import

- `ParallelImportBuilder(fs)` - Create builder
- `builder.add_vmf/mdl/vmt/vtf(path, **options)` - Add import jobs
- `builder.execute()` - Execute all jobs in parallel
- `builder.clear()` - Clear all jobs
- `builder.job_count` - Number of queued jobs

### Exceptions

- `PlumberAPIError` - Base exception for all API errors
- `GameNotFoundError` - Game not found in preferences
- `FileSystemError` - File system access error
- `ImportError` - Asset import error

## Requirements

- Blender with Plumber addon installed and configured
- At least one game definition in Plumber preferences
- Game files accessible from configured search paths

## Notes

- The API wraps internal Plumber classes and provides a stable interface
- All paths use forward slashes regardless of platform
- File reading operations extract files to temporary locations
- Parallel imports currently execute sequentially (may be improved in future)
- Import options match those available in Plumber's UI operators