# window

Main window of the application, with the sidebar panels, the menus and the controllers that hold the window logic.

## Files

- `__init__.py`: package docstring describing how panels, controllers and the window fit together.
- `main_window.py`: `MainWindow`, which composes the panels and controllers, connects pipeline and view signals, handles Esc and persists the window geometry.
- `context.py`: shared window state handed to controllers, and the settings dictionary saved on every change.
- `menus.py`: File, Camera, Image, Tools, View, AI and Help menus with their keyboard shortcuts, and the shortcut summary.
- `camera_panel.py`: CAMERA group with the resolution choice and the statistics line.
- `camera_controller.py`: resolution changes and the stream statistics in the sidebar and status bar.
- `capture_panel.py`: Capture tab with stills, recording options, automation and folder buttons.
- `capture_controller.py`: snapshots, recording, time-lapse, scope button gestures, progress and recording state, and the recent captures strip.
- `ai_panel.py`: AI tab with the context field, Analyze, the answer panel, follow-up questions, report and settings buttons.
- `ai_controller.py`: AI worker thread, lazy backend construction, analysis and streamed follow-up questions.
- `ai_transcript.py`: rich text for the analysis panel, suggested questions, follow-ups and the AI status line.
- `report_controller.py`: collection of analyzed views and HTML and PDF inspection reports.
- `image_panel.py`: Image tab with color sliders, detail filters, view mode and reset.
- `image_controller.py`: image settings applied to the pipeline, meters and zebra stripes.
- `tools_panel.py`: Tools tab groups for freeze and compare, measurement and annotation, and meters.
- `freeze_controller.py`: freezing the view and every way back to the live camera.
- `compare_controller.py`: reference images for split and overlay comparison.
- `measure_controller.py`: measurement tools, units, calibration, the focus-locked scale status and the AI scale estimate.
- `view_panel.py`: View tab groups for orientation and zoom, and for sharing.
- `view_controller.py`: rotation, mirror, grid, the sidebar and full screen.
- `share_controller.py`: phone monitor with its QR code, and the virtual camera.
- `recent_panel.py`: thumbnails of the latest captures below the tabs.
