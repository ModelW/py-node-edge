from importlib.metadata import version

from ._binaries import default_node_bin, default_npm_bin, default_npm_command
from ._engine import (
    JavaScriptArrayProxy,
    JavaScriptMappingProxy,
    JavaScriptPointer,
    JavaScriptProxy,
    NodeEngine,
    PointerIsh,
    as_mapping,
)
from .exceptions import (
    JavaScriptError,
    NodeEdgeException,
    NodeEdgeTypeError,
    NodeEdgeValueError,
)

__version__ = version("node-edge")

__all__ = [
    "JavaScriptArrayProxy",
    "JavaScriptError",
    "JavaScriptMappingProxy",
    "JavaScriptPointer",
    "JavaScriptProxy",
    "NodeEdgeException",
    "NodeEdgeTypeError",
    "NodeEdgeValueError",
    "NodeEngine",
    "PointerIsh",
    "__version__",
    "as_mapping",
    "default_node_bin",
    "default_npm_bin",
    "default_npm_command",
]
