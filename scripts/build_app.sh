#!/bin/zsh
# Builds "Tower Borescope.app" and its disk image, then installs the application.
#   scripts/build_app.sh               build, make the disk image, install into ~/Applications
#   scripts/build_app.sh --no-install  build and make the disk image only
#
# The bundle carries everything the application needs: Python, Qt, OpenCV, a static
# ffmpeg from the imageio-ffmpeg wheel (the build dependency group) and a libusb built
# here from the release sources for the minimum macOS version. The bundle is signed with
# an ad-hoc signature; README.md describes the first launch on a machine that downloads
# it. The disk image is named after the version and the processor architecture.
set -euo pipefail

ROOT="${0:A:h:h}"
APP_NAME="Tower Borescope"
BUNDLE_ID="com.tylermiller.towerborescope"
MIN_MACOS="13.0"
BUILD="$ROOT/build"
DIST="$ROOT/dist"
PY="$ROOT/.venv/bin/python"
ARCH="$(uname -m)"
LIBUSB_VERSION="1.0.30"
LIBUSB_SHA256="fea36f34f9156400209595e300840767ab1a385ede1dc7ee893015aea9c6dbaf"
LIBUSB_URL="https://github.com/libusb/libusb/releases/download"
LIBUSB_URL="$LIBUSB_URL/v$LIBUSB_VERSION/libusb-$LIBUSB_VERSION.tar.bz2"
LIBUSB_FILE="libusb-1.0.0.dylib"
MIC_TEXT="Recordings include sound from the microphone chosen in the Capture tab."
COPYRIGHT="Copyright 2026 Tyler Miller. MIT License."

[[ -x "$PY" ]] || { echo "Environment missing. Run scripts/setup.sh first." >&2; exit 1; }
VERSION="$("$PY" -c 'from importlib.metadata import version; print(version("tower-borescope"))')"
APP="$DIST/$APP_NAME.app"
PLIST="$APP/Contents/Info.plist"
mkdir -p "$BUILD" "$DIST"
echo "Building $APP_NAME $VERSION for $ARCH (macOS $MIN_MACOS or later)"

# ffmpeg: the static build shipped in the imageio-ffmpeg wheel.
FFMPEG_SRC="$("$PY" -c 'import imageio_ffmpeg; print(imageio_ffmpeg.get_ffmpeg_exe())')" \
  || { echo "imageio-ffmpeg missing. Run: uv sync --all-groups" >&2; exit 1; }
cp "$FFMPEG_SRC" "$BUILD/ffmpeg"
chmod +x "$BUILD/ffmpeg"
require_ffmpeg_feature() {  # listing flag, feature name
  "$BUILD/ffmpeg" -hide_banner "$1" 2>/dev/null | grep -q " $2 " \
    || { echo "The bundled ffmpeg lacks $2" >&2; exit 1; }
}
require_ffmpeg_feature -devices avfoundation
require_ffmpeg_feature -encoders h264_videotoolbox
require_ffmpeg_feature -encoders aac

# libusb: built from the release sources so the library runs on the minimum macOS
# version. Homebrew bottles are built for the machine's own macOS release.
build_libusb() {
  local tarball="$BUILD/libusb-$LIBUSB_VERSION.tar.bz2"
  local source="$BUILD/libusb-$LIBUSB_VERSION"
  [[ -f "$tarball" ]] || curl -fsSL -o "$tarball" "$LIBUSB_URL"
  echo "$LIBUSB_SHA256  $tarball" | shasum -a 256 -c - >/dev/null
  rm -rf "$source"
  tar -xjf "$tarball" -C "$BUILD"
  (
    cd "$source"
    CFLAGS="-mmacosx-version-min=$MIN_MACOS -arch $ARCH" \
      ./configure --disable-static --disable-dependency-tracking >/dev/null
    make -j "$(sysctl -n hw.ncpu)" >/dev/null
  )
  cp "$source/libusb/.libs/$LIBUSB_FILE" "$BUILD/$LIBUSB_FILE"
}
[[ -f "$BUILD/$LIBUSB_FILE" ]] || build_libusb
lipo -archs "$BUILD/$LIBUSB_FILE" | grep -qw "$ARCH" \
  || { echo "The libusb in build/ is not built for $ARCH; delete it and rerun" >&2; exit 1; }

