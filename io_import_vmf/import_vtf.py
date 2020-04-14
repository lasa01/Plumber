from vmfpy.fs import AnyBinaryIO
from pyvtflib import VTFLib, VTFImageFlag
import numpy
from typing import Dict
import bpy


class VTFImporter():
    def __init__(self) -> None:
        self._cache: Dict[str, bpy.types.Image] = {}

    def load(self, image_name: str, file: AnyBinaryIO,
             colorspace: str = 'sRGB', alpha_mode: str = 'CHANNEL_PACKED') -> bpy.types.Image:
        if image_name in self._cache:
            return self._cache[image_name]
        with VTFLib() as vtflib:
            with file:
                vtflib.load_image_bytes(file.read())
            alpha = bool(vtflib.image_flags() & (VTFImageFlag.TEXTUREFLAGS_ONEBITALPHA |
                                                 VTFImageFlag.TEXTUREFLAGS_EIGHTBITALPHA))
            width, height = vtflib.image_width(), vtflib.image_height()
            image: bpy.types.Image = bpy.data.images.new(image_name + ".png", width, height,
                                                         alpha=alpha)
            pixels = numpy.frombuffer(vtflib.flip_image(vtflib.image_as_rgba8888(), width, height), dtype=numpy.uint8)
        pixels = pixels.astype(numpy.float16, copy=False)
        pixels /= 255
        image.pixels = pixels
        image.file_format = 'PNG'
        image.pack()
        image.colorspace_settings.name = colorspace
        image.alpha_mode = alpha_mode
        self._cache[image_name] = image
        return image
