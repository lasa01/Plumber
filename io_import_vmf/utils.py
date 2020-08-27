from hashlib import md5
from base64 import urlsafe_b64encode
from posixpath import split, splitext
from typing import Iterable
import numpy
import bpy

_HASH_LEN = 6
_B64_LEN = 8


def _hashed(s: str) -> str:
    return urlsafe_b64encode(md5(s.encode('utf-8')).digest()[:_HASH_LEN])[:_B64_LEN].decode('ascii')


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


_VISIBLE_TOOLS = frozenset((
    "tools/toolsblack", "tools/toolswhite", "tools/toolsnolight",
))


def is_invisible_tool(materials: Iterable[str]) -> bool:
    return all(mat.startswith("tools/") and mat not in _VISIBLE_TOOLS for mat in materials)


# Originally created by Alex Flint, https://stackoverflow.com/a/12729229
# Applied Pete Florence's suggested modifications to make it work with this use case.
# Modified out of bounds handling to prevent black pixels.
def bilinear_interpolate(im: numpy.ndarray, x: numpy.ndarray, y: numpy.ndarray) -> numpy.ndarray:
    x0 = numpy.floor(x).astype(int)
    x1 = x0 + 1
    y0 = numpy.floor(y).astype(int)
    y1 = y0 + 1

    x0 = numpy.clip(x0, 0, im.shape[1]-1)
    x1 = numpy.clip(x1, 0, im.shape[1]-1)
    y0 = numpy.clip(y0, 0, im.shape[0]-1)
    y1 = numpy.clip(y1, 0, im.shape[0]-1)

    i_a = im[y0, x0]
    i_b = im[y1, x0]
    i_c = im[y0, x1]
    i_d = im[y1, x1]

    wa = (x1-x) * (y1-y)
    wb = (x1-x) * (y-y0)
    wc = (x-x0) * (y1-y)
    wd = (x-x0) * (y-y0)

    z = (wa + wb + wc + wd) < 0.001

    wa[z] = 0.25
    wb[z] = 0.25
    wc[z] = 0.25
    wd[z] = 0.25

    return (i_a.T*wa).T + (i_b.T*wb).T + (i_c.T*wc).T + (i_d.T*wd).T


def fallback_material(material_name: str, truncated_name: str) -> bpy.types.Material:
    material: bpy.types.Material = bpy.data.materials.new(truncated_name)
    material.vmt_data.full_name = material_name
    return material


def filesystemify(s: str) -> str:
    return "".join(c if c.isalnum() or c in "._- " else "_" for c in s)