# The icon is drawn by code, so no image file is stored in the repository.
"$PY" -c "from pathlib import Path; from tower_borescope.app.icon import write_icon_png; \
write_icon_png(Path('$BUILD/icon.png'))"
ICONSET="$BUILD/icon.iconset"
rm -rf "$ICONSET" && mkdir -p "$ICONSET"
for size in 16 32 128 256 512; do
  double=$((size * 2))
  sips -z "$size" "$size" "$BUILD/icon.png" --out "$ICONSET/icon_${size}x${size}.png" >/dev/null
  sips -z "$double" "$double" "$BUILD/icon.png" \
    --out "$ICONSET/icon_${size}x${size}@2x.png" >/dev/null
done
iconutil -c icns "$ICONSET" -o "$BUILD/icon.icns"

rm -rf "$BUILD/pyinstaller" "$DIST/$APP_NAME" "$APP"
"$PY" -m PyInstaller --noconfirm --log-level WARN --windowed --name "$APP_NAME" \
  --icon "$BUILD/icon.icns" --osx-bundle-identifier "$BUNDLE_ID" \
  --add-data "$ROOT/.env.example:." \
  --add-binary "$BUILD/ffmpeg:bin" \
  --add-binary "$BUILD/$LIBUSB_FILE:." \
  --collect-submodules tower_borescope \
  --hidden-import qrcode --hidden-import pyvirtualcam --hidden-import anthropic \
  --distpath "$DIST" --workpath "$BUILD/pyinstaller" --specpath "$BUILD" \
  "$ROOT/scripts/app_entry.py"

# Bundle metadata that PyInstaller does not set, then an ad-hoc signature over the result.
set_plist() {  # key, type, value
  /usr/libexec/PlistBuddy -c "Set :$1 $3" "$PLIST" 2>/dev/null \
    || /usr/libexec/PlistBuddy -c "Add :$1 $2 $3" "$PLIST"
}
set_plist CFBundleShortVersionString string "$VERSION"
set_plist CFBundleVersion string "$VERSION"
set_plist LSMinimumSystemVersion string "$MIN_MACOS"
set_plist LSApplicationCategoryType string public.app-category.utilities
set_plist NSMicrophoneUsageDescription string "$MIC_TEXT"
set_plist NSHumanReadableCopyright string "$COPYRIGHT"
codesign --force --deep --sign - "$APP"
codesign --verify --deep --strict "$APP"

# The built application must open a window and save a picture of it.
SHOT="$BUILD/test_shot.png"
rm -f "$SHOT"
"$APP/Contents/MacOS/$APP_NAME" --test-shot "$SHOT"
[[ -s "$SHOT" ]] || { echo "The built application did not render a window" >&2; exit 1; }
echo "Built $APP"

STAGE="$BUILD/dmg"
rm -rf "$STAGE" && mkdir -p "$STAGE"
cp -R "$APP" "$STAGE/"
ln -s /Applications "$STAGE/Applications"
DMG="$DIST/Tower-Borescope-$VERSION-$ARCH.dmg"
rm -f "$DMG"
hdiutil create -quiet -volname "$APP_NAME" -srcfolder "$STAGE" -ov -format UDZO "$DMG"
echo "Built $DMG"

if [[ "${1:-}" != "--no-install" ]]; then
  mkdir -p "$HOME/Applications"
  rm -rf "$HOME/Applications/$APP_NAME.app"
  cp -R "$APP" "$HOME/Applications/$APP_NAME.app"
  echo "Installed ~/Applications/$APP_NAME.app"
fi
