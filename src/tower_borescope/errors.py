"""Exception types shared across the package."""


class BorescopeError(Exception):
    """A problem reported to the user as a plain message rather than a traceback."""


class CameraDisconnectedError(BorescopeError):
    """The borescope stopped responding or was unplugged while streaming."""
