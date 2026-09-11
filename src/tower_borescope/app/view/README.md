# view

Shows processed frames in a widget with zoom, pan, freeze, compare, measurement and annotation tools, meters, AI boxes and badges.

## Files

- `__init__.py`: package docstring listing the view modules.
- `ai_boxes.py`: `AiBox` and `boxes_from_analysis`, which turns located AI issues into boxes in image fractions.
- `geometry.py`: zoom limits, wheel zoom steps, pan clamping, zoom anchoring at the pointer, the split divider position and `ImageMapper` for image and widget coordinates.
- `overlays.py`: `OverlayModel` holding finished measurements and annotations, the item being drawn and the undo history, with `OverlaySnapshot` copies.
- `tools.py`: `ToolController` for distance, angle, area, calibrate, arrow, circle, text and freehand tools, including area closing and the text dialog.
- `pointer.py`: `PointerHandler` that routes presses, moves, releases, double clicks and wheel turns to panning, zooming, the split divider, the FROZEN badge and the tools.
- `badges.py`: rounded text badges, `Toasts`, and the heads-up display with status text, recording timer, FROZEN badge, zoom badge and tool hints.
- `overlay_painter.py`: drawing of measurements with labels and the focus-doubt marker, and of arrows, circles, text notes and freehand strokes.
- `painter.py`: drawing of the frame, split and overlay compare, thirds grid, AI boxes with corner brackets and numbered labels, the focus bar and the histogram.
- `video_view.py`: `VideoView`, the widget that holds the view state, composes the parts above and binds the Qt paint and input handlers.
