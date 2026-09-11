# scripts

Scripts that prepare the development environment, build the application bundle and check the code against the size and complexity limits.

## Files

- `setup.sh`: installs Homebrew libusb, ffmpeg and uv when missing, syncs the uv environment, and writes `.env` with the Homebrew library locations.
- `build_app.sh`: draws the icon, builds a libusb for the minimum macOS version, packs it with a static ffmpeg into `Tower Borescope.app` through PyInstaller, signs the bundle, checks that it renders a window, writes the disk image and installs the application into `~/Applications`.
- `app_entry.py`: PyInstaller entry point that enables multiprocessing in the frozen application and starts it.
- `check_limits.py`: standard-library checker for the limits in `AGENTS.md`. `python scripts/check_limits.py [PATH ...]` reads the `.py` files under the given paths (`src`, `tests` and `scripts` by default) and reports, one line each as `path:line: RULE message (value, limit)`, every line over 90 characters (`LINE`), module over 400 lines (`MODULE`), function over 50 lines (`FUNC`), class over 200 lines (`CLASS`), class with more than 20 methods (`METHODS`), 15 public methods (`PUBLIC`) or a weighted method complexity above 30 (`WMC`), function with more than 5 parameters (`PARAMS`), nesting deeper than 4 (`NESTING`) or cyclomatic complexity above 10 (`CC`), missing docstring on a module or on a public class, function or method outside test modules (`DOC`), and module that does not parse (`PARSE`). The metrics match the Tower audit: a definition spans from its `def` or `class` line to its last line, decorators excluded and docstring included; `self` and `cls` do not count as parameters; nested definitions are measured on their own; closures and an `__init__` in a documented class need no docstring. The exit status is 1 when anything is reported, and CI runs the script after radon.
