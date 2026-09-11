"""Frame outputs: the phone monitor and the pyvirtualcam virtual camera.

The virtual camera needs OBS with its camera extension installed. Without it,
pyvirtualcam raises ``RuntimeError`` on open; the pipeline then clears the request and
reports the reason instead of failing.

pyvirtualcam is an optional dependency (the ``virtual-camera`` extra) and the
downloadable application does not include it; ``vcam_available`` tells the window
whether to offer the control at all.
"""

from __future__ import annotations

from importlib.util import find_spec
from typing import Final, Protocol

from tower_borescope.app.pipeline.events import PipelineEvents
from tower_borescope.app.pipeline.state import PipelineState
from tower_borescope.device.constants import FPS
from tower_borescope.image_types import BgrImage
from tower_borescope.remote.server import RemoteServer

OBS_HINT = "Virtual camera needs OBS (with its virtual camera) installed: "
VCAM_MODULE: Final = "pyvirtualcam"
VCAM_MISSING_TEXT: Final = (
    "Virtual camera is not included in this build. "
    "It needs the source version with the virtual-camera extra."
)
ERROR_TEXT_LIMIT = 80
# pyvirtualcam documents RuntimeError for a missing backend and ValueError or TypeError
# for a frame that does not match the camera; OSError covers a device that went away.
CAMERA_ERRORS = (RuntimeError, ValueError, TypeError, OSError)


class CameraSink(Protocol):
    """The part of ``pyvirtualcam.Camera`` the pipeline uses."""

    @property
    def device(self) -> str:
        """Name of the virtual camera device."""
        ...

    def send(self, frame: BgrImage) -> None:
        """Send one frame."""
        ...

    def close(self) -> None:
        """Release the device."""
        ...


def vcam_available() -> bool:
    """Whether pyvirtualcam is installed.

    Returns:
        True when the ``pyvirtualcam`` package can be imported; False in the
        downloadable application and in a source checkout without the extra.
    """
    return find_spec(VCAM_MODULE) is not None


def open_camera(width: int, height: int) -> CameraSink:
    """Open a BGR virtual camera at the camera frame rate.

    Args:
        width: Frame width in pixels.
        height: Frame height in pixels.

    Returns:
        The open camera.

    Raises:
        ImportError: When pyvirtualcam cannot load its native backend.
        RuntimeError: When no virtual camera backend is available.
        ValueError: When the size or format is not accepted.
    """
    import pyvirtualcam

    camera: CameraSink = pyvirtualcam.Camera(
        width=width, height=height, fps=FPS, fmt=pyvirtualcam.PixelFormat.BGR
    )
    return camera


class FrameOutputs:
    """Publishes processed frames to the phone monitor and the virtual camera.

    Attributes:
        remote: Running phone monitor server, or None when it is off.
    """

    def __init__(self, state: PipelineState, events: PipelineEvents) -> None:
        self.remote: RemoteServer | None = None
        self._state = state
        self._events = events
        self._camera: CameraSink | None = None

    @property
    def vcam_active(self) -> bool:
        """True while the virtual camera is open."""
        return self._camera is not None

    def sync_vcam(self, size: tuple[int, int] | None) -> None:
        """Open or close the virtual camera to match ``want_vcam``.

        Args:
            size: Camera frame size, or None before the first frame.
        """
        if self._state.want_vcam and self._camera is None:
            self._camera = self._open(size)
        elif not self._state.want_vcam and self._camera is not None:
            self.close()
            self._events.vcam_changed(False)

    def resize_vcam(self, size: tuple[int, int]) -> None:
        """Reopen an open virtual camera at a new frame size.

        Args:
            size: New camera frame size.
        """
        if self._camera is not None:
            self.close()
            self._camera = self._open(size)

    def send(self, image: BgrImage) -> None:
        """Publish a processed frame to every active output.

        Args:
            image: Processed frame.
        """
        remote = self.remote
        if remote is not None:
            remote.publish(image)
        camera = self._camera
        if camera is None:
            return
        try:
            camera.send(image)
        except CAMERA_ERRORS as error:
            self._events.notice(f"Virtual camera stopped: {error}")
            self.close()
            self._state.want_vcam = False
            self._events.vcam_changed(False)

    def close(self) -> None:
        """Release the virtual camera without reporting a change."""
        camera, self._camera = self._camera, None
        if camera is not None:
            camera.close()

    def _open(self, size: tuple[int, int] | None) -> CameraSink | None:
        """Open the virtual camera for oriented frames, or report why it cannot."""
        if size is None:
            return None
        width, height = size
        if self._state.rotation % 2:
            width, height = height, width
        try:
            camera = open_camera(width, height)
        except (ImportError, *CAMERA_ERRORS) as error:
            self._state.want_vcam = False
            self._events.vcam_changed(False)
            self._events.notice(OBS_HINT + str(error)[:ERROR_TEXT_LIMIT])
            return None
        self._events.vcam_changed(True)
        self._events.notice(f"Virtual camera on ({camera.device})")
        return camera
