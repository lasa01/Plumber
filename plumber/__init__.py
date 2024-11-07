import platform
import os

is_windows = platform.system() == "Windows"


def register():
    if is_windows:
        # Check if the extension module was renamed on the last unregister,
        # and either rename it back or delete it if the addon was updated with a newer extension module
        ext_path = os.path.join(os.path.dirname(__file__), "plumber.pyd")
        unloaded_ext_path = os.path.join(
            os.path.dirname(os.path.dirname(__file__)), "plumber.pyd.unloaded"
        )

        if os.path.isfile(unloaded_ext_path):
            if os.path.isfile(ext_path):
                try:
                    os.remove(unloaded_ext_path)
                except OSError:
                    print(
                        "[Plumber] [WARN] old files remaining, restart Blender to finish post-update clean up"
                    )
            else:
                os.rename(unloaded_ext_path, ext_path)

    from . import addon

    addon.register()


def unregister():
    from . import addon

    addon.unregister()

    if is_windows:
        # Rename the extension module to allow updating the addon without restarting Blender,
        # since the extension module will stay open and can't be overwritten even if the addon is unloaded
        ext_path = os.path.join(os.path.dirname(__file__), "plumber.pyd")
        unloaded_ext_path = os.path.join(
            os.path.dirname(os.path.dirname(__file__)), "plumber.pyd.unloaded"
        )

        try:
            os.rename(ext_path, unloaded_ext_path)
        except OSError:
            pass
