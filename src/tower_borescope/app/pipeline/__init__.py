"""Per-frame processing thread: filters, meters, stills, recording and outputs.

Modules:
    state: Tunable settings shared with the window, and timing constants.
    events: Callbacks through which components report to the thread's signals.
    processor: Static image chain, live filters and meters.
    stills: Snapshots, stacked stills, bursts and their metadata sidecars.
    recording: Recorder lifecycle with the background pre-roll writer.
    automation: Time-lapse, automatic stacked stills and motion snapshots.
    outputs: Phone monitor publishing and the virtual camera.
    thread: The ``Pipeline`` QThread that runs the frame loop.
"""
