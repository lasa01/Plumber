# Originally by adamb70 from https://github.com/adamb70/Python-Spherical-Projection
# Modified to be used with Source Engine cubemaps.
# Converted to numpy to achieve reasonable performance.

import numpy
from numpy import ndarray
from enum import IntEnum
from typing import Tuple


def spherical_coordinates(i: ndarray, j: ndarray, w: float, h: float) -> Tuple[ndarray, ndarray]:
    """ Returns spherical coordinates of the pixel from the output image. """
    theta = 2*i/w-1
    phi = 2*j/h-1
    # phi = lat, theta = long
    return phi*(numpy.pi/2), theta*numpy.pi


def vector_coordinates(phi: ndarray, theta: ndarray) -> Tuple[ndarray, ndarray, ndarray]:
    """ Returns 3D vector which points to the pixel location inside a sphere. """
    phi_cos = numpy.cos(phi)
    return (phi_cos * numpy.cos(theta),  # X
            numpy.sin(phi),              # Y
            phi_cos * numpy.sin(theta))  # Z


class CubemapFace(IntEnum):
    LEFT = 0
    RIGHT = 1
    TOP = 2
    BOTTOM = 3
    FRONT = 4
    BACK = 5


def get_face(x: ndarray, y: ndarray, z: ndarray) -> ndarray:
    """ Uses 3D vector to find which cube face the pixel lies on. """
    abs_x = numpy.abs(x)
    abs_y = numpy.abs(y)
    abs_z = numpy.abs(z)
    largest_magnitude = numpy.maximum.reduce((abs_x, abs_y, abs_z))

    x_selector: ndarray = largest_magnitude - abs_x < 1e-9
    x_specifier: ndarray = x < 0
    y_selector: ndarray = largest_magnitude - abs_y < 1e-9
    y_specifier: ndarray = y < 0
    z_selector: ndarray = largest_magnitude - abs_z < 1e-9
    z_specifier: ndarray = z < 0

    return numpy.select(
        (
            x_selector & x_specifier, x_selector & ~x_specifier,
            y_selector & y_specifier, y_selector & ~y_specifier,
            z_selector & z_specifier, z_selector & ~z_specifier,
        ),
        (
            CubemapFace.LEFT, CubemapFace.RIGHT,
            CubemapFace.TOP, CubemapFace.BOTTOM,
            CubemapFace.BACK, CubemapFace.FRONT,
        ),
    )


def raw_face_coordinates(face: ndarray, x: ndarray, y: ndarray, z: ndarray) -> Tuple[ndarray, ndarray, ndarray]:
    """
    Return coordinates with necessary sign (- or +) depending on which face they lie on.

    From Open-GL specification (chapter 3.8.10) https://www.opengl.org/registry/doc/glspec41.core.20100725.pdf
    """
    front = face == CubemapFace.FRONT
    back = face == CubemapFace.BACK
    bottom = face == CubemapFace.BOTTOM
    top = face == CubemapFace.TOP
    left = face == CubemapFace.LEFT
    right = face == CubemapFace.RIGHT

    x_neg = -x

    xc = numpy.select(
        (
            front, back, bottom, top, left, right,
        ),
        (
            x_neg, x, z, z, -z, z,
        )
    )
    yc = numpy.select(
        (
            front, back, bottom, top, left, right,
        ),
        (
            y, y, x_neg, x, y, y,
        )
    )
    ma = numpy.select(
        (
            front, back, bottom, top, left, right,
        ),
        (
            z, z, y, y, x, x,
        )
    )

    return xc, yc, ma


def raw_coordinates(xc: ndarray, yc: ndarray, ma: ndarray) -> Tuple[ndarray, ndarray]:
    """
    Return 2D coordinates on the specified face relative to the bottom-left corner of the face.
    Also from Open-GL spec.
    """
    return (xc/numpy.abs(ma) + 1) / 2, (yc/numpy.abs(ma) + 1) / 2


def normalized_coordinates(face: ndarray, x: ndarray, y: ndarray, n: int) -> Tuple[ndarray, ndarray]:
    """ Return pixel coordinates in the input image where the specified pixel lies. """
    return (x*n).clip(0, n-1), (y*n).clip(0, n-1)


def find_corresponding_pixels(width: int, height: int, out_dim: int) -> Tuple[ndarray, Tuple[ndarray, ndarray]]:
    """ Returns face index, pixel coordinates for the input image that a specified pixel in the output image maps to."""

    y, x = numpy.mgrid[0:height, 0:width]

    y = y[::-1]

    spherical = spherical_coordinates(x, y, width, height)
    vector_coords = vector_coordinates(spherical[0], spherical[1])
    face = get_face(vector_coords[0], vector_coords[1], vector_coords[2])
    raw_face_coords = raw_face_coordinates(face, vector_coords[0], vector_coords[1], vector_coords[2])

    cube_coords = raw_coordinates(raw_face_coords[0], raw_face_coords[1], raw_face_coords[2])

    return face, normalized_coordinates(face, cube_coords[0], cube_coords[1], out_dim)
