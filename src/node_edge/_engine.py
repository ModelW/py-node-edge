import json
import socket
from dataclasses import dataclass
from hashlib import sha256
from itertools import chain
from pathlib import Path
from queue import Queue
from selectors import EVENT_READ, DefaultSelector
from subprocess import DEVNULL, PIPE, Popen
from tempfile import gettempdir
from threading import Event, Thread
from typing import Any, Mapping, Optional, TextIO

from xdg import xdg_state_home

from .exceptions import *

__all__ = [
    "NodeEngine",
    "JavaScriptPointer",
]


@dataclass
class RemoteMessage:
    """
    A JSON message from the JS side
    """

    content: Any


@dataclass
class LocalMessage:
    """
    A JSON message to the JS side
    """

    content: Any


@dataclass
class ProtocolError:
    """
    A protocol error
    """

    message: str


@dataclass
class Eval:
    """
    An eval request + response/exception
    """

    code: str
    event: Event
    success: Optional[bool] = None
    result: Optional[Any] = None
    error: Optional[Mapping] = None


@dataclass
class Await:
    """
    An await request + response/exception
    """

    pointer_id: int
    event: Event
    success: Optional[bool] = None
    result: Optional[Any] = None
    error: Optional[Mapping] = None


class Finish:
    """
    A finish request, that closes the engine
    """


@dataclass
class JavaScriptPointer:
    """
    A pointer to a JavaScript object
    """

    id: int
    awaitable: bool
    repr: str


