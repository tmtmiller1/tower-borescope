# Third-party notices

Tower Borescope is released under the MIT License (see `LICENSE`). The downloadable
application (`Tower Borescope.app` in the disk image) contains the components below, each
under its own license. The application carries the license texts in
`Tower Borescope.app/Contents/Resources/licenses`:

- `LICENSE` and `THIRD_PARTY_NOTICES.md`: this project.
- `LGPL-3.0.txt` and `GPL-3.0.txt`: the full GNU LGPL 3.0 and GNU GPL 3.0 texts. The LGPL 3.0
  incorporates the GPL 3.0.
- `qt-for-python/`: `LGPL-3.0-only.txt` and `GPL-3.0-only.txt` for Qt, PySide6 and shiboken6;
  the build verifies that they match `LICENSES/` in pyside-setup 6.11.2.
- `ffmpeg/`: `COPYING.LGPLv2.1`, `LICENSE.md` and `configure.txt`, the exact configure line of
  the bundled build.
- `libusb/COPYING`.
- `opencv/`: `LICENSE`, the OpenCV license; `3rdparty/`, the license files of every
  third-party library compiled into OpenCV; `cmake-args.txt`, the CMake options of the build;
  and `build-information.txt`, the output of `cv2.getBuildInformation()`.
- `python/`: the license files of every bundled Python distribution, among them
  `opencv-python-5.0.0.93/LICENSE.txt` (the MIT license of the opencv-python packaging) and
  `LICENSE-3RD-PARTY.txt`, which carries the texts of `opencv/`; the CPython license in
  `CPython-<version>/LICENSE.txt`; and `DISTRIBUTIONS.txt`, the list of bundled distributions.

The disk image also carries `LICENSE` and `THIRD_PARTY_NOTICES.md` next to the application.

## Components in the application bundle

| Component | Version | License | Source |
|---|---|---|---|
| CPython interpreter and standard library | 3.12 | PSF-2.0 | https://www.python.org |
| Qt libraries (QtCore, QtGui, QtWidgets, QtNetwork, QtDBus, QtSvg, QtPdf) and plugins | 6.11.2 | LGPL-3.0-only | https://download.qt.io/official_releases/qt/6.11/6.11.2/single/qt-everywhere-src-6.11.2.tar.xz |
| PySide6 (pyside6-essentials, pyside6-addons) and shiboken6 | 6.11.2 | LGPL-3.0-only | https://download.qt.io/official_releases/QtForPython/pyside6/PySide6-6.11.2-src/pyside-setup-everywhere-src-6.11.2.tar.xz |
| FFmpeg (the `ffmpeg` program) | 9.0.1 | LGPL-2.1-or-later | `ffmpeg-9.0.1.tar.xz` attached to each release; https://ffmpeg.org/releases/ffmpeg-9.0.1.tar.xz |
| libusb | 1.0.30 | LGPL-2.1-or-later | `libusb-1.0.30.tar.bz2` attached to each release; https://github.com/libusb/libusb/releases/tag/v1.0.30 |
| OpenCV, built from the opencv-python sdist (see below) | OpenCV 5.0.0, opencv-python 5.0.0.93 | Apache-2.0; opencv-python packaging MIT; compiled-in libraries under their own licenses (see below) | https://pypi.org/project/opencv-python/5.0.0.93/ (`opencv_python-5.0.0.93.tar.gz`) |
| NumPy | 2.5.3 | BSD-3-Clause AND 0BSD AND MIT AND Zlib AND CC0-1.0 | https://github.com/numpy/numpy |
| pydantic | 2.13.5 | MIT | https://github.com/pydantic/pydantic |
| pydantic-core | 2.46.5 | MIT | https://github.com/pydantic/pydantic-core |
| annotated-types | 0.8.0 | MIT | https://github.com/annotated-types/annotated-types |
| typing-inspection | 0.4.4 | MIT | https://github.com/pydantic/typing-inspection |
| typing-extensions | 4.16.0 | PSF-2.0 | https://github.com/python/typing_extensions |
| anthropic | 1.5.0 | MIT | https://github.com/anthropics/anthropic-sdk-python |
| anyio | 4.15.1 | MIT | https://github.com/agronholm/anyio |
| sniffio | 1.3.1 | MIT OR Apache-2.0 | https://github.com/python-trio/sniffio |
| h11 | 0.16.0 | MIT | https://github.com/python-hyper/h11 |
| httpx2 and httpcore2 | 2.12.0 | BSD-3-Clause | https://github.com/pydantic/httpx2 |
| idna | 3.19 | BSD-3-Clause | https://github.com/kjd/idna |
| jiter | 0.16.0 | MIT | https://github.com/pydantic/jiter |
| docstring-parser | 0.18.0 | MIT | https://github.com/rr-/docstring_parser |
| truststore | 0.10.4 | MIT | https://github.com/sethmlarson/truststore |
| python-dotenv | 1.2.3 | BSD-3-Clause | https://github.com/theskumar/python-dotenv |
| pyusb | 1.3.1 | BSD-3-Clause | https://github.com/pyusb/pyusb |
| qrcode | 8.2 | BSD-3-Clause | https://github.com/lincolnloop/python-qrcode |
| PyInstaller bootloader and runtime hooks | 6.22.2 | GPL-2.0-or-later WITH Bootloader-exception; runtime hooks Apache-2.0 | https://github.com/pyinstaller/pyinstaller |
| pyinstaller-hooks-contrib runtime hook for pyusb | 2026.7 | Apache-2.0 | https://github.com/pyinstaller/pyinstaller-hooks-contrib |

