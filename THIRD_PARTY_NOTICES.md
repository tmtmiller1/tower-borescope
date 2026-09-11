# Third-party notices

Tower Borescope is released under the MIT License (see `LICENSE`). The application bundle
and the source checkout include the components below, each under its own license. The
license texts ship with the components themselves inside the bundle and in the installed
Python packages.

## Components in the application bundle

| Component | Version | License | Source |
|---|---|---|---|
| Python | 3.12 | PSF License | https://www.python.org |
| Qt for Python (PySide6, shiboken6) and the Qt libraries | 6.11.2 | LGPL-3.0 | https://pyside.org |
| NumPy | 2.5.3 | BSD-3-Clause (with 0BSD, MIT, Zlib and CC0-1.0 parts) | https://numpy.org |
| OpenCV (opencv-python) | 5.0.0.93 | Apache-2.0 | https://github.com/opencv/opencv-python |
| pydantic, pydantic-core, annotated-types, typing-inspection | 2.13.5 | MIT | https://github.com/pydantic/pydantic |
| python-dotenv | 1.2.3 | BSD-3-Clause | https://github.com/theskumar/python-dotenv |
| pyusb | 1.3.1 | BSD-3-Clause | https://pyusb.github.io/pyusb |
| pyvirtualcam | 0.15.0 | GPL-2.0 | https://github.com/letmaik/pyvirtualcam |
| qrcode | 8.2 | BSD-3-Clause | https://github.com/lincolnloop/python-qrcode |
| anthropic SDK | 1.5.0 | MIT | https://github.com/anthropics/anthropic-sdk-python |
| anyio, h11, jiter, sniffio, truststore, docstring-parser | various | MIT | see each project |
| httpx2, httpcore2, idna, colorama | various | BSD-3-Clause | see each project |
| typing-extensions | 4.16.0 | PSF-2.0 | https://github.com/python/typing_extensions |
| libusb | 1.0.30 | LGPL-2.1-or-later | https://libusb.info |
| FFmpeg (static build from the imageio-ffmpeg wheel) | 7.1 | GPL-2.0-or-later | https://ffmpeg.org |
| imageio-ffmpeg (wheel that carries the FFmpeg build) | 0.6.0 | BSD-2-Clause | https://github.com/imageio/imageio-ffmpeg |
| PyInstaller bootloader | 6.22.2 | GPL-2.0-or-later with the PyInstaller bootloader exception | https://pyinstaller.org |

## Notes

- The FFmpeg build is configured with `--enable-gpl` and links libx264, libx265 and other
  GPL libraries, so the FFmpeg executable in the bundle is distributed under the GPL. The
  application runs it as a separate process for recording and time-lapse assembly.
- pyvirtualcam, which provides the OBS virtual camera output, is licensed under GPL-2.0.
- Qt and libusb are dynamically linked and may be replaced by a user with compatible
  versions, as the LGPL requires. The Qt libraries live in
  `Tower Borescope.app/Contents/Frameworks/PySide6/Qt/lib`; libusb is
  `Tower Borescope.app/Contents/Frameworks/libusb-1.0.0.dylib`.
- Mutmut, mypy, pytest, radon and ruff are development tools and are not distributed with
  the application.