class NodeEngine:
    """
    Manages the Node process, and the communication with it. It allows to
    run JS code from Python, including installing dependencies, creating
    the environment, etc.
    """

    def __init__(
        self,
        package: Mapping,
        npm_bin: str = "npm",
        keep_lock: bool = True,
        debug: bool = False,
    ):
        self.package = package
        self.npm_bin = npm_bin
        self.debug = debug
        self.keep_lock = keep_lock
        self._env_dir = None
        self._listen_socket: Optional[socket.socket] = None
        self._remote_conn: Optional[socket.socket] = None
        self._remote_read: Optional[TextIO] = None
        self._remote_proc: Optional[Popen] = None
        self._events = Queue(1000)
        self._remote_thread: Optional[Thread] = None
        self._events_thread: Optional[Thread] = None
        self._pending = {}

    @property
    def package_signature(self) -> str:
        """
        We create a signature for the package, so that we can reuse the
        environment if the package is the same (but create new one otherwise)
        """

        return sha256(
            json.dumps(self.package, ensure_ascii=True).encode("ascii")
        ).hexdigest()

    def __enter__(self):
        """
        Starts the engine if used as context manager
        """

        self.start()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        """
        Ensures the engine is stopped if used as context manager
        """

        self.stop()

    def _try_env_candidate(self, path: Path):
        """
        Try to create the env dir, and return True if it worked, False
        otherwise. Several candidates are attempted this way by
        _ensure_env_dir()

        Parameters
        ----------
        path
            The path to try to create
        """

        try:
            path.mkdir(parents=True, exist_ok=True)
        except (PermissionError, NotADirectoryError):
            return False
        else:
            return True

    def _ensure_env_dir(self) -> Path:
        """
        Figures an environment directory, and creates it if it does not yet
        exist. The directory is created in the XDG state directory if possible,
        otherwise in a temporary directory. If none of these work, I have no
        idea what to do, so I raise an exception.
        """

        for candidate in [xdg_state_home(), Path(gettempdir())]:
            full_path = candidate / "node_edge" / "envs" / self.package_signature

            if self._try_env_candidate(full_path):
                return full_path

        raise NodeEdgeException("Could not find/create env dir")

    def ensure_env_dir(self, force: bool = False) -> Path:
        """
        Ensures the environment directory exists. The result is cached, unless
        force is True in which case the guessing will happen again.

        Parameters
        ----------
        force
            If True, the directory is always "re-guessed"
        """

        if self._env_dir is None or force:
            self._env_dir = self._ensure_env_dir()

        return self._env_dir

    def create_env(self) -> Path:
        """
        Creates the Node environment, including installing dependencies
        and writing the runtime that we'll use to communicate with it.
        """

        root = self.ensure_env_dir()

        self._write_package_json(root)
        self._write_runtime(root)
        self._npm_install(root)

        return root

    def _write_package_json(self, root: Path):
        """
        Writes the package.json file in the environment directory based on what
        the user specified, with however a few changes on import type and
        on the scripts section to make sure our expectations are set.

        Notes
        -----
        We're using the scripts section to make sure that we're using the same
        Node binary as NPM is.

        Parameters
        ----------
        root
            The environment directory
        """

        package = {
            **self.package,
            "type": "module",
            "scripts": {
                **self.package.get("scripts", {}),
                "node_edge_runtime": "node ./index.js",
            },
        }

        with open(root / "package.json", "w") as f:
            json.dump(package, f, indent=4)

    def _write_runtime(self, root: Path):
        """
        Writes the runtime file in the environment directory. This is the file
        that will be executed by Node, and that will communicate with the
        Python side.

        Parameters
        ----------
        root
            The environment directory
        """

        with open(root / "index.js", "w", encoding="utf-8") as o, open(
            Path(__file__).parent / "runtime.js", "r", encoding="utf-8"
        ) as i:
            while buf := i.read(1024**2):
                o.write(buf)

        (root / "index.js").chmod(0o755)

    def _npm_install(self, root: Path):
        """
        Runs NPM install in the environment directory.

        Depending on the keep_lock option, the lock file will be discarded or
        kept before running the install.

        Parameters
        ----------
        root
            The environment directory
        """

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

    def _run_events(self):
        """
        Runs the events loop, which is responsible for reading the events
        from the queue (fed both from remote process and from the local
        process) and dispatching them to the appropriate callbacks.
        """

        while evt := self._events.get():
            match evt:
                case Finish():
                    break
                case LocalMessage(content=data):
                    self._send_message(data)
                case Eval(code=code):
                    self._pending[str(id(evt))] = evt
                    self._eval(event_id=id(evt), code=code)
                case RemoteMessage(
                    content={
                        "type": "eval_result",
                        "payload": payload,
                        "event_id": event_id,
                    }
                ):
                    if event_id in self._pending:
                        pending_event = self._pending.pop(event_id)
                        pending_event.success = True
                        pending_event.result = payload["result"]
                        pending_event.event.set()
                case RemoteMessage(
                    content={
                        "type": "eval_error",
                        "payload": payload,
                        "event_id": event_id,
                    }
                ):
                    if event_id in self._pending:
                        pending_event = self._pending.pop(event_id)
                        pending_event.success = False
                        pending_event.error = payload["error"]
                        pending_event.event.set()
                case Await(pointer_id=pointer_id):
                    self._pending[str(id(evt))] = evt
                    self._await(event_id=id(evt), pointer_id=pointer_id)
                case RemoteMessage(
                    content={
                        "type": "await_result",
                        "payload": payload,
                        "event_id": event_id,
                    }
                ):
                    if event_id in self._pending:
                        pending_event = self._pending.pop(event_id)
                        pending_event.success = True
                        pending_event.result = payload["result"]
                        pending_event.event.set()
                case RemoteMessage(
                    content={
                        "type": "await_error",
                        "payload": payload,
                        "event_id": event_id,
                    }
                ):
                    if event_id in self._pending:
                        pending_event = self._pending.pop(event_id)
                        pending_event.success = False
                        pending_event.error = payload["error"]
                        pending_event.event.set()
                case _:
                    print(evt)

    def _run_listen_remote(self):
        """
        Listens to the remote process, and feeds the events queue with the
        messages it receives. This is done in a separate thread, so that
        the events loop can run in parallel.

        Notes
        -----
        The logic in there is a bit convoluted because the underlying socket
        APIs are a bit shitty. The idea is that messages are JSON separated by
        newlines, and that we need to read the socket until we have a full
        message, and then we can parse it and feed the queue.

        We also deal with the fact that the remote process might die, in which
        case we need to stop the events loop.

        And finally, the local process might ask us to stop, in which case we
        just exit the loop and let the thread die.

        We're using a selector in order to be able to poll every second the
        "liveness" of the engine (as opposed to using a blocking read, which
        deals with timeouts in a weird way).
        """

        def handle_line(b_line: bytes):
            try:
                self._events.put(RemoteMessage(json.loads(b_line.decode("utf-8"))))
            except (ValueError, UnicodeError):
                self._events.put(ProtocolError("Could not decode Node output"))

        self._remote_conn, _ = self._listen_socket.accept()
        self._remote_conn.setblocking(False)

        buf = []
        sel = DefaultSelector()
        sel.register(self._remote_conn, EVENT_READ)

        self._events_thread.start()

        try:
            while True:
                sel.select(1)

                try:
                    while chunk := self._remote_conn.recv(1024**2):
                        bits = chunk.split(b"\n")

                        if len(bits) == 1:
                            buf.append(chunk)
                        else:
                            first_line = b"".join(chain(buf, bits[:1]))
                            handle_line(first_line)

                            for line in bits[1:-1]:
                                handle_line(line)

                            buf.clear()
                            buf.append(bits[-1])
                except BlockingIOError:
                    pass
        except Exception as e:
            match (e):
                case OSError(errno=9):
                    pass
                case _:
                    raise

    def send_message(self, data):
        """
        Sends a message to the remote process.

        Parameters
        ----------
        data
            The data to send
        """

        self._events.put(LocalMessage(data))

    def _send_message(self, data):
        """
        Underlying implementation of the send_message() method, which will run
        in the events loop's thread (making sure that the socket is connected
        for example).

        Parameters
        ----------
        data
            The data to send
        """

        self._remote_conn.send(
            json.dumps(data, ensure_ascii=True).encode("ascii") + b"\n"
        )

    def start(self):
        """
        Starts the engine. This will start the remote process, and the events
        loop. The remote process will connect back through the socket and
        when that happens we'll start the events loop.
        """

        root = self.create_env()

        self._listen_socket = socket.create_server(
            address=("::1", 0),
            family=socket.AF_INET6,
        )
        _, port, _, _ = self._listen_socket.getsockname()

        extra = {}

        if not self.debug:
            extra.update(
                stdin=DEVNULL,
                stdout=DEVNULL,
                stderr=DEVNULL,
            )

        self._remote_proc = Popen(
            args=[self.npm_bin, "run", "node_edge_runtime", "--", f"{port}"],
            cwd=root,
            **extra,
        )

        self._remote_thread = Thread(target=self._run_listen_remote)
        self._events_thread = Thread(target=self._run_events)

        self._remote_thread.start()

    def stop(self):
        """
        Stops the engine. This will stop the events loop and disconnect the
        socket. The remote process will then exit on its own due to the
        disconnection.
        """

        if self._remote_conn:
            self._remote_conn.close()

        if self._listen_socket:
            self._listen_socket.close()

        self._events.put(Finish())

    def _final_value(self, msg):
        """
        The JS side can either return a JSON-serializable value, or a pointer
        to a value. This will automatically either return the value or wrap
        the pointer in a JavaScriptPointer object. The JavaScriptPointer is
        supposed to be transparent for use as a Python object and will proxy
        all the calls to the remote process.
        """

        if msg["type"] == "pointer":
            return JavaScriptPointer(msg["id"], msg["awaitable"], msg["repr"])
        elif msg["type"] == "naive":
            return msg["data"]

    def eval(self, code: str) -> Any:
        """
        Synchronously evaluates some code in the remote process and returns the
        value.

        It will block the thread until the result is available.

        Parameters
        ----------
        code
            The JS code to evaluate
        """

        msg = Eval(code, Event())
        self._events.put(msg)
        msg.event.wait()

        if msg.success:
            return self._final_value(msg.result)
        else:
            raise JavaScriptError(**msg.error)

    def _eval(self, event_id: int, code: str) -> None:
        """
        Underlying implementation of the eval() method, which will run in the
        events loop's thread.

        Parameters
        ----------
        event_id
            The ID of the event
        code
            The JS code to evaluate
        """

        self._send_message(
            dict(
                type="eval",
                payload=dict(
                    event_id=f"{event_id}",
                    code=code,
                ),
            )
        )

    def await_(self, pointer: JavaScriptPointer) -> Any:
        """
        Synchronously awaits a JavaScript pointer and returns the value.

        It will block the thread until the result is available.

        Parameters
        ----------
        pointer
            The pointer to await
        """

        if not isinstance(pointer, JavaScriptPointer):
            raise TypeError("Pointer must be a JavaScriptPointer")

        if not pointer.awaitable:
            raise NodeEdgeValueError("Cannot await a non-awaitable pointer")

        msg = Await(pointer.id, Event())
        self._events.put(msg)
        msg.event.wait()

        if msg.success:
            return self._final_value(msg.result)
        else:
            raise JavaScriptError(**msg.error)

    def _await(self, event_id: int, pointer_id: str) -> None:
        """
        Underlying implementation of the await_() method, which will run in the
        events loop's thread.

        Parameters
        ----------
        event_id
            The ID of the event
        pointer_id
            The ID of the pointer to await
        """

        self._send_message(
            dict(
                type="await",
                payload=dict(
                    event_id=f"{event_id}",
                    pointer_id=pointer_id,
                ),
            )
        )
