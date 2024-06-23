from hashlib import md5
from base64 import urlsafe_b64encode
from posixpath import split, splitext
from typing import Optional
import bpy

_HASH_LEN = 6
_B64_LEN = 8


def _hashed(s: str) -> str:
    return urlsafe_b64encode(md5(s.encode("utf-8")).digest()[:_HASH_LEN])[
        :_B64_LEN
    ].decode("ascii")


def truncate_name(name: str, maxlen: int = 59) -> str:
    name = name.replace("\\", "/").strip("/")
    if len(name) <= maxlen:
        return name
    path, basename = split(name)
    max_path_len = maxlen - (len(basename) + _B64_LEN + 2)
    if max_path_len <= 0:
        name, extension = splitext(name)
        return f"~{_hashed(name)}{extension}"
    path_split = -max_path_len
    path_discard, path_keep = path[:path_split], path[path_split:]
    if "/" in path_keep:
        extra_discard, final_keep = path_keep.split("/", maxsplit=1)
        final_keep += "/"
    else:
        extra_discard, final_keep = path_keep, ""
    final_discard = path_discard + extra_discard
    return f"~{_hashed(final_discard)}/{final_keep}{basename}"


def get_unknown_material() -> bpy.types.Material:
    material = bpy.data.materials.get("?.vmt")
    if material is None:
        material = bpy.data.materials.new("?.vmt")
    return material


def find_armature_modifier(
    obj: bpy.types.Object,
) -> Optional[bpy.types.ArmatureModifier]:
    for modifier in obj.modifiers:
        if modifier.type == "ARMATURE":
            return modifier
    return None
