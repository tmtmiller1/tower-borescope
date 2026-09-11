"""Snapshots, stacked stills and bursts, with metadata sidecars and annotated copies."""

from __future__ import annotations

import threading
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import cv2

from tower_borescope.app.pipeline.events import PipelineEvents
from tower_borescope.app.pipeline.processor import FrameProcessor
from tower_borescope.app.pipeline.state import BURST_FRAMES, PipelineState
from tower_borescope.capture.storage import CAPTURE_PREFIX, timestamp, write_sidecar
from tower_borescope.errors import BorescopeError
from tower_borescope.image_types import BgrImage
from tower_borescope.imaging.stacking import STACK_FRAMES, stack_frames
from tower_borescope.measure.render import render_overlay
from tower_borescope.measure.shapes import OverlaySnapshot

STILL_EXTENSION = ".png"
ANNOTATED_SUFFIX = "_annotated"
STACK_SUFFIX = "_stack"
STACK_SCALE = 2.0


@dataclass(frozen=True, slots=True)
class _SnapshotRequest:
    """A pending snapshot and the overlay to burn into its annotated copy."""

    overlay: OverlaySnapshot | None


def _measurement_metadata(overlay: OverlaySnapshot) -> list[dict[str, Any]]:
    """Kind, points and label of every measurement, for a sidecar."""
    return [
        {
            "kind": item.kind,
            "points": [list(point) for point in item.points],
            "label": item.label(overlay.mm_per_px, overlay.unit),
        }
        for item in overlay.measurements
    ]


class StillCapture:
    """Saves still images from the frame loop.

    Snapshot, stack and burst requests arrive from the GUI thread and are served by
    the next frames: a stacked still collects raw frames, while snapshots and bursts
    take processed frames.

    Attributes:
        folder: Folder that receives stills, bursts and their sidecars.
    """

    def __init__(
        self,
        state: PipelineState,
        processor: FrameProcessor,
        folder: Path,
        events: PipelineEvents,
    ) -> None:
        self.folder = folder
        self._state = state
        self._processor = processor
        self._events = events
        self._snapshot: _SnapshotRequest | None = None
        self._stack_wanted = False
        self._stack_frames: list[BgrImage] | None = None
        self._burst_left = 0
        self._burst_frames: list[BgrImage] = []

    @property
    def stacking(self) -> bool:
        """True while frames for a stacked still are being collected."""
        return self._stack_frames is not None

    def request_snapshot(self, overlay: OverlaySnapshot | None = None) -> None:
        """Save the next processed frame.

        Args:
            overlay: Measurements and annotations for an annotated copy, or None.
        """
        self._snapshot = _SnapshotRequest(overlay)

    def request_stack(self) -> None:
        """Collect the next raw frames into a stacked still."""
        self._stack_wanted = True

    def request_burst(self) -> None:
        """Save the next processed frames as a burst."""
        self._burst_left = BURST_FRAMES

    def collect_stack(self, raw: BgrImage) -> None:
        """Add a raw frame to a stacked still in progress, saving it once complete.

        Args:
            raw: Decoded camera frame before any processing.
        """
        if self._stack_wanted and self._stack_frames is None:
            self._stack_frames = []
            self._stack_wanted = False
        frames = self._stack_frames
        if frames is None:
            return
        frames.append(raw)
        self._events.stack_progress(len(frames), STACK_FRAMES)
        if len(frames) >= STACK_FRAMES:
            self._stack_frames = None
            self._save_stack(frames)
            self._events.stack_progress(0, 0)

    def capture_processed(self, image: BgrImage) -> None:
        """Serve pending snapshot and burst requests with a processed frame.

        Args:
            image: Processed frame.
        """
        pending, self._snapshot = self._snapshot, None
        if pending is not None:
            self.save_image(image, "snapshot", overlay=pending.overlay)
            self._events.notice("Snapshot saved")
        if self._burst_left <= 0:
            return
        self._burst_frames.append(image.copy())
        self._burst_left -= 1
        if self._burst_left == 0:
            frames, self._burst_frames = self._burst_frames, []
            worker = threading.Thread(
                target=self._save_burst, args=(frames,), daemon=True
            )
            worker.start()

    def save_image(
        self,
        image: BgrImage,
        kind: str,
        suffix: str = "",
        overlay: OverlaySnapshot | None = None,
        scale: float = 1.0,
    ) -> Path:
        """Write a PNG with its sidecar, plus an annotated copy when there are items.

        Args:
            image: Frame to save.
            kind: Capture kind recorded in the sidecar and signalled, such as "snapshot".
            suffix: Text after the timestamp in the file name.
            overlay: Measurements and annotations to burn into the annotated copy.
            scale: Output pixels per overlay pixel, 2 for stacked stills.

        Returns:
            The path of the plain PNG.
        """
        self.folder.mkdir(parents=True, exist_ok=True)
        stamp = timestamp()
        path = self.folder / f"{CAPTURE_PREFIX}{stamp}{suffix}{STILL_EXTENSION}"
        cv2.imwrite(str(path), image)
        meta: dict[str, Any] = {"kind": kind, "time": stamp}
        meta.update(self._state.capture_metadata())
        if overlay is not None and overlay.has_items:
            meta["measurements"] = _measurement_metadata(overlay)
            annotated = path.with_name(f"{path.stem}{ANNOTATED_SUFFIX}{STILL_EXTENSION}")
            cv2.imwrite(str(annotated), render_overlay(image, overlay, scale))
            write_sidecar(annotated, meta)
            self._events.captured(kind, str(annotated))
        write_sidecar(path, meta)
        self._events.captured(kind, str(path))
        return path

    def _save_stack(self, frames: list[BgrImage]) -> None:
        """Stack, finish and save a still, reporting frames that do not align."""
        try:
            stacked, used = stack_frames(frames)
        except BorescopeError as error:
            self._events.notice(str(error))
            return
        still = self._processor.finish_stack(stacked)
        # A snapshot requested at the same time lends its overlay to the stacked still.
        pending = self._snapshot
        overlay = pending.overlay if pending is not None else None
        self.save_image(still, "stack", STACK_SUFFIX, overlay, STACK_SCALE)
        height, width = still.shape[:2]
        self._events.notice(f"Stacked still saved ({used} frames, {width}x{height})")

    def _save_burst(self, frames: list[BgrImage]) -> None:
        """Write burst frames into their own folder; runs on a worker thread."""
        folder = self.folder / f"burst_{timestamp()}"
        folder.mkdir(parents=True, exist_ok=True)
        for number, image in enumerate(frames, 1):
            cv2.imwrite(str(folder / f"burst_{number:02d}{STILL_EXTENSION}"), image)
        self._events.captured("snapshot", str(folder / f"burst_01{STILL_EXTENSION}"))
        self._events.notice(f"Burst: {len(frames)} frames saved to {folder.name}")
