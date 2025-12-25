__all__ = ["get", "get_all"]
from .core import get, get_all
__version__ = "0.0.0"

def __getattr__(name):
    if name in __all__:
        return globals()[name]
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")

def __dir__():
    return list(__all__) + ["__version__"]
