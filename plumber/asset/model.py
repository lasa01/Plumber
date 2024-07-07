from typing import Dict, List, Optional

import bpy
from bpy.types import (
    Action,
    Armature,
    ArmatureModifier,
    Bone,
    Collection,
    Object,
    Material,
)
from mathutils import Euler, Vector, Matrix

from .utils import find_armature_modifier, get_unknown_material, truncate_name
from ..plumber import (
    BoneRestData,
    LoadedAnimation,
    LoadedBone,
    LoadedMesh,
    Model,
    QuaternionData,
    VectorData,
)


class ModelState:
    def __init__(
        self, model_obj: Object, children: List[Object], collection: Collection
    ) -> None:
        self.object = model_obj
        self.children = children
        self.used = False
        self.collection = collection


class ModelTracker:
    imported_objects: Dict[str, ModelState]

    def __init__(self) -> None:
        self.imported_objects = {}

    def import_model(self, model: Model, collection: Collection) -> None:
        original_name = model.name()
        model_name = truncate_name(original_name)

        parent_obj = None
        children = []

        bones = model.bones()
        if bones:
            rest_positions = model.rest_positions()
            bone_names = []
            parent_obj = import_armature(
                collection, model_name, bones, rest_positions, bone_names
            )

            animations = model.animations()
            for animation in animations:
                import_animation(parent_obj, bone_names, animation)

        bl_materials = []
        for material in model.materials():
            if material is None:
                material_data = get_unknown_material()
            else:
                material_original_name = material
                material = truncate_name(material)
                material_data = bpy.data.materials.get(material)
                if material_data is None:
                    material_data = bpy.data.materials.new(material)
                    material_data["path_id"] = material_original_name
            bl_materials.append(material_data)

        meshes = model.meshes()

        if len(meshes) > 1 and parent_obj is None:
            parent_obj = bpy.data.objects.new(model_name, object_data=None)
            collection.objects.link(parent_obj)

        for mesh in meshes:
            mesh_obj = import_mesh(
                collection, model_name, bl_materials, mesh, bones if bones else None
            )
            if parent_obj is not None:
                mesh_obj.parent = parent_obj
                if parent_obj.type == "ARMATURE":
                    armature_mod: ArmatureModifier = mesh_obj.modifiers.new(
                        "Armature", "ARMATURE"
                    )
                    armature_mod.object = parent_obj
                children.append(mesh_obj)
            else:
                # this only gets called if there is 1 mesh
                parent_obj = mesh_obj

        self.imported_objects[original_name.lower()] = ModelState(
            parent_obj, children, collection
        )

    def get_model_copy(
        self, model_name: str, collection: Collection
    ) -> Optional[Object]:
        model_state = self.imported_objects.get(model_name.lower())

        if model_state is None:
            return None

        if not model_state.used:
            model_state.used = True

            if model_state.object.name not in collection.objects:
                model_state.collection.objects.unlink(model_state.object)
                collection.objects.link(model_state.object)

                for child in model_state.children:
                    model_state.collection.objects.unlink(child)
                    collection.objects.link(child)

            return model_state.object

        # if the original object is already used, create a copy
        parent_copy = model_state.object.copy()
        collection.objects.link(parent_copy)

        for child in model_state.children:
            child_copy = child.copy()
            child_copy.parent = parent_copy

            if parent_copy.type == "ARMATURE":
                child_armature_mod = find_armature_modifier(child_copy)
                if child_armature_mod is not None:
                    child_armature_mod.object = parent_copy

            collection.objects.link(child_copy)

        return parent_copy

    def get_last_imported(self) -> Optional[Object]:
        last = next(reversed(self.imported_objects.values()), None)

        if last is None:
            return None

        return last.object


