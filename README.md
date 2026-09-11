# tower_borescope

Desktop application and USB driver for Geek szitman supercamera inspection borescopes on macOS.

The borescopes (USB ID `2ce3:3828`) are sold for phone apps such as xscope and Useeplus and do
not present themselves to macOS as webcams. `tower_borescope` reads them over libusb and
provides live view, capture, measurement, image processing and AI-assisted inspection in a
Qt application named Tower Borescope.

## Subfolders

- `.github/`: GitHub Actions workflows for checks and releases.
- `docs/`: USB protocol notes, the user guide and implementation plans.
- `scripts/`: environment setup and application bundle build scripts.
- `src/`: the `tower_borescope` package.
- `tests/`: pytest suite, synthetic test media and test doubles.

## Files

- `pyproject.toml`: package metadata, dependencies, and ruff, mypy, pytest and mutmut configuration.
- `uv.lock`: resolved dependency versions used by `uv sync`.
- `.env.example`: template for machine-specific configuration: service endpoints, native tool paths and data locations.
- `.gitignore`: ignored environment, build and personal files.
- `AGENTS.md`: layout, commands and enforced limits for agentic tools.
- `LICENSE`: MIT License.
- `THIRD_PARTY_NOTICES.md`: licenses of the components inside the application bundle.

## Installing the application

Requirements: a Mac running macOS 13 or later (Apple silicon or Intel) and a supercamera
borescope on a USB port. Nothing else needs to be installed; the application carries its own
copies of Python, Qt, OpenCV, ffmpeg and libusb.

1. Download the disk image for the Mac from the
   [releases page](https://github.com/tmtmiller1/tower-borescope/releases):
   `Tower-Borescope-<version>-arm64.dmg` for Apple silicon or
   `Tower-Borescope-<version>-x86_64.dmg` for Intel.
2. Open the disk image and drag Tower Borescope into Applications.
3. Open the application once. macOS blocks it because the application is signed without an
   Apple Developer ID: close the message, open System Settings, choose Privacy & Security,
   scroll to the Security section and click Open Anyway next to Tower Borescope, then confirm.
   On macOS 13 and 14, Control-clicking the application and choosing Open also works. This
   happens once per download. The equivalent command is
   `xattr -d com.apple.quarantine "/Applications/Tower Borescope.app"`.
4. Plug in the borescope. The window shows the live view at 1280 x 720.

Recording with a microphone asks for microphone access on first use. Optional additions:
[Ollama](https://ollama.com) with `ollama pull qwen3-vl:4b-instruct` for local AI inspection,
and OBS for the virtual camera output. `docs/user_guide.md` describes every feature.

## Running from source

Requirements: macOS 13 or later, [Homebrew](https://brew.sh) and Xcode Command Line Tools.

```
git clone https://github.com/tmtmiller1/tower-borescope.git
cd tower-borescope
scripts/setup.sh
uv run tower-borescope
```

`scripts/setup.sh` installs libusb, ffmpeg and uv through Homebrew, creates the environment
and writes `.env` with the library locations. `uv run tower-borescope grab frame.jpg`,
`stack still.png` and `record clip.mp4 --duration 30` capture without opening a window.

## Building the application

`scripts/build_app.sh` builds `Tower Borescope.app` for the architecture of the machine,
signs it, checks that it renders a window, writes the disk image into `dist/` and installs the
application into `~/Applications`. The GitHub release workflow runs the same script on Apple
silicon and Intel runners; pushing a tag such as `v0.1.0` publishes both disk images.

## Standards

The code follows the Tower coding standards. `AGENTS.md` restates the enforced limits and the
verification commands; `docs/plans/standards_conformance.md` records the module contract.
`scripts/check_limits.py` verifies the size and complexity limits without the private Tower
audit tool, and CI runs it on every push.

## License

MIT License; see `LICENSE`. The bundled components and their licenses are listed in
`THIRD_PARTY_NOTICES.md`.
