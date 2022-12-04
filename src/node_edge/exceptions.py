__all__ = [
    "NodeEdgeException",
    "NodeEdgeValueError",
    "JavaScriptError",
]


class NodeEdgeException(Exception):
    """
    Root exception for things that happen here
    """


class NodeEdgeValueError(NodeEdgeException, ValueError):
    pass


class JavaScriptError(NodeEdgeException):
    """
    Forwarded from the JS side, replicating the JS Error object as closely
    as possible
    """

    def __init__(
        self, message: str = "unknown error", stack: str = "", **extra
    ) -> None:
        self.message = message
        self.stack = stack
        self.extra = extra

    def __str__(self):
        """
        Try to replicate the JS Error object as closely as possible and have
        a nice render
        """

        return f"{self.message}:\n{self.stack}"
