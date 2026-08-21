"""Resolution of the ``node`` and ``npm`` binaries.

By default, node-edge relies on Node being installed system-wide and
available in the ``PATH``. However, if the optional ``nodejs-wheel-binaries``
package is installed (through the ``node-edge[node]`` extra), the bundled
binaries are preferred, which makes node-edge work in environments that have
no Node installation at all.
"""

import os
from pathlib import Path

__all__ = ["default_node_bin", "default_npm_bin", "default_npm_command"]


def _nodejs_wheel_root() -> Path | None:
    """Locate the root directory of nodejs-wheel, if installed.

    Returns
    -------
    Path or None
        The package directory of ``nodejs-wheel-binaries``, or None if it is
        not installed.
    """
    try:
        from nodejs_wheel.executable import ROOT_DIR
    except ImportError:
        return None

    return Path(ROOT_DIR)


def default_node_bin() -> str:
    """Return the default ``node`` binary to use.

    Prefers the binary bundled by ``nodejs-wheel-binaries`` when available,
    and falls back to whatever ``node`` resolves to in the ``PATH``.
    """
    if root := _nodejs_wheel_root():
        if os.name == "nt":
            return str(root / "node.exe")

        return str(root / "bin" / "node")

    return "node"


def default_npm_bin() -> str:
    """Return the default ``npm`` binary to use.

    .. deprecated::
        Use :func:`default_npm_command` instead, which correctly invokes the
        npm bundled by nodejs-wheel. This is kept for backwards compat and
        only ever returns the PATH-based fallback.
    """
    return "npm"


def default_npm_command() -> list[str]:
    """Return the default command (argv prefix) that runs npm.

    When ``nodejs-wheel-binaries`` is installed, its ``bin/npm`` shim is a
    broken copy of what should be a symlink, so — like nodejs-wheel's own
    Python API does — npm is invoked as ``node .../npm/bin/npm-cli.js``.
    Otherwise this is just ``["npm"]`` from the ``PATH``.
    """
    if root := _nodejs_wheel_root():
        npm_cli = root / "lib" / "node_modules" / "npm" / "bin" / "npm-cli.js"

        return [default_node_bin(), str(npm_cli)]

    return ["npm"]
