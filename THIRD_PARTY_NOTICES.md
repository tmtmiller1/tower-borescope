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
- `python/`: the license files of every bundled Python distribution, among them
  `opencv-python-5.0.0.93/LICENSE.txt` and `LICENSE-3RD-PARTY.txt`; the CPython license in
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
| OpenCV (opencv-python) | 5.0.0.93 | Apache-2.0; the libraries in its wheel under their own licenses (see below) | https://github.com/opencv/opencv-python |
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
`--disable-autodetect` and enables only the AVFoundation input device; the MJPEG, rawvideo and
image2 demuxers; the MJPEG, PNG, rawvideo and PCM decoders; the VideoToolbox H.264 and
AudioToolbox AAC encoders, which are part of macOS; the MOV, MP4, Matroska and AVI muxers;
the scale, format, aformat, aresample, null and anull filters; the file, pipe and fd protocols;
and zlib from macOS. The program links only libraries and frameworks from `/usr/lib` and
`/System/Library`. `licenses/ffmpeg/configure.txt` records the exact configure line.

## Corresponding source for the LGPL components

- FFmpeg 9.0.1 and libusb 1.0.30: the GitHub release of each Tower Borescope version attaches
  the exact source tarballs the build compiled, `ffmpeg-9.0.1.tar.xz` and
  `libusb-1.0.30.tar.bz2`, next to the disk images. `scripts/build_app.sh` in the tagged
  source records the build commands.
- Qt 6.11.2:
  https://download.qt.io/official_releases/qt/6.11/6.11.2/single/qt-everywhere-src-6.11.2.tar.xz
- PySide6 and shiboken6 6.11.2:
  https://download.qt.io/official_releases/QtForPython/pyside6/PySide6-6.11.2-src/pyside-setup-everywhere-src-6.11.2.tar.xz
- The LGPL libraries inside the opencv-python wheel: the upstream sources listed in the next
  section.

Qt, PySide6, shiboken6 and libusb are dynamically linked, and a user may replace them with
compatible versions as the LGPL permits. The Qt libraries are in
`Tower Borescope.app/Contents/Frameworks/PySide6/Qt/lib`, the bindings in
`Contents/Frameworks/PySide6` and `Contents/Frameworks/shiboken6`, and libusb is
`Contents/Frameworks/libusb-1.0.0.dylib`. FFmpeg runs as a separate program; the
`TOWER_BORESCOPE_FFMPEG_PATH` and `TOWER_BORESCOPE_LIBUSB_PATH` environment variables select
another ffmpeg program or libusb library without changing the bundle. A changed bundle needs a
new ad-hoc signature: `codesign --force --deep --sign - "Tower Borescope.app"`.

## Libraries inside the opencv-python wheel

The opencv-python 5.0.0.93 wheel for macOS carries prebuilt libraries in `cv2/.dylibs`, which
the bundle keeps in `Contents/Frameworks`. The wheel's own `LICENSE-3RD-PARTY.txt` ships in
`licenses/python/opencv-python-5.0.0.93/`. Versions below come from the libraries themselves;
where no package version is embedded, the library file name is given.

GPL libraries. The FFmpeg libraries in the wheel were built from FFmpeg 7.1.1 with
`--enable-gpl --enable-version3` and link x264, x265, Rubber Band and vid.stab, so these
libraries are covered by GPL-3.0-or-later. `cv2.abi3.so` links libavcodec, libavformat,
libavutil, libavdevice and libswscale directly.

| Library | Version | License | Source |
|---|---|---|---|
| libavcodec, libavformat, libavutil, libavfilter, libavdevice, libswscale, libswresample, libpostproc | FFmpeg 7.1.1 | GPL-3.0-or-later as configured | https://ffmpeg.org/releases/ffmpeg-7.1.1.tar.xz |
| libx264 | libx264.164 | GPL-2.0-or-later | https://code.videolan.org/videolan/x264 |
| libx265 | 4.1 | GPL-2.0-or-later | https://bitbucket.org/multicoreware/x265_git |
| librubberband | librubberband.3 | GPL-2.0-or-later | https://breakfastquay.com/rubberband/ |
| libvidstab | libvidstab.1.2 | GPL-2.0-or-later | https://github.com/georgmartius/vid.stab |

LGPL libraries.

