from setuptools import setup, find_packages, sic
from setuptools_rust import Binding, RustExtension

from plumber import version_str

rust_extension = RustExtension(
    "plumber.plumber",
    binding=Binding.PyO3,
    py_limited_api=True,
    features=["trace"],
    args=["--no-default-features", "--profile=trace"],
)

setup(
    name="plumber",
    version=sic(version_str),
    rust_extensions=[rust_extension],
    packages=find_packages(),
    # rust extensions are not zip safe, just like C-extensions.
    zip_safe=False,
)
