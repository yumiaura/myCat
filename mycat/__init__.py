from importlib.metadata import version, PackageNotFoundError

try:
    __version__ = version("mycat")
except PackageNotFoundError:
    __version__ = "0.0.0"

__all__ = ["__version__"]
