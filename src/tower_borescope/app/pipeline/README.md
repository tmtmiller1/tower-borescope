# pipeline

Runs every per-frame task off the GUI thread: decoding, filters, meters, stills, recording with pre-roll, automation and outputs.

## Files

- `__init__.py`: package docstring listing the pipeline modules.
- `state.py`: `PipelineState` with every tunable setting, its construction from saved settings and the capture metadata, plus the pre-roll, burst and automation timing constants.
- `events.py`: `PipelineEvents`, the report callbacks the components use in place of the thread's signals.
- `processor.py`: `FrameProcessor` with the static chain (grade, enhance, glare, view mode, orientation), the live stabilizer and denoise filters, stacked still finishing and the meter readings.
- `stills.py`: `StillCapture` for snapshots, stacked stills and bursts, with JSON sidecars and annotated copies drawn by `measure.render`.
- `recording.py`: `RecordingControl` for the recorder lifecycle, the ten-second pre-roll written on a background thread with pending-frame hand-off, and dropped-frame padding.
- `automation.py`: `Automation` and `TimeLapse` for time-lapse frames and their ffmpeg assembly, stacked stills after holding still and motion snapshots with a cooldown.
- `outputs.py`: `FrameOutputs` for phone monitor publishing and the pyvirtualcam virtual camera, which reports a missing OBS installation instead of failing, and `vcam_available`, which reports whether the optional pyvirtualcam package is installed.
- `thread.py`: `Pipeline`, the QThread that owns the frame source, runs the loop and exposes the signals and request methods the window uses.
