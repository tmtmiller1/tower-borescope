# measure

Calibrated measurement and annotation of borescope images, from unit formatting to drawing the overlay onto saved frames.

## Files

- `__init__.py`: package docstring listing the measure modules.
- `units.py`: length and area units, conversion of typed lengths and display formatting.
- `calibration.py`: millimetres per pixel per camera mode, including the older settings format and the focus lock.
- `shapes.py`: points, measurement and annotation kinds, `Measurement`, `Annotation` and `OverlaySnapshot`.
- `render.py`: overlay colors and `render_overlay`, which draws measurements and annotations onto a copy of a frame.
