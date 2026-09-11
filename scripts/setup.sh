#!/bin/zsh
# One-time environment setup: Homebrew libraries, the uv environment and a local .env file.
# The .env file records the Homebrew locations of libusb and ffmpeg so that no machine path
# is written into the source code. The environment includes the virtual-camera extra
# (pyvirtualcam), which the downloadable application leaves out.
set -euo pipefail

ROOT="${0:A:h:h}"

command -v brew >/dev/null || { echo "Homebrew is required: https://brew.sh" >&2; exit 1; }
command -v uv >/dev/null || brew install uv
for package in libusb ffmpeg; do
  brew list --versions "$package" >/dev/null || brew install "$package"
done

cd "$ROOT"
uv sync --all-groups --extra virtual-camera

if [[ ! -f .env ]]; then
  prefix="$(brew --prefix)"
  sed \
    -e "s|^TOWER_BORESCOPE_LIBUSB_PATH=.*|TOWER_BORESCOPE_LIBUSB_PATH=${prefix}/lib/libusb-1.0.dylib|" \
    -e "s|^TOWER_BORESCOPE_FFMPEG_PATH=.*|TOWER_BORESCOPE_FFMPEG_PATH=${prefix}/bin/ffmpeg|" \
    .env.example > .env
  echo "Wrote .env with the Homebrew libusb and ffmpeg locations"
fi

echo "Environment ready. Start the application with: uv run tower-borescope"
