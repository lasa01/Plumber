from .utils import truncate_name, bilinear_interpolate
from .cube2equi import find_corresponding_pixels
from vmfpy.fs import AnyBinaryIO
from pyvtflib import VTFLib, VTFImageFlag, VTFImageFormat
import numpy
from typing import Dict, List, Optional, Callable
import bpy


class StagedImage():
    def __init__(self, importer: 'VTFImporter', name: str, file: Optional[AnyBinaryIO],
                 colorspace: str, alpha_mode: str, reused: Optional[bpy.types.Image] = None) -> None:
        self.name = name
        self.file = file
        self.colorspace = colorspace
        self.alpha_mode = alpha_mode
        self.reused = reused
        self._vtf_importer = importer

    def get_image(self) -> bpy.types.Image:
        if self.reused is not None:
            return self.reused
        return self._vtf_importer.get(self.name)

    @staticmethod
    def from_existing(importer: 'VTFImporter', image: bpy.types.Image) -> 'StagedImage':
        return StagedImage(
            importer, image.vtf_data.full_name, None, image.colorspace_settings.name, image.alpha_mode, image
        )


class VTFImporter():
    def __init__(self, reuse_old: bool = True) -> None:
        self.reuse_old = reuse_old
        self.progress_callback: Callable[[int, int], None] = lambda current, total: None
        self._cache: Dict[str, bpy.types.Image] = {}
        self._staging: Dict[str, StagedImage] = {}
        self._loaded: Dict[str, StagedImage] = {}
        self.reusable_amount = 0
        self.importable_amount = 0

    def stage(self, image_name: str, file: AnyBinaryIO,
              colorspace: str = 'sRGB', alpha_mode: str = 'CHANNEL_PACKED') -> StagedImage:
        image_name = image_name.lower()
        truncated_name = truncate_name(image_name + ".png")
        if image_name in self._staging:
            staged = self._staging[image_name]
            if colorspace != staged.colorspace:
                print(f"[WARNING] IMAGE {image_name}: COLORSPACES CONFLICT ({colorspace}, {staged.colorspace})")
            if alpha_mode != staged.alpha_mode:
                print(f"[WARNING] IMAGE {image_name}: ALPHA MODES CONFLICT ({alpha_mode}, {staged.alpha_mode})")
            return staged
        if image_name in self._loaded:
            loaded = self._loaded[image_name]
            if colorspace != loaded.colorspace:
                print(f"[WARNING] IMAGE {image_name}: COLORSPACES CONFLICT ({colorspace}, {loaded.colorspace})")
            if alpha_mode != loaded.alpha_mode:
                print(f"[WARNING] IMAGE {image_name}: ALPHA MODES CONFLICT ({alpha_mode}, {loaded.alpha_mode})")
            return loaded
        elif self.reuse_old and truncated_name in bpy.data.images:
            self._staging[image_name] = StagedImage.from_existing(self, bpy.data.images[truncated_name])
            self.reusable_amount += 1
        else:
            self._staging[image_name] = StagedImage(self, image_name, file, colorspace, alpha_mode)
            self.importable_amount += 1
        return self._staging[image_name]

    def load_all(self) -> None:
        total = len(self._staging)
        current = 0
        for image_name in self._staging:
            staged = self._staging[image_name]
            self._load(image_name, staged)
            self._loaded[image_name] = staged
            current += 1
            if current % 10 == 0 or current == total:
                self.progress_callback(current, total)
        self._staging.clear()
        self.reusable_amount = 0
        self.importable_amount = 0

    def _load(self, image_name: str, staged: StagedImage) -> None:
        image_name = image_name.lower()
        truncated_name = truncate_name(image_name + ".png")
        if staged.reused is not None:
            # image is already loaded
            self._cache[image_name] = staged.reused
            return
        if staged.file is None:
            raise Exception("a file was not specified for non-reused staged image")
        with VTFLib() as vtflib:
            with staged.file:
                vtflib.load_image_bytes(staged.file.read())
            alpha = bool(vtflib.image_flags() & (VTFImageFlag.TEXTUREFLAGS_ONEBITALPHA |
                                                 VTFImageFlag.TEXTUREFLAGS_EIGHTBITALPHA))
            width, height = vtflib.image_width(), vtflib.image_height()
            image: bpy.types.Image = bpy.data.images.new(truncated_name, width, height, alpha=alpha)
            image.vtf_data.full_name = image_name
            pixels = numpy.frombuffer(vtflib.flip_image(vtflib.image_as_rgba8888(), width, height), dtype=numpy.uint8)
        pixels = pixels.astype(numpy.float16, copy=False)
        pixels /= 255
        image.pixels = pixels
        image.file_format = 'PNG'
        image.pack()
        image.colorspace_settings.name = staged.colorspace
        image.alpha_mode = staged.alpha_mode
        self._cache[image_name] = image

    def get(self, image_name: str) -> bpy.types.Image:
        image_name = image_name.lower()
        if image_name not in self._cache:
            raise Exception(f"image {image_name} hasn't been loaded")
        return self._cache[image_name]


