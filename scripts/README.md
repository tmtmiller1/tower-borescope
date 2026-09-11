# scripts

Shell scripts that prepare the development environment and build the application bundle.

## Files

- `setup.sh`: installs Homebrew libusb, ffmpeg and uv when missing, syncs the uv environment, and writes `.env` with the Homebrew library locations.
- `build_app.sh`: draws the icon, builds a libusb for the minimum macOS version, packs it with a static ffmpeg into `Tower Borescope.app` through PyInstaller, signs the bundle, checks that it renders a window, writes the disk image and installs the application into `~/Applications`.
- `app_entry.py`: PyInstaller entry point that enables multiprocessing in the frozen application and starts it.
