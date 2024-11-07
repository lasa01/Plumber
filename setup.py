from setuptools import setup, find_packages, sic
from setuptools_rust import Binding, RustExtension
import toml

with open("plumber/blender_manifest.toml", "r") as f:
    manifest = toml.load(f)

version_str = manifest["version"]

rust_extension = RustExtension(
    "plumber.plumber",
    binding=Binding.PyO3,
    py_limited_api=True,
)

setup(
    name="plumber",
    version=sic(version_str),
    rust_extensions=[rust_extension],
    packages=find_packages(),
    # rust extensions are not zip safe, just like C-extensions.
    zip_safe=False,
)
