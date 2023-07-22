from typing import Set
import time
from statistics import mean

import bpy
from bpy.types import Context
from bpy.props import StringProperty, IntProperty
from bpy.app.handlers import persistent

from .importer import ImporterOperator, ImporterOperatorProps
from .preferences import AddonPreferences

from .plumber import log_info

HANDLER_KEY = "PLUMBER_BENCHMARK_HANDLER"

BENCHMARKS_LEFT = 0
IMPORT_SETTINGS = {}
BENCHMARK_TIMES = []


class BenchmarkVmf(
    ImporterOperator,
    ImporterOperatorProps,
):
    """Benchmark Source Engine VMF map import"""

    bl_idname = "import_scene.plumber_vmf_benchmark"
    bl_label = "Benchmark VMF import"
    bl_options = {"REGISTER"}

    filename_ext = ".vmf"

    filter_glob: StringProperty(
        default="*.vmf",
        options={"HIDDEN"},
        maxlen=255,
    )

    map_data_path: StringProperty(
        name="Embedded files path", default="", description="Leave empty to auto-detect"
    )

    import_count: IntProperty(
        name="Import count",
        default=5,
    )

    def execute(self, context: Context) -> Set[str]:
        log_info(f"Starting benchmarking vmf import with {self.import_count} imports")

        log_info(f"Warming up with first import")

        bpy.ops.import_scene.plumber_vmf(
            game=self.game,
            filepath=self.filepath,
            map_data_path=self.map_data_path,
        )

        global BENCHMARKS_LEFT, IMPORT_SETTINGS, BENCHMARK_TIMES

        BENCHMARKS_LEFT = self.import_count
        IMPORT_SETTINGS = {
            "game": self.game,
            "filepath": self.filepath,
            "map_data_path": self.map_data_path,
        }
        BENCHMARK_TIMES = []

        log_info(f"Starting measurements...")
        bpy.app.handlers.load_post.append(persistent_benchmarker)
        bpy.app.timers.register(load_empty_blend_file, first_interval=1)

        # Note: missing return statement on purpose, otherwise Blender crashes after benchmark :D

    def draw(self, context: Context):
        layout = self.layout

        layout.prop(self, "map_data_path")
        layout.prop(self, "import_count")


def load_empty_blend_file():
    bpy.ops.wm.read_homefile(use_empty=True)


@persistent
def persistent_benchmarker(_):
    global BENCHMARKS_LEFT, IMPORT_SETTINGS, BENCHMARK_TIMES

    start = time.perf_counter()
    bpy.ops.import_scene.plumber_vmf(**IMPORT_SETTINGS)
    end = time.perf_counter()

    BENCHMARK_TIMES.append(end - start)
    BENCHMARKS_LEFT -= 1

    if BENCHMARKS_LEFT <= 0:
        mean_time = mean(BENCHMARK_TIMES)
        log_info(f"Benchmark finished. Mean time: {mean_time:.4f} s")

        bpy.app.handlers.load_post.remove(persistent_benchmarker)
    else:
        load_empty_blend_file()


def register():
    preferences: AddonPreferences = bpy.context.preferences.addons[
        __package__
    ].preferences

    if preferences.enable_benchmarking:
        bpy.utils.register_class(BenchmarkVmf)


def unregister():
    preferences: AddonPreferences = bpy.context.preferences.addons[
        __package__
    ].preferences

    if preferences.enable_benchmarking:
        bpy.utils.unregister_class(BenchmarkVmf)
