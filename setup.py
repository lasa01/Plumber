from setuptools import setup, find_packages, sic
from setuptools.command.develop import develop
from setuptools_rust import Binding, RustExtension

from plumber import version_str

rust_extension = RustExtension(
    "plumber.plumber",
    binding=Binding.PyO3,
    py_limited_api=True,
)


# patch develop command to allow building in release
class DevelopCommand(develop):
    user_options = develop.user_options + [("release", None, "Build in release mode")]

    def initialize_options(self):
        develop.initialize_options(self)
        self.release = False

    def finalize_options(self):
        develop.finalize_options(self)

    def run(self):
        global rust_extension
        rust_extension.debug = not self.release
        develop.run(self)


setup(
    name="plumber",
    version=sic(version_str),
    rust_extensions=[rust_extension],
    packages=find_packages(),
    # rust extensions are not zip safe, just like C-extensions.
    zip_safe=False,
    cmdclass={
        "develop": DevelopCommand,
    },
)