## FFmpeg build

The bundled `ffmpeg` (`Tower Borescope.app/Contents/Frameworks/bin/ffmpeg`) is built by
`scripts/build_app.sh` from the FFmpeg 9.0.1 release tarball (SHA-256
`cf38e0e28c7e5605942c4a77755349b0145804a397af37eb1fb4c77cb237f635`) and is licensed under
LGPL-2.1-or-later. The configuration contains no `--enable-gpl`, `--enable-version3`,
`--enable-nonfree` or external codec library. It starts from `--disable-everything` and
`--disable-autodetect` and enables only the AVFoundation input device; the MJPEG, rawvideo,
image2, MOV, Matroska and AVI demuxers; the MJPEG, PNG, rawvideo, H.264 and PCM decoders;
the VideoToolbox H.264 and AudioToolbox AAC encoders, which are part of macOS, and the
rawvideo encoder; the MOV, MP4, Matroska, AVI and rawvideo muxers; the MJPEG, PNG and H.264
parsers; the scale, format, aformat, aresample, null and anull filters; the file, pipe and fd
protocols; and zlib from macOS. The program links only libraries and frameworks from
`/usr/lib` and `/System/Library`. `licenses/ffmpeg/configure.txt` records the exact configure
line.

## OpenCV build

The bundled OpenCV (`cv2` in `Tower Borescope.app/Contents/Frameworks`) is not the
opencv-python wheel from PyPI: those wheels link FFmpeg libraries configured under the GPL.
`scripts/build_opencv.sh` compiles it from the opencv-python 5.0.0.93 sdist
(`opencv_python-5.0.0.93.tar.gz`, SHA-256
`66aac3e5b5faa48d4025816592f3af19e4bfc2c68dec067bae2dbb4ca10aa9e2`), which contains the
OpenCV 5.0.0 source and its bundled third-party sources. OpenCV is licensed under
Apache-2.0; the opencv-python packaging files are MIT. The build contains the core, flann,
geometry, imgproc, imgcodecs and video modules and the Python bindings. It contains no
FFmpeg, GStreamer or AVFoundation video I/O and no other video library: the videoio and
highgui modules are not built, and every video backend and plugin loader is switched off.
The `cv2` extension is statically linked and links only libraries and frameworks from
`/usr/lib` and `/System/Library` (among them Accelerate and OpenCL). The one change to the
sdist is in its build tooling: the typing stub generator
(`opencv/modules/python/src2/typing_stubs_generation/api_refinement.py` and
`generation.py`) skips annotation refinements and type aliases that name functions or
classes of modules that are not built, such as `Feature2D`; the compiled code is unchanged. `licenses/opencv/cmake-args.txt` records the CMake options and
`licenses/opencv/build-information.txt` the resulting configuration.

Libraries compiled into `cv2`, all from the sdist unless noted:

