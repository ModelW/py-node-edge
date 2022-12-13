from os import getenv
from pathlib import Path


def _path_from_env(variable: str, default: Path) -> Path:
    """
    Very inspired by https://pypi.org/project/xdg/

    Read an environment variable as a path.

    The environment variable with the specified name is read, and its
    value returned as a path. If the environment variable is not set, is
    set to the empty string, or is set to a relative rather than
    absolute path, the default value is returned.

    Parameters
    ----------
    variable
        Name of the environment variable.
    default
        Default value.
    """

    if (value := getenv(variable)) and (path := Path(value)).is_absolute():
        return path

    return default


def xdg_state_home() -> Path:
    """Return a Path corresponding to XDG_STATE_HOME."""
    return _path_from_env("XDG_STATE_HOME", Path.home() / ".local" / "state")
