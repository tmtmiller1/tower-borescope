# app

Qt desktop application that shows the borescope video, processes frames and exposes every capture, image, measurement and AI feature.

## Subfolders

- `pipeline/`: per-frame processing thread with filters, meters, stills, recording, automation and outputs.
- `view/`: video widget with zoom, freeze, compare, measurement and annotation tools, and overlays.
- `window/`: main window, sidebar panels, menus and the controllers behind them.
- `dialogs/`: AI settings, QR code and capture gallery dialogs.
- `widgets/`: shared sidebar widgets and layout helpers.

## Files

- `__init__.py`: package docstring listing the subpackages.
- `frame_info.py`: processed frame and meter readings passed from the pipeline to the view.
- `qt_image.py`: conversion from OpenCV images to Qt images.
- `icon.py`: code-drawn application icon.
- `style.py`: application style sheet and palette constants.
- `main.py`: application start-up, environment loading and the test capture option.
