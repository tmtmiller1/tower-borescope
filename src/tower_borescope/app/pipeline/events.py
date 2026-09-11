"""Callbacks through which pipeline components report to the thread's signals.

Components receive plain callables rather than the thread itself, so each one can be
exercised in a test with recording functions and no Qt event loop.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class PipelineEvents:
    """Report functions shared by the pipeline components.

    Attributes:
        notice: Short status message for a toast.
        captured: Capture kind and file path, once the file is written.
        recording_changed: Recording state and output path.
        timelapse_changed: Time-lapse running state and frames captured so far.
        stack_progress: Frames collected and frames needed for a stacked still.
        vcam_changed: Virtual camera state.
    """

    notice: Callable[[str], None]
    captured: Callable[[str, str], None]
    recording_changed: Callable[[bool, str], None]
    timelapse_changed: Callable[[bool, int], None]
    stack_progress: Callable[[int, int], None]
    vcam_changed: Callable[[bool], None]