| Library | Version | License | Source |
|---|---|---|---|
| GnuTLS | 3.8.9 | LGPL-2.1-or-later | https://www.gnupg.org/ftp/gcrypt/gnutls/v3.8/gnutls-3.8.9.tar.xz |
| libtasn1 | 4.20.0 | LGPL-2.1-or-later | https://ftp.gnu.org/gnu/libtasn1/libtasn1-4.20.0.tar.gz |
| Nettle (libnettle, libhogweed) | libnettle.8.10, libhogweed.6.10 | LGPL-3.0-or-later OR GPL-2.0-or-later | https://ftp.gnu.org/gnu/nettle/ |
| GMP | 6.3.0 | LGPL-3.0-or-later OR GPL-2.0-or-later | https://gmplib.org/download/gmp/gmp-6.3.0.tar.xz |
| libidn2 | 2.3.8 | LGPL-3.0-or-later OR GPL-2.0-or-later | https://ftp.gnu.org/gnu/libidn/libidn2-2.3.8.tar.gz |
| libunistring | libunistring.5 | LGPL-3.0-or-later OR GPL-2.0-or-later | https://ftp.gnu.org/gnu/libunistring/ |
| libintl (gettext) | 0.25 | LGPL-2.1-or-later | https://ftp.gnu.org/gnu/gettext/gettext-0.25.tar.xz |
| GLib | 2.84.3 | LGPL-2.1-or-later | https://download.gnome.org/sources/glib/2.84/glib-2.84.3.tar.xz |
| FriBidi | 1.0.16 | LGPL-2.1-or-later | https://github.com/fribidi/fribidi/releases/tag/v1.0.16 |
| libbluray | 1.3.4 | LGPL-2.1-or-later | https://download.videolan.org/pub/videolan/libbluray/1.3.4/ |
| libaribb24 | libaribb24.0 | LGPL-3.0-or-later | https://github.com/nkoriyama/aribb24 |
| LAME (libmp3lame) | 3.100 | LGPL-2.0-or-later | https://sourceforge.net/projects/lame/files/lame/3.100/ |
| SoX Resampler (libsoxr) | 0.1.3 | LGPL-2.1-or-later | https://sourceforge.net/projects/soxr/files/ |
| libssh | 0.11.1 | LGPL-2.1-or-later | https://www.libssh.org/files/0.11/libssh-0.11.1.tar.xz |
| Graphite2 | libgraphite2.3.2.1 | LGPL-2.1-or-later OR MPL-2.0 OR GPL-2.0-or-later | https://github.com/silnrsi/graphite |

Other licenses. MPL-2.0: libzmq, SRT 1.5.4. Apache-2.0 OR GPL-2.0-or-later: Mbed TLS
crypto 3.6.3. FTL OR GPL-2.0-or-later: FreeType. BSD-3-Clause OR GPL-2.0-only: Zstandard
1.5.7. Apache-2.0: OpenSSL 3.6.0, Tesseract 5.5.1, opencore-amr. BSD-2-Clause: libaom
3.12.1, dav1d, rav1e 0.8.0, libavif, OpenJPEG 2.5.3, LZ4 1.10.0, libarchive 3.8.1, librist,
libsamplerate 0.2.2, Leptonica. BSD-2-Clause-Patent: libvmaf. BSD-3-Clause-Clear: SVT-AV1
3.0.2. BSD-3-Clause: libvpx, Opus, Ogg, Vorbis, Theora, Speex, libwebp and libsharpyuv,
libjxl 0.11.1, OpenEXR and Imath, Snappy 1.2.2, p11-kit 0.25.5. Apache-2.0 OR BSD-3-Clause:
Highway 1.2.0. MIT: HarfBuzz 11.2.1, Brotli 1.1.0, Little CMS, giflib, libdeflate, cJSON
1.7.18, libX11, libXau, libXdmcp and libxcb. ISC: libass 0.17.4, libsodium. Zlib: SDL2,
libunibreak. 0BSD: liblzma. CC0-1.0: libb2. libpng-2.0: libpng 1.6.49. libtiff: LibTIFF.
IJG AND BSD-3-Clause AND Zlib: libjpeg-turbo. HPND: Fontconfig. BSD-3-Clause WITH
PCRE2-exception: PCRE2 10.45. WTFPL: zimg.

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
distributed with the application.

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
