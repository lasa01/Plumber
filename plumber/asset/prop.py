from typing import List
import bpy
from bpy.types import Collection, Object

from .utils import find_armature_modifier
from .model import ModelTracker
from ..plumber import LoadedProp, log_info


def import_prop(
    prop: LoadedProp,
    collection: Collection,
    model_tracker: ModelTracker,
    apply_armatures: bool,
    armatures_to_apply: List[Object],
) -> None:
    model_name = prop.model()
    obj = model_tracker.get_model_copy(model_name, collection)
    obj["path_id"] = model_name
    obj["props"] = prop.properties()

    name = f"{prop.class_name()}_{prop.id()}"

    if obj is None:
        obj = bpy.data.objects.new(name, object_data=None)
        collection.objects.link(obj)
    else:
        obj.name = name

    obj.location = prop.position()
    obj.rotation_euler = prop.rotation()
    obj.scale = prop.scale()
    obj.color = prop.color()

    if apply_armatures and obj.type == "ARMATURE":
        armatures_to_apply.append(obj)


def apply_armatures(armatures_to_apply: List[Object]):
    if not armatures_to_apply:
        return

    log_info(f"applying armatures for {len(armatures_to_apply)} props...")

    selected_objects = bpy.context.selected_objects
    active_object = bpy.context.view_layer.objects.active

    for selected_obj in selected_objects:
        selected_obj.select_set(False)

    for obj in armatures_to_apply:
        apply_armature(obj)

    for selected_obj in selected_objects:
        selected_obj.select_set(True)

    bpy.context.view_layer.objects.active = active_object

    log_info("armatures applied")


def apply_armature(obj: Object):
    children: List[Object] = obj.children

    for child in children:
        child.select_set(True)

    bpy.ops.object.make_single_user(type="SELECTED_OBJECTS", object=True, obdata=True)

    name = obj.name
    obj.name = f"{obj.name}-"

    for child in children:
        modifier = find_armature_modifier(child)

        if modifier is not None:
            bpy.context.view_layer.objects.active = child
            bpy.ops.object.modifier_apply(modifier=modifier.name)

        old_matrix_world = child.matrix_world
        child.parent = None
        child.matrix_world = old_matrix_world

        child.name = name
        child.select_set(False)

    bpy.data.objects.remove(obj)
