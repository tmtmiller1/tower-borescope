"""Hands-free captures: time-lapse, automatic stacked stills and motion snapshots."""

from __future__ import annotations

import subprocess
import threading
from dataclasses import dataclass
from pathlib import Path

import cv2

from tower_borescope.app.pipeline.events import PipelineEvents
from tower_borescope.app.pipeline.state import (
    AUTO_STACK_STILL_SECONDS,
    MOTION_COOLDOWN_SECONDS,
    PipelineState,
)
from tower_borescope.app.pipeline.stills import StillCapture
from tower_borescope.capture.ffmpeg import find_ffmpeg
from tower_borescope.capture.storage import timestamp
from tower_borescope.config import DataPaths
from tower_borescope.image_types import BgrImage
from tower_borescope.imaging.meters import MotionDetector

TIMELAPSE_FRAMERATE = "10"
TIMELAPSE_BITRATE = "6M"
TIMELAPSE_FRAME_PATTERN = "frame_%05d.png"
MIN_TIMELAPSE_FRAMES = 2
MOTION_TRIGGER_FACTOR = 2.0


@dataclass(slots=True)
class TimeLapseRun:
    """Folder and progress of a running time-lapse.

    Attributes:
        stamp: Timestamp shared by the frame folder and the finished video.
        folder: Folder receiving numbered PNG frames.
        count: Frames written so far.
        last: Monotonic time of the latest frame.
    """

    stamp: str
    folder: Path
    count: int = 0
    last: float = float("-inf")


def timelapse_command(ffmpeg: str, folder: Path, output: Path) -> list[str]:
    """ffmpeg command that encodes numbered PNG frames into an H.264 MP4.

    Args:
        ffmpeg: ffmpeg executable.
        folder: Folder holding ``frame_00001.png`` and the following frames.
        output: Video file to write.

    Returns:
        The command line.
    """
    command = [ffmpeg, "-hide_banner", "-loglevel", "error", "-y"]
    command += [
        "-framerate",
        TIMELAPSE_FRAMERATE,
        "-i",
        str(folder / TIMELAPSE_FRAME_PATTERN),
    ]
    command += ["-c:v", "h264_videotoolbox", "-b:v", TIMELAPSE_BITRATE]
    command += ["-pix_fmt", "yuv420p", "-tag:v", "avc1", "-movflags", "+faststart"]
    return [*command, str(output)]


class TimeLapse:
    """Writes a frame every ``timelapse_interval`` seconds and assembles a video."""

    def __init__(
        self, state: PipelineState, paths: DataPaths, events: PipelineEvents
    ) -> None:
        self._state = state
        self._paths = paths
        self._events = events
        self._run: TimeLapseRun | None = None

    @property
    def running(self) -> bool:
        """True while a time-lapse is capturing frames."""
        return self._run is not None

    def sync(self) -> None:
        """Start or finish the time-lapse to match the interval setting."""
        interval = self._state.timelapse_interval
        if interval > 0 and self._run is None:
            stamp = timestamp()
            folder = self._paths.pictures / f"timelapse_{stamp}"
            folder.mkdir(parents=True, exist_ok=True)
            self._run = TimeLapseRun(stamp, folder)
            self._events.timelapse_changed(True, 0)
        elif interval <= 0 and self._run is not None:
            self.finish()

    def capture(self, image: BgrImage, now: float) -> None:
        """Write ``image`` as the next frame when the interval has passed.

        Args:
            image: Processed frame.
            now: Monotonic time of the frame.
        """
        run = self._run
        if run is None or now - run.last < self._state.timelapse_interval:
            return
        run.last = now
        run.count += 1
        cv2.imwrite(str(run.folder / f"frame_{run.count:05d}.png"), image)
        self._events.timelapse_changed(True, run.count)

    def finish(self) -> None:
        """Stop capturing and assemble the video on a worker thread."""
        run, self._run = self._run, None
        if run is None:
            return
        self._events.timelapse_changed(False, run.count)
        if run.count < MIN_TIMELAPSE_FRAMES:
            return
        output = self._paths.movies / f"timelapse_{run.stamp}.mp4"
        worker = threading.Thread(target=self._assemble, args=(run, output), daemon=True)
        worker.start()

    def _assemble(self, run: TimeLapseRun, output: Path) -> None:
        """Encode the frames with ffmpeg and report the result."""
        failed = f"Time-lapse video failed; frames are in {run.folder}"
        ffmpeg = find_ffmpeg()
        if ffmpeg is None:
            self._events.notice(failed)
            return
        output.parent.mkdir(parents=True, exist_ok=True)
        command = timelapse_command(ffmpeg, run.folder, output)
        try:
            result = subprocess.run(command, stdin=subprocess.DEVNULL, check=False)
        except OSError:
            self._events.notice(failed)
            return
        if result.returncode != 0:
            self._events.notice(failed)
            return
        self._events.captured("video", str(output))
        self._events.notice(f"Time-lapse saved ({run.count} frames)")


class Automation:
    """Motion measurement and the captures it drives.

    Attributes:
        motion: Motion detector fed with raw frames.
        timelapse: Time-lapse writer.
    """

    def __init__(
        self,
        state: PipelineState,
        stills: StillCapture,
        paths: DataPaths,
        events: PipelineEvents,
    ) -> None:
        self.motion = MotionDetector()
        self.timelapse = TimeLapse(state, paths, events)
        self._state = state
        self._stills = stills
        self._events = events
        self._armed = True
        self._last_motion_shot = float("-inf")

    def measure(self, raw: BgrImage, now: float) -> float:
        """Update the motion detector with a raw frame.

        Args:
            raw: Decoded camera frame.
            now: Monotonic time of the frame.

        Returns:
            The motion level.
        """
        return self.motion.update(raw, now)

    def after_frame(self, image: BgrImage, motion: float, now: float) -> None:
        """Run the time-lapse, automatic stack and motion snapshot for one frame.

        Args:
            image: Processed frame.
            motion: Motion level returned by :meth:`measure` for this frame.
            now: Monotonic time of the frame.
        """
        self.timelapse.capture(image, now)
        self._auto_stack(now)
        self._motion_snapshot(image, motion, now)

    def _auto_stack(self, now: float) -> None:
        """Request a stacked still once the scene has been still long enough.

        One still is taken per steady period; motion re-arms the trigger.
        """
        still_for = self.motion.still_seconds(now)
        if not self._state.auto_stack:
            return
        if still_for == 0:
            self._armed = True
        elif self._armed and still_for >= AUTO_STACK_STILL_SECONDS:
            if self._stills.stacking:
                return
            self._armed = False
            self._stills.request_stack()
            self._events.notice("Holding still: taking a stacked still")

    def _motion_snapshot(self, image: BgrImage, motion: float, now: float) -> None:
        """Save a snapshot on strong motion, at most once per cooldown."""
        if not self._state.motion_trigger:
            return
        strong = motion > self.motion.threshold * MOTION_TRIGGER_FACTOR
        if strong and now - self._last_motion_shot > MOTION_COOLDOWN_SECONDS:
            self._last_motion_shot = now
            self._stills.save_image(image, "motion")
            self._events.notice("Motion: snapshot saved")
