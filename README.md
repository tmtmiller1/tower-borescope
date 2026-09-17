# Tower Borescope

Turn a cheap USB inspection borescope into a real inspection instrument on macOS.

[![CI](https://github.com/tmtmiller1/tower-borescope/actions/workflows/ci.yml/badge.svg)](https://github.com/tmtmiller1/tower-borescope/actions/workflows/ci.yml)
[![Release](https://github.com/tmtmiller1/tower-borescope/actions/workflows/release.yml/badge.svg)](https://github.com/tmtmiller1/tower-borescope/actions/workflows/release.yml)
[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)
![Platform: macOS 13+](https://img.shields.io/badge/Platform-macOS%2013%2B-lightgrey)

Geek szitman supercamera borescopes (USB ID `2ce3:3828`) are sold for phone apps such as xscope
and Useeplus. They do not identify themselves to macOS as webcams, so no Mac application sees
them — including QuickTime, Photo Booth and every video-conferencing tool. Tower Borescope talks
to the hardware directly over libusb and builds a full inspection workstation on top of it: live
view, capture, image processing, on-screen measurement, AI-assisted analysis and PDF reporting.

It ships as a self-contained Mac application. Nothing else needs to be installed — the bundle
carries its own Python, Qt, OpenCV, ffmpeg and libusb.

## Features

### Live view and capture

- Live video at 1280 x 720, with wheel zoom around the pointer, drag to pan and double click to
  reset.
- Focus meter, histogram with clipped-highlight percentage, optional grid with crosshair and
  zebra stripes over blown highlights.
- Snapshots as PNG with a JSON sidecar recording every setting in use, plus an annotated copy
  when measurements or annotations are on screen.
- Stacked stills: 16 frames aligned and averaged at twice the resolution to cut sensor noise.
- Burst of 10 frames, and H.264 MP4 recording of the processed view or the camera's original
  JPEG stream to MOV, with optional microphone audio and a 10-second pre-roll.
- Automation: interval time-lapse assembled into an MP4, an automatic stacked still whenever the
  view holds still, and a snapshot whenever motion appears.
- The button on the scope cable takes a snapshot on a short press and starts or stops recording
  when held.

### Image processing

Auto white balance, brightness, contrast, saturation, enhance (deblocking, local contrast and
sharpening), stabilization, temporal denoise and glare reduction, with the view modes Normal,
Grayscale, Inverted, Edges and Outline.

### Measurement and annotation

- Distance, angle and area measurement in millimetres, centimetres, decimal inches, fractional
  inches, or feet and inches.
- Arrow, circle, text and freehand annotation.
- Scale calibration from a clicked known length. Every calibration records the focus level, and
  the Tools tab warns when the current focus differs — the signal that the working distance
  changed and the scale no longer holds.
- Freeze a frame, and compare it against a reference image split side by side or overlaid with
  adjustable opacity.

### AI-assisted inspection

- Analyze a frozen frame to identify the subject, rate its condition, list issues with boxes
  drawn on the image, and recommend actions, parts and safety steps, with suggested follow-up
  questions that stream their answers into the panel.
- Estimate scale with AI, which finds an object of standard size in view and proposes a
  calibration.
- Collect analyzed views and write an HTML and PDF inspection report.
- Three interchangeable backends: [Ollama](https://ollama.com) on the local machine (the
  default), an AnythingLLM workspace, or Anthropic. API keys entered in the dialog are stored in
  the macOS Keychain, never in a file.

### Output

- Phone monitor: serves the live view, with snapshot and record buttons, to any browser on the
  same network through a QR code. Each session mints a new private access key, so an address
  from an earlier session stops working and others on the network cannot open the stream
  without it.
- Virtual camera output for OBS and video calls, available when running from source.
- Rotation, mirroring and five capture resolutions.

Full controls, the keyboard shortcut table and data locations are in
[`docs/user_guide.md`](docs/user_guide.md).

## Installing

Requirements: a Mac running macOS 13 or later, Apple silicon or Intel, and a supercamera
borescope on a USB port.

1. Download the disk image for the Mac from the
   [releases page](https://github.com/tmtmiller1/tower-borescope/releases):
   `Tower-Borescope-<version>-arm64.dmg` for Apple silicon or
   `Tower-Borescope-<version>-x86_64.dmg` for Intel.
2. Open the disk image and drag Tower Borescope into Applications.
3. Open the application once. macOS blocks it because the application is signed without an Apple
   Developer ID: close the message, open System Settings, choose Privacy & Security, scroll to
   the Security section and click Open Anyway next to Tower Borescope, then confirm. On macOS 13
   and 14, Control-clicking the application and choosing Open also works. This happens once per
   download. The equivalent command is
   `xattr -d com.apple.quarantine "/Applications/Tower Borescope.app"`.
4. Plug in the borescope. The window shows the live view at 1280 x 720.

Recording with a microphone asks for microphone access on first use. For local AI inspection,
install [Ollama](https://ollama.com) and run `ollama pull qwen3-vl:4b-instruct`.

The downloadable application does not include the virtual camera output. It relies on
pyvirtualcam, licensed under GPL-2.0 only, which cannot be distributed in one program with
OpenCV's Apache-2.0 license, so the View tab shows the virtual camera button disabled. Running
from source provides it; it also needs OBS with its virtual camera.

## Running from source

Requirements: macOS 13 or later, Python 3.12, [Homebrew](https://brew.sh) and Xcode Command Line
Tools.

```sh
git clone https://github.com/tmtmiller1/tower-borescope.git
cd tower-borescope
scripts/setup.sh
uv run tower-borescope
```

`scripts/setup.sh` installs libusb, ffmpeg and uv through Homebrew, creates the environment with
the `virtual-camera` extra (pyvirtualcam) and writes `.env` with the library locations. A plain
`uv sync` removes the extra again; `uv sync --extra virtual-camera` keeps the virtual camera.

### Command line

Capture without opening a window:

```sh
uv run tower-borescope grab frame.jpg
uv run tower-borescope stack still.png --enhance
uv run tower-borescope record clip.mp4 --duration 30
```

All three accept `--res`; `record` also takes `--raw` to write the camera's original JPEG stream
to a `.mov`.

## Building the application

`scripts/build_app.sh` builds `Tower Borescope.app` for the architecture of the machine, writes
the disk image into `dist/` and installs the application into `~/Applications`. It needs uv and
Xcode Command Line Tools, plus `brew install nasm` on an Intel Mac.

The build compiles its own dependencies rather than taking wheels, for licensing reasons:

- libusb and ffmpeg are compiled from pinned, checksum-verified release sources into `build/`.
  The ffmpeg build is LGPL and contains only the devices, formats, codecs, filters and protocols
  the application uses, linking only macOS system libraries.
- OpenCV comes from `scripts/build_opencv.sh`, which compiles the opencv-python sdist with only
  the modules the application uses and without FFmpeg or any other video library, because every
  opencv-python wheel on PyPI for macOS links GPL-licensed FFmpeg libraries. The first build
  takes a few minutes on Apple silicon and is cached in `build/` afterwards.

The script builds in its own environment in `build/venv` from `uv.lock` and leaves the
development environment in `.venv` unchanged. PyInstaller then packs the application without
unused Qt modules and Python packages, the license texts of every bundled component are
collected into `Contents/Resources/licenses`, and the bundle is signed and checked for a
rendering window.

Pushing a tag such as `v0.1.0` runs the same script on Apple silicon and Intel runners and
publishes both disk images, together with the ffmpeg and libusb source tarballs the build
compiled, as a GitHub release.

## Repository layout

| Path | Contents |
|---|---|
| `src/tower_borescope/` | The package: `device`, `imaging`, `measure`, `capture`, `remote`, `ai` and `app` |
| `tests/` | pytest suite with synthetic frames, USB packets and test doubles |
| `scripts/` | Environment setup, application bundle build, license collection, limit checks |
| `docs/` | USB protocol reference, user guide and implementation plans |
| `.github/` | GitHub Actions workflows for checks and releases |

## Development

```sh
uv run ruff check src tests
uv run mypy
uv run pytest
uv run python scripts/check_limits.py
```

The code follows the Tower coding standards. [`AGENTS.md`](AGENTS.md) restates the enforced size
and complexity limits and the full verification command list;
[`docs/plans/standards_conformance.md`](docs/plans/standards_conformance.md) records the module
contract. `scripts/check_limits.py` verifies the limits without the private Tower audit tool, and
CI runs it on every push.

`uv run pytest --camera` runs the tests that need a borescope attached, and
`uv run pytest --camera --live-ai` also exercises the configured AI backend.

## License

MIT License; see [`LICENSE`](LICENSE).

[`THIRD_PARTY_NOTICES.md`](THIRD_PARTY_NOTICES.md) lists the bundled components, their licenses
and where the corresponding source of each LGPL component is available. The application carries
the license texts in `Tower Borescope.app/Contents/Resources/licenses`, and the disk image
carries `LICENSE` and `THIRD_PARTY_NOTICES.md` next to the application.
