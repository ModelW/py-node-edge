import json
from hashlib import sha256
from pathlib import Path
from subprocess import DEVNULL, PIPE, Popen
from tempfile import gettempdir
from typing import Mapping

from xdg import xdg_state_home

from ._exceptions import NodeEdgeException

__all__ = [
    "NodeEngine",
]


class NodeEngine:
    def __init__(self, package: Mapping, npm_bin: str = "npm", keep_lock: bool = True):
        self.package = package
        self.npm_bin = npm_bin
        self.keep_lock = keep_lock
        self._env_dir = None

    @property
    def package_signature(self):
        return sha256(
            json.dumps(self.package, ensure_ascii=True).encode("ascii")
        ).hexdigest()

    def _try_env_candidate(self, path: Path):
        try:
            path.mkdir(parents=True, exist_ok=True)
        except (PermissionError, NotADirectoryError):
            return False
        else:
            return True

    def _ensure_env_dir(self) -> Path:
        for candidate in [xdg_state_home(), Path(gettempdir())]:
            full_path = candidate / "node_edge" / "envs" / self.package_signature

            if self._try_env_candidate(full_path):
                return full_path

        raise NodeEdgeException("Could not find/create env dir")

    def ensure_env_dir(self, force: bool = False) -> Path:
        if self._env_dir is None or force:
            self._env_dir = self._ensure_env_dir()

        return self._env_dir

    def create_env(self):
        root = self.ensure_env_dir()

        with open(root / "package.json", "w") as f:
            json.dump(self.package, f)

        if not self.keep_lock:
            (root / "package-lock.json").unlink(missing_ok=True)

        p = Popen(
            args=[self.npm_bin, "install"],
            stdin=DEVNULL,
            stdout=DEVNULL,
            stderr=PIPE,
            cwd=root,
        )

        if p.wait():
            try:
                err = p.stderr.read().decode()[-1000:]
            except UnicodeDecodeError:
                err = "unknown error"

            raise NodeEdgeException(f"Could not create env: {err}")
