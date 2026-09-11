"""Phone monitor and virtual camera."""

from __future__ import annotations

from collections.abc import Callable
from typing import Final

from PySide6.QtCore import QObject, Qt, Signal

from tower_borescope.app.dialogs.qr_dialog import QrDialog
from tower_borescope.app.window.context import WindowContext
from tower_borescope.app.window.view_panel import REMOTE_OFF_TEXT, ShareGroup
from tower_borescope.remote.server import RemoteServer

SNAPSHOT_REQUEST: Final = "snapshot"
RECORD_REQUEST: Final = "record"


class ShareController(QObject):
    """Starts and stops the phone monitor and the virtual camera.

    Requests from the phone page arrive on the server's HTTP threads and are handed to
    the GUI thread through ``remote_request``.

    Attributes:
        remote_request: Emits ``"snapshot"`` or ``"record"`` for a phone page button.
        ctx: Shared window state.
        group: The SHARE group.
        qr: QR code dialog while the phone monitor runs, or None.
    """

    remote_request = Signal(str)

    def __init__(
        self,
        ctx: WindowContext,
        snapshot: Callable[[], None],
        toggle_recording: Callable[[], None],
    ) -> None:
        super().__init__(ctx.window)
        self.ctx = ctx
        self.qr: QrDialog | None = None
        self._requests = {SNAPSHOT_REQUEST: snapshot, RECORD_REQUEST: toggle_recording}
        self.group = ShareGroup(self.toggle_remote, self.toggle_vcam)
        self.remote_request.connect(
            self._handle_request, Qt.ConnectionType.QueuedConnection
        )

    def toggle_remote(self) -> None:
        """Start the phone monitor with its QR code, or stop it."""
        if self.ctx.pipeline.remote is None:
            self._start_remote()
        else:
            self.stop_remote()

    def _start_remote(self) -> None:
        """Serve the live view and show the address as a QR code."""
        server = RemoteServer(
            on_snapshot=self._phone_snapshot, on_record=self._phone_record
        )
        try:
            server.start()
        except OSError as error:
            self.ctx.toast(f"Could not start the phone monitor: {error}")
            self.group.remote_btn.setChecked(False)
            return
        self.ctx.pipeline.set_remote(server)
        self.group.remote_label.setText("On: " + server.url)
        self.group.remote_btn.setChecked(True)
        self.qr = QrDialog(server.url, self.ctx.window)
        self.qr.show()

    def stop_remote(self) -> None:
        """Stop publishing, stop the server and close the QR code."""
        server = self.ctx.pipeline.remote
        self.ctx.pipeline.set_remote(None)
        if server is not None:
            server.stop()
        self.group.remote_label.setText(REMOTE_OFF_TEXT)
        self.group.remote_btn.setChecked(False)
        if self.qr is not None:
            self.qr.close()
            self.qr = None

    def _phone_snapshot(self) -> None:
        """Snapshot button on the phone page, called on an HTTP thread."""
        self.remote_request.emit(SNAPSHOT_REQUEST)

    def _phone_record(self) -> bool:
        """Record button on the phone page; returns the recording state it requests."""
        self.remote_request.emit(RECORD_REQUEST)
        return not self.ctx.pipeline.recording

    def _handle_request(self, request: str) -> None:
        """Run a phone page request on the GUI thread."""
        handler = self._requests.get(request)
        if handler is not None:
            handler()

    def toggle_vcam(self) -> None:
        """Ask the pipeline to start or stop the virtual camera."""
        state = self.ctx.pipeline.state
        state.want_vcam = not state.want_vcam
        self.group.vcam_btn.setChecked(state.want_vcam)

    def on_vcam_changed(self, on: bool) -> None:
        """Reflect the virtual camera state the pipeline reports."""
        self.group.vcam_btn.setChecked(on)
