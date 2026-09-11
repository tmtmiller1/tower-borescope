# tower_borescope

Import package for the borescope driver, image processing, capture, AI inspection and the Qt application.

## Subfolders

- `device/`: USB borescope protocol, libusb transfers, the camera and the frame reader process.
- `imaging/`: color grading, enhancement, geometry, stacking, stabilization, denoising, view modes and meters.
- `measure/`: length units, calibration, measurement and annotation shapes, and overlay drawing.
- `capture/`: ffmpeg discovery, video recording and capture file storage.
- `remote/`: phone monitor web server, page and QR code.
- `ai/`: inspection analysis through Ollama, AnythingLLM or Claude, with reports and API key storage.
- `app/`: Qt desktop application.

## Files

- `__init__.py`: package docstring and version.
- `cli.py`: command line that captures stills, stacked stills and recordings, or starts the application.
- `config.py`: environment variables, `.env` loading, data locations and the settings store.
- `errors.py`: shared exception types.
- `image_types.py`: type aliases for image arrays.
- `jpeg.py`: JPEG header parsing, decoding and encoding.
- `py.typed`: marker declaring that the package ships inline type annotations.
