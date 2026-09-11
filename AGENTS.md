# tower_borescope agent guide

Operating notes for agentic tools working in this repository. The code follows the Tower coding
standards (`tower-agent/.github/instructions/coding_standards.instructions.md`); the limits that
tooling enforces are restated here so the repository stays self-contained.

## Layout

- `src/tower_borescope/`: the package. Subpackages `device`, `imaging`, `measure`, `capture`,
  `remote`, `ai` and `app`; shared modules `config`, `errors`, `image_types`, `jpeg` and `cli`.
- `tests/`: pytest suite. `conftest.py` sandboxes every data location; `synthetic.py` generates
  frames and USB packets; `fakes.py` holds the camera reader and AI backend doubles.
- `scripts/`: environment setup, application bundle build, license collection and the limits
  checker.
- `docs/`: protocol reference, user guide and plans.

## Commands

```
scripts/setup.sh
uv run ruff check src tests
uv run ruff format src tests
uv run mypy
uv run radon cc src tests -n C -s
uv run python scripts/check_limits.py
uv run pytest
uv run pytest --camera
uv run pytest --camera --live-ai
uv run mutmut run --max-children 2
uv run python scripts/mutation_score.py --gate
scripts/build_opencv.sh
scripts/build_app.sh
build/venv/bin/pytest tests/test_imaging_*.py tests/test_measure_*.py tests/test_jpeg.py \
  tests/test_app_dialogs_gallery.py -m "not timing"
```

`scripts/check_limits.py` measures the size and complexity limits in the table below and
exits 1 on any finding; CI runs it after radon.
`--camera` tests need the borescope attached and no running Tower Borescope process.
`--live-ai` tests need a local Ollama server with a vision model. `scripts/build_app.sh`
creates its own environment in `build/venv` from `uv.lock` (build and dev groups, no
extras) and never touches `.venv`. It runs `scripts/build_opencv.sh`, which compiles the
opencv-python sdist without FFmpeg or any video I/O into a wheel cached in
`build/opencv-<version>-<arch>-<hash>/`, because every PyPI opencv-python wheel for macOS
links GPL FFmpeg libraries; development and CI keep the PyPI wheel. It compiles libusb and
an LGPL ffmpeg from pinned release sources into `build/` with at most four make jobs,
leaves unused Qt modules and Python packages out of the bundle, collects the license texts
through `scripts/collect_licenses.py` and produces the signed bundle and the disk image in
`dist/`; `.github/workflows/release.yml` runs both scripts for both architectures, runs the
imaging, measurement, JPEG and gallery tests with `build/venv/bin/pytest` against the
OpenCV build and attaches the ffmpeg and libusb source tarballs to each release. OpenCV
compiles take several minutes and memory; run one at a time, never beside another build
or a large pytest run. Gallery thumbnails come from ffmpeg
(`tower_borescope.capture.ffmpeg.first_frame`), not from OpenCV's videoio module, which the
bundled OpenCV does not contain; new code must not use `cv2.VideoCapture` or
`cv2.VideoWriter`. The downloadable application leaves out the
`virtual-camera` extra (pyvirtualcam, GPL-2.0) and its View tab shows the virtual camera
disabled; `scripts/setup.sh` installs the extra for development, and
`uv sync --all-groups --extra virtual-camera` restores it after a plain `uv sync`.
Tests marked `timing` assert wall-clock speed: frame rates and per-frame time budgets. CI,
release and mutation runs leave them out, so `uv run pytest -m timing` runs them on a
development machine.
`uv run mutmut run --max-children 2` mutates the whole package and keeps its results in
`mutants/`; a later run retests only changed code. Each mutmut worker holds about 1.8 GB,
and without `--max-children` mutmut starts one per core, which runs a 16 GB Mac out of
memory. `scripts/mutation_score.py --gate` then fails when a
subpackage scores more than one point below its floor in `docs/mutation_baseline.json` or
when mutants remain unchecked.

## Enforced limits

| Area | Limit |
|---|---|
| Lint and format | ruff rules E, F, I, W, B, UP, PGH, C901; 90-character lines |
| Types | `mypy --strict` clean for `src/` |
| Complexity | cyclomatic complexity 10 per function |
| Size | functions 50 lines, classes 200 lines, modules 400 lines |
| Classes | 20 methods, 15 public methods, weighted method complexity 30 |
| Signatures | 5 parameters, nesting depth 4, no mutable defaults |
| Documentation | Google-style docstrings on modules and public symbols; a `README.md` in every directory |
| Exceptions | specific exception types; `except Exception` only when re-raising |
| Configuration | endpoints, native tool paths and keys come from environment variables or `.env` |
| Prose | no em or en dashes, emoji, second person, words from the standards' forbidden lists, or conversational filler |
| Media | no photographs or camera captures committed; tests generate media at run time |

## Conventions

- Qt virtual methods are bound by class attribute (`paintEvent = _paint_event`) so every function
  definition is snake_case.
- Tests are named `test_<package>_<module>.py`; hardware tests carry `@pytest.mark.camera` and live
  model tests `@pytest.mark.live_ai`.
- Capture files keep the `scope_` filename prefix and the existing `~/Pictures/Scope`,
  `~/Movies/Scope` and `~/Documents/Scope Reports` folders.
- Commit messages use an imperative subject of 72 characters or fewer.
