# imaging

Image processing that turns decoded borescope frames into the graded, stabilized and measured pictures the application shows and saves.

## Files

- `__init__.py`: package docstring listing the imaging modules.
- `color.py`: color defaults and the `ColorGrade` white balance, brightness, contrast and saturation controls.
- `enhance.py`: unsharp masking, the enhance filter and final sharpening for stacked stills.
- `geometry.py`: zoom steps, digital zoom, rotation, mirroring and the small grayscale analysis copy.
- `stacking.py`: alignment and averaging of several frames into an upscaled still.
- `stabilize.py`: the `Stabilizer` that removes handheld shake by phase correlation.
- `denoise.py`: the `TemporalDenoise` filter that averages still regions over time.
- `view_modes.py`: glare compression, the outline look and the view mode dispatcher.
- `meters.py`: focus score and meter, histogram, clipped fraction, zebra stripes and the motion detector.