| Library | Version | License | Architectures |
|---|---|---|---|
| zlib | 1.3.2 | Zlib | arm64, x86_64 |
| libjpeg-turbo | 3.1.2 | IJG AND BSD-3-Clause AND Zlib | arm64, x86_64 |
| libpng | 1.6.57 | libpng-2.0 | arm64, x86_64 |
| LibTIFF | 4.7.1 | libtiff | arm64, x86_64 |
| libwebp | 1.6.0 | BSD-3-Clause | arm64, x86_64 |
| OpenJPEG | 2.5.3 | BSD-2-Clause | arm64, x86_64 |
| Intel ITT API (ittnotify) | 3.25.4 | GPL-2.0-only OR BSD-3-Clause, used under BSD-3-Clause | arm64, x86_64 |
| carotene | 0.0.1 | BSD-3-Clause | arm64 |
| KleidiCV, from https://gitlab.arm.com/kleidi/kleidicv/-/archive/26.03/kleidicv-26.03.tar.gz (SHA-256 `1bb4078fd215565f3906c33f76a00e7b843328965230d765afcd0d51141c434f`) | 26.03 | Apache-2.0 | arm64 |

Compared with the PyPI wheel, the build leaves out the OpenEXR and AVIF codecs, whose
libraries OpenCV 5 does not carry in source form, Intel IPP, and the WenQuanYi Micro Hei
font; the application uses none of them.

## Corresponding source for the LGPL components

- FFmpeg 9.0.1 and libusb 1.0.30: the GitHub release of each Tower Borescope version attaches
  the exact source tarballs the build compiled, `ffmpeg-9.0.1.tar.xz` and
  `libusb-1.0.30.tar.bz2`, next to the disk images. `scripts/build_app.sh` in the tagged
  source records the build commands.
- Qt 6.11.2:
  https://download.qt.io/official_releases/qt/6.11/6.11.2/single/qt-everywhere-src-6.11.2.tar.xz
- PySide6 and shiboken6 6.11.2:
  https://download.qt.io/official_releases/QtForPython/pyside6/PySide6-6.11.2-src/pyside-setup-everywhere-src-6.11.2.tar.xz

Qt, PySide6, shiboken6 and libusb are dynamically linked, and a user may replace them with
compatible versions as the LGPL permits. The Qt libraries are in
`Tower Borescope.app/Contents/Frameworks/PySide6/Qt/lib`, the bindings in
`Contents/Frameworks/PySide6` and `Contents/Frameworks/shiboken6`, and libusb is
`Contents/Frameworks/libusb-1.0.0.dylib`. FFmpeg runs as a separate program; the
`TOWER_BORESCOPE_FFMPEG_PATH` and `TOWER_BORESCOPE_LIBUSB_PATH` environment variables select
another ffmpeg program or libusb library without changing the bundle. A changed bundle needs a
new ad-hoc signature: `codesign --force --deep --sign - "Tower Borescope.app"`.

NumPy 2.5.3 carries no separate libraries on macOS; its vendored source files are listed with
their licenses in `licenses/python/numpy-2.5.3/`.

## Not distributed: pyvirtualcam

The optional OBS virtual camera output uses pyvirtualcam 0.15.0 (GPL-2.0,
https://github.com/letmaik/pyvirtualcam). It is not distributed with the application: the
build excludes it, and the View tab of the downloadable application shows the virtual camera
disabled. pyvirtualcam is installed only when the application runs from source with the
`virtual-camera` extra (`uv sync --extra virtual-camera`, which `scripts/setup.sh` runs).

## Development tools

imageio-ffmpeg (the static ffmpeg the CI tests use), mutmut, mypy, pytest, radon, ruff and
PyInstaller apart from its bootloader and runtime hooks are development tools and are not
distributed with the application. The opencv-python wheel from PyPI, which development and
CI use, is not distributed either. CMake, scikit-build, setuptools, wheel, pip, packaging,
the NumPy 2.0.2 headers and, on Intel, NASM only build the bundled OpenCV.

## Acknowledgements

The USB protocol notes in `docs/usb_protocol.md` credit these projects:

- hbens/geek-szitman-supercamera (CC0-1.0): https://github.com/hbens/geek-szitman-supercamera
- echase/ProbeView (MIT): https://github.com/echase/ProbeView
- jerometerry/useeplus (MIT): https://github.com/jerometerry/useeplus
- Tibiaworx/usee-plus-camera (GPL-3.0): https://github.com/Tibiaworx/usee-plus-camera
- JimKnopfIoT/harbour-pipecam (GPL-3.0): https://github.com/JimKnopfIoT/harbour-pipecam

The implementation uses protocol facts documented by these projects (descriptors, the start
and stop sequences, packet layout, resolution requests and heartbeat handling) and contains no
code from them. ProbeView's license notice is reproduced below as a courtesy.

```
MIT License

Copyright (c) 2026 Everitt Chase

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.
```