def import_mesh(
    collection: Collection,
    model_name: str,
    bl_materials: List[Material],
    mesh: LoadedMesh,
    bones: Optional[List[LoadedBone]],
) -> Object:
    mesh_name = truncate_name(f"{model_name}/{mesh.name()}")

    mesh_data = bpy.data.meshes.get(mesh_name)
    if mesh_data is None:
        mesh_data = bpy.data.meshes.new(mesh_name)
    else:
        mesh_data.clear_geometry()
        mesh_data.materials.clear()

    mesh_data["path_id"] = mesh_name

    polygons_len = mesh.polygons_len()

    vertices = mesh.vertices()
    mesh_data.vertices.add(len(vertices) // 3)
    mesh_data.loops.add(mesh.loops_len())
    mesh_data.polygons.add(mesh.polygons_len())
    mesh_data.vertices.foreach_set("co", vertices)
    mesh_data.polygons.foreach_set("loop_total", mesh.polygon_loop_totals())
    mesh_data.polygons.foreach_set("loop_start", mesh.polygon_loop_starts())
    mesh_data.polygons.foreach_set("vertices", mesh.polygon_vertices())
    mesh_data.polygons.foreach_set("material_index", mesh.polygon_material_indices())
    mesh_data.polygons.foreach_set("use_smooth", [True] * polygons_len)
    mesh_data.update(calc_edges=True)

    if bpy.app.version < (4, 1, 0):
        mesh_data.use_auto_smooth = True

    mesh_data.normals_split_custom_set_from_vertices(mesh.normals())

    uv_layer = mesh_data.uv_layers.new()
    uv_layer.data.foreach_set("uv", mesh.loop_uvs())

    for bl_material in bl_materials:
        mesh_data.materials.append(bl_material)

    mesh_obj = bpy.data.objects.new(mesh_name, object_data=mesh_data)
    collection.objects.link(mesh_obj)

    if bones is not None:
        for bone_index, weights in mesh.weight_groups().items():
            bone_name = truncate_name(bones[bone_index].name())
            vg = mesh_obj.vertex_groups.new(name=bone_name)
            for vertex_index, weight in weights.items():
                vg.add([vertex_index], weight, "REPLACE")

    return mesh_obj


def import_armature(
    collection: Collection,
    model_name: str,
    bones: List[LoadedBone],
    rest_positions: Dict[int, BoneRestData],
    bone_names: List[str],
) -> Object:
    old_armature_data = bpy.data.armatures.get(model_name)
    if old_armature_data is not None:
        old_armature_data.name = f"{old_armature_data.name}.001"

    armature_data: Armature = bpy.data.armatures.new(model_name)
    armature: Object = bpy.data.objects.new(model_name, object_data=armature_data)
    collection.objects.link(armature)

    old_active_object = bpy.context.view_layer.objects.active
    armature.select_set(True)
    bpy.context.view_layer.objects.active = armature
    bpy.ops.object.mode_set(mode="EDIT")
    bl_bones: List[Bone] = []

    for bone in bones:
        bone_name = truncate_name(bone.name())
        bl_bone = armature_data.edit_bones.new(bone_name)
        bl_bones.append(bl_bone)
        bone_names.append(bl_bone.name)

        parent_bone_index = bone.parent_bone_index()
        if parent_bone_index is not None:
            bl_bone.parent = bl_bones[parent_bone_index]

        bl_bone.tail = (0, 0, 1)
        pos = Vector(bone.position())
        rot = Euler(bone.rotation())
        matrix = Matrix.Translation(pos) @ rot.to_matrix().to_4x4()
        bl_bone.matrix = bl_bone.parent.matrix @ matrix if bl_bone.parent else matrix

    bpy.ops.object.mode_set(mode="OBJECT")

    for bone_i, rest_data in rest_positions.items():
        bone_name = bone_names[bone_i]
        bl_bone = armature.pose.bones[bone_name]

        pos = Vector(rest_data.position())
        rot = Euler(rest_data.rotation())
        matrix = Matrix.Translation(pos) @ rot.to_matrix().to_4x4()
        bl_bone.matrix = bl_bone.parent.matrix @ matrix if bl_bone.parent else matrix

    armature.select_set(False)
    bpy.context.view_layer.objects.active = old_active_object

    return armature


def import_animation(
    armature_obj: Object,
    bone_names: List[str],
    animation: LoadedAnimation,
) -> None:
    animation_data = armature_obj.animation_data_create()

    name = truncate_name(f"{armature_obj.name}/{animation.name()}")

    action = bpy.data.actions.new(name)
    animation_data.action = action

    data = animation.data()
    looping = animation.looping()

    for bone_i, bone_data in data.items():
        bone_name = bone_names[bone_i]
        curve_basename = f'pose.bones["{bone_name}"]'

        rotation = bone_data.rotation()

        if isinstance(rotation, QuaternionData):
            curve_name = f"{curve_basename}.rotation_quaternion"
            import_quaternions(action, rotation, curve_name, looping)
            armature_obj.pose.bones[bone_name].rotation_mode = "QUATERNION"
        elif rotation is not None:
            curve_name = f"{curve_basename}.rotation_quaternion"
            import_quaternion(action, rotation, curve_name)
            armature_obj.pose.bones[bone_name].rotation_mode = "QUATERNION"

        position = bone_data.position()

        if isinstance(position, VectorData):
            curve_name = f"{curve_basename}.location"
            import_vectors(action, position, curve_name, looping)
        elif position is not None:
            curve_name = f"{curve_basename}.location"
            import_vector(action, position, curve_name)


def import_quaternions(
    action: Action, data: QuaternionData, curve_name: str, looping: bool
) -> None:
    curves = [action.fcurves.new(curve_name, index=i) for i in range(4)]

    w_curve = curves[0]
    w_values = data.w_points()
    w_curve.keyframe_points.add(len(w_values) // 2)
    w_curve.keyframe_points.foreach_set("co", w_values)

    x_curve = curves[1]
    x_values = data.x_points()
    x_curve.keyframe_points.add(len(x_values) // 2)
    x_curve.keyframe_points.foreach_set("co", x_values)

    y_curve = curves[2]
    y_values = data.y_points()
    y_curve.keyframe_points.add(len(y_values) // 2)
    y_curve.keyframe_points.foreach_set("co", y_values)

    z_curve = curves[3]
    z_values = data.z_points()
    z_curve.keyframe_points.add(len(z_values) // 2)
    z_curve.keyframe_points.foreach_set("co", z_values)

    for curve in curves:
        if looping:
            curve.modifiers.new("CYCLES")
        curve.update()


def import_quaternion(action: Action, data: List[float], curve_name: str) -> None:
    w_curve = action.fcurves.new(curve_name, index=0)
    w_curve.keyframe_points.insert(0.0, data[3])
    x_curve = action.fcurves.new(curve_name, index=1)
    x_curve.keyframe_points.insert(0.0, data[0])
    y_curve = action.fcurves.new(curve_name, index=2)
    y_curve.keyframe_points.insert(0.0, data[1])
    z_curve = action.fcurves.new(curve_name, index=3)
    z_curve.keyframe_points.insert(0.0, data[2])


def import_vectors(
    action: Action, data: VectorData, curve_name: str, looping: bool
) -> None:
    curves = [action.fcurves.new(curve_name, index=i) for i in range(3)]

    x_curve = curves[0]
    x_values = data.x_points()
    x_curve.keyframe_points.add(len(x_values) // 2)
    x_curve.keyframe_points.foreach_set("co", x_values)

    y_curve = curves[1]
    y_values = data.y_points()
    y_curve.keyframe_points.add(len(y_values) // 2)
    y_curve.keyframe_points.foreach_set("co", y_values)

    z_curve = curves[2]
    z_values = data.z_points()
    z_curve.keyframe_points.add(len(z_values) // 2)
    z_curve.keyframe_points.foreach_set("co", z_values)

    for curve in curves:
        if looping:
            curve.modifiers.new("CYCLES")
        curve.update()


def import_vector(action: Action, data: List[float], curve_name: str) -> None:
    x_curve = action.fcurves.new(curve_name, index=0)
    x_curve.keyframe_points.insert(0.0, data[0])
    y_curve = action.fcurves.new(curve_name, index=1)
    y_curve.keyframe_points.insert(0.0, data[1])
    z_curve = action.fcurves.new(curve_name, index=2)
    z_curve.keyframe_points.insert(0.0, data[2])