def load_as_equi(cubemap_name: str, files: List[AnyBinaryIO], out_height: int, hdr: bool = False) -> bpy.types.Image:
    cubemap_name = cubemap_name.lower()
    images: List[numpy.ndarray] = []
    cubemap_dim: int = -1
    with VTFLib() as vtflib:
        for file in files:
            with file:
                vtflib.load_image_bytes(file.read())
            width, height = vtflib.image_width(), vtflib.image_height()
            if width > cubemap_dim:
                cubemap_dim = width
            if hdr:
                image_format = vtflib.image_format()
                if image_format == VTFImageFormat.IMAGE_FORMAT_RGBA16161616F:  # floating point HDR
                    pixels: numpy.ndarray = numpy.fromstring(
                        vtflib.image_get_data(), dtype=numpy.float16,
                    )
                    pixels.shape = (-1, 4)
                    pixels[:, 3] = 1.0
                elif image_format == VTFImageFormat.IMAGE_FORMAT_BGRA8888:  # compressed HDR
                    pixels = numpy.frombuffer(
                        vtflib.image_get_data(), dtype=numpy.uint8
                    )
                    pixels = pixels.astype(numpy.float16, copy=False)
                    pixels.shape = (-1, 4)
                    pixels[:, :3] = pixels[:, 2::-1] * (pixels[:, 3:] * (16 / 262144))
                    pixels[:, 3] = 1.0
                else:  # don't know what this is, just treat is as a normal texture
                    pixels = numpy.frombuffer(
                        vtflib.image_as_rgba8888(), dtype=numpy.uint8
                    )
                    pixels = pixels.astype(numpy.float16, copy=False)
                    pixels /= 255
                    hdr = False
            else:
                pixels = numpy.frombuffer(
                    vtflib.image_as_rgba8888(), dtype=numpy.uint8
                )
                pixels = pixels.astype(numpy.float16, copy=False)
                pixels /= 255
            pixels.shape = (height, width, 4)
            images.append(pixels)

    if out_height == 0:
        out_height = 2 * cubemap_dim
    out_width = 2 * out_height

    faces, (input_xs, input_ys) = find_corresponding_pixels(out_width, out_height, cubemap_dim)
    output_pixels = numpy.empty((out_height, out_width, 4), dtype=numpy.float16)
    for idx, img in enumerate(images):
        face_mask: numpy.ndarray = faces == idx
        output_pixels[face_mask] = bilinear_interpolate(img, input_xs[face_mask], input_ys[face_mask])
    output_pixels.shape = (-1,)

    image: bpy.types.Image = bpy.data.images.new(
        truncate_name(cubemap_name + (".exr" if hdr else ".png")), out_width, out_height, float_buffer=hdr
    )
    image.pixels = output_pixels
    if hdr:
        image.file_format = 'OPEN_EXR'
    else:
        image.file_format = 'PNG'
    image.pack()
    image.colorspace_settings.name = 'sRGB'
    return image
