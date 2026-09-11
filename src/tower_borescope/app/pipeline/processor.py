"""Image processing for each frame: the static chain, the live filters and the meters."""

from __future__ import annotations

from tower_borescope.app.frame_info import FrameInfo
from tower_borescope.app.pipeline.state import NORMAL_VIEW, PipelineState
from tower_borescope.app.qt_image import to_qimage
from tower_borescope.image_types import BgrImage
from tower_borescope.imaging.denoise import TemporalDenoise
from tower_borescope.imaging.enhance import enhance, finish_still
from tower_borescope.imaging.geometry import orient
from tower_borescope.imaging.meters import (
    FocusMeter,
    clipped_fraction,
    focus_score,
    histogram,
    zebra,
)
from tower_borescope.imaging.stabilize import Stabilizer
from tower_borescope.imaging.view_modes import apply_view_mode, glare_reduce


class FrameProcessor:
    """Applies the settings in a :class:`PipelineState` to camera frames.

    The static chain (grade, enhance, glare, view mode, orientation) keeps no state
    between frames, so pre-roll frames go through it on another thread. The live
    filters (stabilizer and temporal denoise) depend on the previous frames and run
    only on the frame loop.

    Attributes:
        state: Settings read on every call.
    """

    def __init__(self, state: PipelineState) -> None:
        self.state = state
        self._stabilizer = Stabilizer()
        self._denoiser = TemporalDenoise()
        self._focus = FocusMeter()

    def process_static(self, raw: BgrImage) -> BgrImage:
        """Grade, enhance, reduce glare, apply the view mode and orient one frame.

        Args:
            raw: Decoded camera frame, or the output of the live filters.

        Returns:
            The processed frame.
        """
        state = self.state
        image = state.grade.apply(raw)
        if state.enhanced:
            image = enhance(image)
        if state.glare > 0:
            image = glare_reduce(image, state.glare)
        if state.view_mode != NORMAL_VIEW:
            image = apply_view_mode(image, state.view_mode)
        return orient(image, state.rotation, state.mirror)

    def process_live(self, raw: BgrImage) -> BgrImage:
        """Stabilize and denoise when enabled, then run the static chain.

        Args:
            raw: Decoded camera frame, the next in the stream.

        Returns:
            The processed frame.
        """
        image = raw
        if self.state.stabilize:
            image = self._stabilizer.apply(image)
        if self.state.denoise > 0:
            self._denoiser.strength = self.state.denoise
            image = self._denoiser.apply(image)
        return self.process_static(image)

    def finish_stack(self, stacked: BgrImage) -> BgrImage:
        """Grade, sharpen, reduce glare and orient a stacked still.

        The view mode is left out so that stills keep their natural look.

        Args:
            stacked: Output of ``imaging.stacking.stack_frames``.

        Returns:
            The finished still.
        """
        state = self.state
        still = finish_still(state.grade.apply(stacked), state.enhanced)
        if state.glare > 0:
            still = glare_reduce(still, state.glare)
        return orient(still, state.rotation, state.mirror)

    def frame_info(self, raw: BgrImage, image: BgrImage, motion: float) -> FrameInfo:
        """Build the display image and meter readings for the view.

        Args:
            raw: Decoded camera frame, for the focus score.
            image: Processed frame.
            motion: Motion level measured on the raw frame.

        Returns:
            The frame info; focus, histogram and clipping are filled in with meters on.
        """
        display = zebra(image) if self.state.zebra else image
        score = focus_score(raw)
        info = FrameInfo(to_qimage(display), focus_raw=score, motion=motion)
        if self.state.meters:
            info.focus = self._focus.update(score)
            info.hist = histogram(image)
            info.clipped = clipped_fraction(image)
        return info

    def reset_stabilizer(self) -> None:
        """Forget the stabilizer's camera path."""
        self._stabilizer.reset()

    def reset_denoiser(self) -> None:
        """Drop the running denoise average."""
        self._denoiser.reset()

    def reset_filters(self) -> None:
        """Reset both live filters, for example after a resolution change."""
        self.reset_stabilizer()
        self.reset_denoiser()
