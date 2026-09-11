"""Video widget with zoom, freeze, compare, measurement tools and overlays.

Modules:
    ai_boxes: Issue boxes taken from an AI analysis.
    geometry: Zoom limits, pan clamping and image to widget coordinate mapping.
    overlays: Measurement and annotation model with undo history.
    tools: Mouse handling for the measurement and annotation tools.
    pointer: Mouse and wheel dispatch for pan, zoom, split compare and the FROZEN badge.
    badges: Rounded text badges, toasts and the heads-up display.
    overlay_painter: Drawing of measurements and annotations on the widget.
    painter: Drawing of the frame, compare modes, grid, AI boxes and meters.
    video_view: The ``VideoView`` widget composing the parts above.
"""
