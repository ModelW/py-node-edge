"""Resolution of the ``node`` and ``npm`` binaries.

By default, node-edge relies on Node being installed system-wide and
available in the ``PATH``. However, if the optional ``nodejs-wheel-binaries``
package is installed (through the ``node-edge[node]`` extra), the bundled
binaries are preferred, which makes node-edge work in environments that have
no Node installation at all.
"""

import os
from pathlib import Path

__all__ = ["default_node_bin", "default_npm_bin"]


def _nodejs_wheel_bin_dir() -> Path | None:
    """Locate the binary directory of nodejs-wheel, if installed.

    Returns
    -------
    Path or None
        The directory containing the bundled ``node``/``npm`` binaries, or
        None if ``nodejs-wheel-binaries`` is not installed.
    """
    try:
        from nodejs_wheel.executable import ROOT_DIR
    except ImportError:
        return None

    root = Path(ROOT_DIR)

    return root if os.name == "nt" else root / "bin"


def default_node_bin() -> str:
    """Return the default ``node`` binary to use.

    Prefers the binary bundled by ``nodejs-wheel-binaries`` when available,
    and falls back to whatever ``node`` resolves to in the ``PATH``.
    """
    if bin_dir := _nodejs_wheel_bin_dir():
        return str(bin_dir / ("node.exe" if os.name == "nt" else "node"))

    return "node"


def default_npm_bin() -> str:
    """Return the default ``npm`` binary to use.

    Prefers the binary bundled by ``nodejs-wheel-binaries`` when available,
    and falls back to whatever ``npm`` resolves to in the ``PATH``.
    """
    if bin_dir := _nodejs_wheel_bin_dir():
        return str(bin_dir / ("npm.cmd" if os.name == "nt" else "npm"))

    return "npm"
