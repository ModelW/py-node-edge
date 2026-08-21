"""Core engine running Node code from Python over a local socket."""

import json
import os
import socket
from collections.abc import Iterator, Mapping, MutableMapping, MutableSequence, Sequence
from dataclasses import dataclass
from enum import Enum
from hashlib import sha256
from itertools import chain
from pathlib import Path
from queue import Queue
from selectors import EVENT_READ, DefaultSelector
from subprocess import DEVNULL, PIPE, Popen
from tempfile import gettempdir
from threading import Event, Thread
from typing import Any, TextIO, TypeVar

from ._binaries import default_node_bin, default_npm_command
from ._utils import xdg_state_home
from .exceptions import (
    JavaScriptError,
    NodeEdgeException,
    NodeEdgeTypeError,
    NodeEdgeValueError,
)

__all__ = [
    "JavaScriptArrayProxy",
    "JavaScriptMappingProxy",
    "JavaScriptPointer",
    "JavaScriptProxy",
    "NodeEngine",
    "PointerIsh",
    "as_mapping",
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
    success: bool | None = None
    result: Any | None = None
    error: Mapping | None = None


@dataclass
class Await:
    """
    An await request + response/exception
    """

    pointer_id: int
    event: Event
    success: bool | None = None
    result: Any | None = None
    error: Mapping | None = None


@dataclass
class Import:
    """
    An import request + response/exception
    """

    module: str
    name: str
    event: Event
    success: bool | None = None
    result: Any | None = None
    error: Mapping | None = None


class CallType(Enum):
    """
    Because of the conceptual similarity, both calling a function or accessing
    an index are the same message. If the type os func then it'll do
    obj(*args) and otherwise it'll do obj[args[0]].
    """

    func = "func"
    item = "item"
    attr = "attr"
    entry = "entry"
    prop_count = "prop_count"
    prop_set = "prop_set"
    prop_del = "prop_del"
    prop_list = "prop_list"
    item_insert = "item_insert"


@dataclass
class Call:
    """
    A request to "call" on the pointed object
    """

    pointer_id: int
    args: list[Any]
    type: CallType
    event: Event
    success: bool | None = None
    result: Any | None = None
    result_type: str | None = None
    error: Mapping | None = None


@dataclass
class CallOutput:
    """
    Output of a JS "call". We need the "type" field because the "result" might
    nor not be a pointer to the JS side while the type informs us on things
    that are not necessarily an exception (like out of bounds index) but also
    are not the normal result. We could have decided to do it JS-style and
    return undefined whenever but the goal here is to make those JS objects
    feel as pythonic as possible.
    """

    result: Any
    type: str


class Finish:
    """
    A finish request, that closes the engine
    """


@dataclass
class ReleasePointer:
    """
    Tells the JS side to delete references to this pointer, which will
    eventually lead to the garbage collector being able to release the
    associated memory.
    """

    id: int


@dataclass
class JavaScriptPointer:
    """
    A pointer to a JavaScript object
    """

    id: int
    awaitable: bool
    array: bool
    repr: str
    engine: "NodeEngine"

    # noinspection PyProtectedMember
    def __del__(self):
        """
        On object deletion, notify the JS side so that it can also free its
        memory.
        """

        self.engine._events.put(ReleasePointer(self.id))

    @property
    def proxy(self) -> "JavaScriptProxy | JavaScriptArrayProxy":
        """
        JS is mixing up arrays, mappings and objects. Well Python isn't so we
        kind of need to deal with that.

        There are several things to consider:

        - If the data was a simple structure, it would have been serialized
          as JSON and we wouldn't be in a proxy (so the "mapping" case rarely
          exists at this point)
        - We know if it's an array because JS tells us
        - By default we're dealing with an object-ish

        There are 3 proxies that exist, we only return the array or the object
        one here. The mapping one can be obtained using the as_mapping()
        function.
        """

        if self.array:
            return JavaScriptArrayProxy(self)
        else:
            return JavaScriptProxy(self)


T = TypeVar("T")
K = TypeVar("K")
V = TypeVar("V")


class JavaScriptArrayProxy(MutableSequence[T]):
    """
    Proxies all the mutable sequence interface calls into poking in the JS
    engine.
    """

    def __init__(self, pointer: JavaScriptPointer) -> None:
        self.__dict__["__pointer__"] = pointer

    def __repr__(self):
        r = self.__dict__["__pointer__"].repr
        return f"<JavaScriptArrayProxy {r}>"

    def insert(self, index: int, value: T) -> None:
        self.__dict__["__pointer__"].engine.call(
            self, [index, value], CallType.item_insert
        )

    def __getitem__(self, index: int) -> T:  # type: ignore[override]
        item = self.__dict__["__pointer__"].engine.call(self, [index], CallType.item)

        if item.type == "out_of_bounds":
            msg = f"Index {index} out of range"
            raise IndexError(msg)
        elif item.type == "not_an_array":
            msg = "Not an array"
            raise TypeError(msg)
        elif item.type != "success":
            msg = "Unexpected error"
            raise TypeError(msg)

        return item.result

    def __setitem__(self, index: int, value: T) -> None:  # type: ignore[override]
        self.__dict__["__pointer__"].engine.call(
            self, [index, value], CallType.prop_set
        )

    def __delitem__(self, index: int) -> None:  # type: ignore[override]
        self.__dict__["__pointer__"].engine.call(self, [index], CallType.prop_del)

    def __len__(self) -> int:
        return (
            self.__dict__["__pointer__"]
            .engine.call(self, [], CallType.prop_count)
            .result
        )


class JavaScriptMappingProxy(MutableMapping[K, V]):
    """
    Proxies all the mutable mapping interface calls into poking in the remote
    JS engine.
    """

    def __init__(self, pointer: JavaScriptPointer) -> None:
        self.__dict__["__pointer__"] = pointer

    def __repr__(self):
        r = self.__dict__["__pointer__"].repr
        return f"<JavaScriptMappingProxy {r}>"

    def __setitem__(self, key: K, value: V) -> None:
        self.__dict__["__pointer__"].engine.call(self, [key, value], CallType.prop_set)

    def __delitem__(self, key: K) -> None:
        self.__dict__["__pointer__"].engine.call(self, [key], CallType.prop_del)

    def __getitem__(self, key: K) -> V:
        item = self.__dict__["__pointer__"].engine.call(self, [key], CallType.entry)

        if item.type == "no_such_entry":
            msg = f"No such property {key}"
            raise KeyError(msg)
        elif item.type != "success":
            msg = "Unexpected error"
            raise TypeError(msg)

        return item.result

    def __len__(self) -> int:
        return (
            self.__dict__["__pointer__"]
            .engine.call(self, [], CallType.prop_count)
            .result
        )

    def __iter__(self) -> Iterator[K]:
        yield from (
            self.__dict__["__pointer__"]
            .engine.call(self, [], CallType.prop_list)
            .result
        )


class JavaScriptProxy:
    """
    Behaves more or less like a JS object. Not really a mapping although
    you can call __getitem__, which is identical to __getattr__. All calls
    are proxied to the JS side, including calls to __call__.
    """

    def __init__(
        self, pointer: JavaScriptPointer, auto_bind: JavaScriptPointer | None = None
    ) -> None:
        self.__dict__["__pointer__"] = pointer
        self.__dict__["__auto_bind__"] = auto_bind

    def __repr__(self):
        r = self.__dict__["__pointer__"].repr
        return f"<JavaScriptProxy {r}>"

    def __getattr__(self, item):
        attr = self.__dict__["__pointer__"].engine.call(self, [item], CallType.attr)

        if attr.type == "no_attributes":
            msg = "No attributes on this type"
            raise TypeError(msg)
        elif attr.type == "no_such_property":
            msg = f"No such property {item}"
            raise AttributeError(msg)
        elif attr.type != "success":
            msg = "Unexpected error"
            raise TypeError(msg)

        out = attr.result

        if isinstance(out, JavaScriptProxy):
            out.__dict__["__auto_bind__"] = self.__dict__["__pointer__"]

        return out

    def __getitem__(self, item):
        return JavaScriptMappingProxy(self.__dict__["__pointer__"]).__getitem__(item)

    def __setattr__(self, key, value):
        self.__dict__["__pointer__"].engine.call(self, [key, value], CallType.prop_set)

    def __delattr__(self, item):
        self.__dict__["__pointer__"].engine.call(self, [item], CallType.prop_del)

    def __call__(self, *args, **kwargs):
        return (
            self.__dict__["__pointer__"]
            .engine.call(
                self,
                dict(args=args, auto_bind=self.__dict__["__auto_bind__"]),
                CallType.func,
            )
            .result
        )


def as_mapping(obj: Any) -> "JavaScriptMappingProxy":
    """
    Converts the pointer (or another proxy) into a mapping proxy, in case you
    want a full dictionary interface in your JS object.
    """

    if isinstance(obj, JavaScriptPointer):
        return JavaScriptMappingProxy(obj)
    elif isinstance(obj, JavaScriptProxy):
        return JavaScriptMappingProxy(obj.__dict__["__pointer__"])
    else:
        msg = "Object must be a JavaScriptPointer or JavaScriptProxy"
        raise NodeEdgeTypeError(msg)


PointerIsh = (
    JavaScriptPointer | JavaScriptProxy | JavaScriptArrayProxy | JavaScriptMappingProxy
)


def _get_pointer(pointer: Any) -> JavaScriptPointer:
    """
    Get the pointer from a proxy
    """

    if isinstance(pointer, JavaScriptPointer):
        return pointer
    elif isinstance(
        pointer, (JavaScriptArrayProxy, JavaScriptProxy, JavaScriptMappingProxy)
    ):
        return pointer.__dict__["__pointer__"]
    else:
        msg = "pointer must be a JavaScriptPointer or JavaScriptProxy"
        raise NodeEdgeTypeError(msg)


def _deep_point(obj):
    """
    In order to be able to make calls, we need to be able to pass arguments.
    This will convert a JSON-serializable structure into something a bit more
    verbose but which allows to have references to JS pointers.
    """

    if isinstance(obj, JavaScriptPointer):
        return dict(type="pointer", id=obj.id)
    elif isinstance(obj, (JavaScriptArrayProxy, JavaScriptProxy)):
        return dict(type="pointer", id=obj.__dict__["__pointer__"].id)
    elif isinstance(obj, (str, bytes, bytearray, int, float, bool)):
        return dict(type="flat", data=obj)
    elif isinstance(obj, Sequence):
        return dict(type="sequence", data=[_deep_point(i) for i in obj])
    elif isinstance(obj, Mapping):
        return dict(type="mapping", data={k: _deep_point(v) for k, v in obj.items()})
    elif obj is None:
        return dict(type="flat", data=None)
    else:
        msg = f"Cannot serialize {type(obj)}"
        raise NodeEdgeTypeError(msg)


class NodeEngine:
    """
    Manages the Node process, and the communication with it. It allows to
    run JS code from Python, including installing dependencies, creating
    the environment, etc.
    """

    def __init__(
        self,
        package: Mapping,
        npm_bin: str | None = None,
        node_bin: str | None = None,
        debug: bool = False,
        env_dir_candidates: Sequence[str | Path] | None = None,
    ):
        """Configure the engine (without starting it).

        Parameters
        ----------
        package
            A package.json-like mapping describing the Node environment,
            most notably its ``dependencies``.
        npm_bin
            Path to the ``npm`` binary. Defaults to the one bundled by
            ``nodejs-wheel-binaries`` if installed, otherwise ``npm`` from
            the PATH.
        node_bin
            Path to the ``node`` binary, same default logic as ``npm_bin``.
        debug
            If True, the Node process inherits stdio so its output becomes
            visible.
        env_dir_candidates
            Directories in which the Node environment may be created. The
            first one that works is used. Defaults to the XDG state home
            then the system temp directory.
        """
        default_paths = [Path(gettempdir())]

        if Path.home():
            default_paths.insert(0, xdg_state_home())

        self.package = package
        self.npm_command: list[str] = (
            [npm_bin] if npm_bin is not None else default_npm_command()
        )
        self.npm_bin = self.npm_command[0]
        self.node_bin = node_bin if node_bin is not None else default_node_bin()
        self.debug = debug
        self.env_dir_candidates = (
            default_paths
            if env_dir_candidates is None
            else [Path(i) for i in env_dir_candidates]
        )
        self._env_dir: Path | None = None
        self._listen_socket: socket.socket | None = None
        self._remote_conn: socket.socket | None = None
        self._remote_read: TextIO | None = None
        self._remote_proc: Popen | None = None
        self._events: Queue[Any] = Queue(1000)
        self._remote_thread: Thread | None = None
        self._events_thread: Thread | None = None
        self._pending: dict[str, Eval | Await | Import | Call] = {}
        self._dead = False

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

        for candidate in self.env_dir_candidates:
            full_path = candidate / "node_edge" / "envs" / self.package_signature

            if self._try_env_candidate(full_path):
                return full_path

        msg = "Could not find/create env dir"
        raise NodeEdgeException(msg)

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

        if not (root / "index.js").exists():
            self._write_package_json(root)
            self._npm_install(root)

        self._write_runtime(root)

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

        with (root / "package.json").open("w") as f:
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

        with (
            (root / "index.js").open("w", encoding="utf-8") as o,
            (Path(__file__).parent / "runtime.js").open(encoding="utf-8") as i,
        ):
            while buf := i.read(1024**2):
                o.write(buf)

        (root / "index.js").chmod(0o755)

    def _npm_install(self, root: Path):
        """
        Runs NPM install in the environment directory.

        Parameters
        ----------
        root
            The environment directory
        """

        p = Popen(
            args=[*self.npm_command, "install"],
            stdin=DEVNULL,
            stdout=DEVNULL,
            stderr=PIPE,
            cwd=root,
            env=self._subprocess_env(),
        )

        if p.wait():
            try:
                err = p.stderr.read().decode()[-1000:] if p.stderr else "unknown error"
            except UnicodeDecodeError:
                err = "unknown error"

            msg = f"Could not create env: {err}"
            raise NodeEdgeException(msg)

    def _fail_pending(self) -> None:
        """
        Fails all pending requests. Called when the connection to the Node
        process is lost, so that threads blocked waiting for a reply receive
        an error instead of waiting forever.
        """

        self._dead = True

        while self._pending:
            _, pending_event = self._pending.popitem()
            pending_event.success = False
            pending_event.error = {"message": "Node process died"}
            pending_event.event.set()

    def _resolve_pending(self, event_id: str, payload: Mapping, success: bool) -> None:
        """
        Resolves a pending request with the response received from the JS
        side, and wakes up the thread that is blocked waiting for it.

        Parameters
        ----------
        event_id
            Correlation ID of the request
        payload
            Payload of the response message
        success
            Whether the JS side reported a success or an error
        """

        if event_id not in self._pending:
            return

        pending_event = self._pending.pop(event_id)
        pending_event.success = success

        if success:
            pending_event.result = payload["result"]

            if isinstance(pending_event, Call):
                pending_event.result_type = payload["type"]
        else:
            pending_event.error = payload["error"]

        pending_event.event.set()

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
                case Await(pointer_id=pointer_id):
                    self._pending[str(id(evt))] = evt
                    self._await(event_id=id(evt), pointer_id=pointer_id)
                case Import(module=module, name=name):
                    self._pending[str(id(evt))] = evt
                    self._import(event_id=id(evt), module=module, name=name)
                case Call(pointer_id=pointer_id, args=args, type=type_):
                    self._pending[str(id(evt))] = evt
                    self._call(
                        pointer_id=pointer_id,
                        args=args,
                        call_type=type_,
                        event_id=id(evt),
                    )
                case ReleasePointer(id=pointer_id):
                    self._release_pointer(pointer_id=pointer_id)
                case RemoteMessage(
                    content={
                        "type": str() as msg_type,
                        "payload": payload,
                        "event_id": event_id,
                    }
                ) if msg_type.endswith(("_result", "_error")):
                    self._resolve_pending(
                        event_id=event_id,
                        payload=payload,
                        success=msg_type.endswith("_result"),
                    )

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
            eof = False

            while not eof:
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
                    else:
                        # recv() returned b"": the remote process closed the
                        # connection (it probably died). Stop listening,
                        # otherwise this loop spins forever on a dead socket.
                        eof = True
                except BlockingIOError:
                    pass
        except Exception as e:
            match e:
                case OSError(errno=9):
                    pass
                case _:
                    raise
        finally:
            # Wake up anything still blocked on a pending request so that
            # the caller gets an error instead of waiting forever.
            self._events.put(Finish())
            self._fail_pending()

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

        try:
            self._remote_conn.send(
                json.dumps(data, ensure_ascii=True).encode("ascii") + b"\n"
            )
        except OSError:
            # The connection is gone (typically, the engine is stopping and
            # garbage-collected pointers are still trying to release
            # themselves). Nothing useful can be done about it.
            pass

    def _subprocess_env(self) -> dict[str, str]:
        """
        Environment for the node/npm subprocesses. The directory of the node
        binary is prepended to the PATH: npm is a script whose shebang
        expects `node` to be findable, which isn't a given when using the
        binaries bundled by nodejs-wheel (or any custom node_bin outside of
        the PATH).
        """

        env = dict(os.environ)
        node_dir = str(Path(self.node_bin).absolute().parent)

        if Path(self.node_bin).is_absolute() or "/" in self.node_bin:
            env["PATH"] = node_dir + os.pathsep + env.get("PATH", "")

        return env

    def start(self):
        """
        Starts the engine. This will start the remote process, and the events
        loop. The remote process will connect back through the socket and
        when that happens we'll start the events loop.
        """

        root = self.create_env()

        self._listen_socket = socket.create_server(
            address=("127.0.0.1", 0),
            family=socket.AF_INET,
        )
        _, port, *_ = self._listen_socket.getsockname()

        extra = {}

        if not self.debug:
            extra.update(
                stdin=DEVNULL,
                stdout=DEVNULL,
                stderr=DEVNULL,
            )

        self._remote_proc = Popen(
            args=[self.node_bin, "./index.js", f"{port}"],
            cwd=root,
            env=self._subprocess_env(),
            **extra,
        )

        # Daemon threads: if the user forgets to stop() the engine (or an
        # exception bypasses it), the interpreter must still be able to exit
        # instead of hanging forever, e.g. in CI.
        self._remote_thread = Thread(target=self._run_listen_remote, daemon=True)
        self._events_thread = Thread(target=self._run_events, daemon=True)

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

    def _release_pointer(self, pointer_id: int):
        """
        Releases a pointer on the remote process.

        Parameters
        ----------
        pointer_id
            The ID of the pointer to release
        """

        self._send_message(
            {
                "type": "release_pointer",
                "payload": {
                    "pointer_id": pointer_id,
                },
            }
        )

    def _final_value(self, msg):
        """
        The JS side can either return a JSON-serializable value, or a pointer
        to a value. This will automatically either return the value or wrap
        the pointer in a JavaScriptPointer object. The JavaScriptPointer is
        supposed to be transparent for use as a Python object and will proxy
        all the calls to the remote process.
        """

        if msg["type"] == "pointer":
            return JavaScriptPointer(
                id=msg["id"],
                awaitable=msg["awaitable"],
                repr=msg["repr"],
                array=msg["array"],
                engine=self,
            ).proxy
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

        if self._dead:
            msg_err = "Node process died"
            raise NodeEdgeException(msg_err)

        req = Eval(code, Event())
        self._events.put(req)
        req.event.wait()

        if req.success:
            return self._final_value(req.result)

        raise JavaScriptError(**(req.error or {}))

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

    def await_(self, pointer: PointerIsh) -> Any:
        """
        Synchronously awaits a JavaScript pointer and returns the value.

        It will block the thread until the result is available.

        Parameters
        ----------
        pointer
            The pointer to await
        """

        pointer = _get_pointer(pointer)

        if not pointer.awaitable:
            msg = "Cannot await a non-awaitable pointer"
            raise NodeEdgeValueError(msg)

        if self._dead:
            msg_err = "Node process died"
            raise NodeEdgeException(msg_err)

        req = Await(pointer.id, Event())
        self._events.put(req)
        req.event.wait()

        if req.success:
            return self._final_value(req.result)

        raise JavaScriptError(**(req.error or {}))

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

    def resolve(self, value: Any) -> Any:
        """
        Awaits the value if it is an awaitable pointer (typically, the return
        value of an async JS function), otherwise returns it unchanged.

        This makes it convenient to call JS functions without worrying about
        whether they are async or not.

        Parameters
        ----------
        value
            Any value, potentially a pointer/proxy to a JS Promise
        """

        try:
            pointer = _get_pointer(value)
        except NodeEdgeTypeError:
            return value

        if pointer.awaitable:
            return self.await_(pointer)

        return value

    def import_from(self, module: str, name: str = "default") -> Any:
        """
        Imports a name from a JS module (by default, "default") and returns
        a pointer ot that object. Which then allows you to call its methods
        etc.
        """

        if self._dead:
            msg_err = "Node process died"
            raise NodeEdgeException(msg_err)

        req = Import(module, name, Event())
        self._events.put(req)
        req.event.wait()

        if req.success:
            return self._final_value(req.result)

        raise JavaScriptError(**(req.error or {}))

    def _import(self, event_id: int, module: str, name: str) -> None:
        """
        Sending the import message to the other side (running here to be in the
        right thread)
        """

        self._send_message(
            dict(
                type="import",
                payload=dict(
                    event_id=f"{event_id}",
                    module=module,
                    name=name,
                ),
            )
        )

    def call(
        self, pointer: PointerIsh, args: Sequence[Any], call_type: CallType
    ) -> CallOutput:
        """
        Calls a method on a pointer and returns the result.

        It will block the thread until the result is available.

        Parameters
        ----------
        pointer
            The pointer to call
        args
            The arguments to pass to the method
        call_type
            The type of call to make
        """

        pointer = _get_pointer(pointer)

        clean_args: list[Any] = _deep_point(args)
        if self._dead:
            msg_err = "Node process died"
            raise NodeEdgeException(msg_err)

        req = Call(pointer.id, clean_args, call_type, Event())
        self._events.put(req)
        req.event.wait()

        if req.success:
            return CallOutput(
                result=self._final_value(req.result),
                type=req.result_type or "",
            )

        raise JavaScriptError(**(req.error or {}))

    def _call(
        self, pointer_id: str, args: list[Any], call_type: CallType, event_id: int
    ) -> None:
        """
        Sending the call message to the other side (running here to be in the
        right thread)
        """

        self._send_message(
            dict(
                type="call",
                payload=dict(
                    event_id=f"{event_id}",
                    pointer_id=pointer_id,
                    args=args,
                    call_type=call_type.value,
                ),
            )
        )
