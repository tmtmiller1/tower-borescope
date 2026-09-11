#!/bin/zsh
# Builds "Tower Borescope.app" and its disk image, then installs the application.
#   scripts/build_app.sh               build, make the disk image, install into ~/Applications
#   scripts/build_app.sh --no-install  build and make the disk image only
#
# The bundle carries everything the application needs: Python, Qt, OpenCV, an LGPL ffmpeg
# and libusb. ffmpeg and libusb are built here from pinned release sources for the minimum
# macOS version; the ffmpeg build enables only the devices, formats, codecs, filters and
# protocols the application uses and links nothing but macOS system libraries. Qt modules
# and Python packages the application never loads are left out, and the license texts of
# every bundled component are collected into Contents/Resources/licenses. The bundle is
# signed with an ad-hoc signature; README.md describes the first launch on a machine that
# downloads it. The disk image is named after the version and the processor architecture
# and carries LICENSE and THIRD_PARTY_NOTICES.md next to the application. The source
# tarballs stay in build/, where the release workflow picks them up.
set -euo pipefail

ROOT="${0:A:h:h}"
APP_NAME="Tower Borescope"
BUNDLE_ID="com.tylermiller.towerborescope"
MIN_MACOS="13.0"
BUILD="$ROOT/build"
DIST="$ROOT/dist"
PY="$ROOT/.venv/bin/python"
ARCH="$(uname -m)"
MAKE_JOBS=4
LIBUSB_VERSION="1.0.30"
LIBUSB_SHA256="fea36f34f9156400209595e300840767ab1a385ede1dc7ee893015aea9c6dbaf"
LIBUSB_URL="https://github.com/libusb/libusb/releases/download"
LIBUSB_URL="$LIBUSB_URL/v$LIBUSB_VERSION/libusb-$LIBUSB_VERSION.tar.bz2"
LIBUSB_TARBALL="$BUILD/libusb-$LIBUSB_VERSION.tar.bz2"
LIBUSB_FILE="libusb-1.0.0.dylib"
FFMPEG_VERSION="9.0.1"
FFMPEG_SHA256="cf38e0e28c7e5605942c4a77755349b0145804a397af37eb1fb4c77cb237f635"
FFMPEG_URL="https://ffmpeg.org/releases/ffmpeg-$FFMPEG_VERSION.tar.xz"
FFMPEG_TARBALL="$BUILD/ffmpeg-$FFMPEG_VERSION.tar.xz"
FFMPEG_OUT="$BUILD/ffmpeg-$FFMPEG_VERSION-$ARCH"
FFMPEG="$FFMPEG_OUT/ffmpeg"
# SHA-256 of LICENSES/LGPL-3.0-only.txt and LICENSES/GPL-3.0-only.txt in pyside-setup
# 6.11.2. COPYING.LGPLv3 and COPYING.GPLv3 in the ffmpeg sources are the same files, so
# they also ship as the license texts of Qt, PySide6 and shiboken6.
LGPL3_SHA256="da7eabb7bafdf7d3ae5e9f223aa5bdc1eece45ac569dc21b3b037520b4464768"
GPL3_SHA256="8ceb4b9ee5adedde47b31e975c1d90c73ad27b6b165a1dcd80c7c545eb65b903"
TEST_SHOT_SECONDS=120
MIC_TEXT="Recordings include sound from the microphone chosen in the Capture tab."
COPYRIGHT="Copyright 2026 Tyler Miller. MIT License."

# ffmpeg configuration: LGPL-2.1-or-later (no --enable-gpl, --enable-version3 or
# --enable-nonfree) and no external libraries. Recording pipes MJPEG or BGR frames in,
# stream-copies MJPEG or encodes H.264 with VideoToolbox, and adds AVFoundation audio
# encoded by AudioToolbox; time-lapse assembly reads numbered PNG files. ffmpeg 9 reads
# the "-" input through the fd protocol. The Intel build skips the standalone x86
# assembly, which needs nasm.
FFMPEG_CONFIGURE=(
  --disable-everything --disable-autodetect --disable-programs --enable-ffmpeg
  --disable-doc --disable-network --disable-debug
  --enable-avfoundation --enable-audiotoolbox --enable-videotoolbox --enable-zlib
  --enable-indev=avfoundation
  --enable-demuxer=mjpeg,rawvideo,image2
  --enable-decoder=mjpeg,png,rawvideo
  --enable-decoder=pcm_f32be,pcm_f32le,pcm_s16be,pcm_s16le
  --enable-decoder=pcm_s24be,pcm_s24le,pcm_s32be,pcm_s32le
  --enable-encoder=h264_videotoolbox,aac_at
  --enable-muxer=mov,mp4,matroska,avi
  --enable-parser=mjpeg,png
  --enable-filter=scale,format,aformat,aresample,null,anull
  --enable-protocol=file,pipe,fd
  "--extra-cflags=-mmacosx-version-min=$MIN_MACOS -arch $ARCH"
  "--extra-ldflags=-mmacosx-version-min=$MIN_MACOS -arch $ARCH"
)
if [[ "$ARCH" == x86_64 ]]; then
  FFMPEG_CONFIGURE+=(--disable-x86asm)
fi
FFMPEG_QUOTED=("${(q-)FFMPEG_CONFIGURE[@]}")
FFMPEG_LINE="MACOSX_DEPLOYMENT_TARGET=$MIN_MACOS ./configure ${FFMPEG_QUOTED[*]}"

# Modules PyInstaller finds through optional imports that the application never runs:
# pydantic's mypy plugin (mypy, mypy_extensions, ast_serialize, librt), numpy's
# configuration printer (yaml), the deprecated httpx2 command line (click, rich, pygments,
# markdown_it), pydantic's schema printer (rich), anyio's pytest runner (pytest) and
# setuptools with packaging, which only setuptools and pytest import. The Qt Quick, QML
# and OpenGL bindings are unused too. pyvirtualcam is GPL-2.0 and stays out of the
# downloadable application.
EXCLUDED_MODULES=(
  mypy mypy_extensions ast_serialize librt yaml click rich pygments markdown_it
  linkify_it mdurl pytest _pytest pluggy iniconfig
  setuptools pkg_resources distutils _distutils_hack packaging pyvirtualcam
  PySide6.QtQml PySide6.QtQuick PySide6.QtQuickWidgets PySide6.QtQuickControls2
  PySide6.QtOpenGL PySide6.QtOpenGLWidgets
)
# Qt Virtual Keyboard, GPL-3.0 in open-source Qt, arrives through the
# platforminputcontexts plugin together with the Qt Quick, QML and OpenGL libraries it
# loads. The application uses none of them, so they leave the bundle before signing.
PRUNED_QT=(
  QtVirtualKeyboard QtVirtualKeyboardQml QtQuick QtQml QtQmlMeta QtQmlModels
  QtQmlWorkerScript QtOpenGL
)
LEFTOVERS="QtVirtualKeyboard|QtQuick|QtQml|QtOpenGL|mypy|setuptools|yaml|click"
LEFTOVERS="$LEFTOVERS|ast_serialize|librt|pyvirtualcam|_native_macos_obs|imageio"
LEFTOVERS="$LEFTOVERS|/(_?pytest|rich|pygments|markdown_it)([-/.]|\$)"

[[ -x "$PY" ]] || { echo "Environment missing. Run scripts/setup.sh first." >&2; exit 1; }
VERSION="$("$PY" -c 'from importlib.metadata import version; print(version("tower-borescope"))')"
APP="$DIST/$APP_NAME.app"
PLIST="$APP/Contents/Info.plist"
LICENSES="$APP/Contents/Resources/licenses"
mkdir -p "$BUILD" "$DIST"
echo "Building $APP_NAME $VERSION for $ARCH (macOS $MIN_MACOS or later)"

fail() {  # message
  echo "$1" >&2
  exit 1
}

fetch_verified() {  # url, file, sha256
  [[ -f "$2" ]] || curl -fsSL -o "$2" "$1"
  echo "$3  $2" | shasum -a 256 -c - >/dev/null \
    || fail "Checksum mismatch for $2; delete it and rerun"
}

# libusb: built from the release sources so the library runs on the minimum macOS
# version. Homebrew bottles are built for the machine's own macOS release.
build_libusb() {
  local source="$BUILD/libusb-$LIBUSB_VERSION"
  rm -rf "$source"
  tar -xjf "$LIBUSB_TARBALL" -C "$BUILD"
  (
    cd "$source"
    CFLAGS="-mmacosx-version-min=$MIN_MACOS -arch $ARCH" \
      ./configure --disable-static --disable-dependency-tracking >/dev/null
    make -j "$MAKE_JOBS" >/dev/null
  )
  cp "$source/libusb/.libs/$LIBUSB_FILE" "$BUILD/$LIBUSB_FILE"
}
fetch_verified "$LIBUSB_URL" "$LIBUSB_TARBALL" "$LIBUSB_SHA256"
[[ -f "$BUILD/$LIBUSB_FILE" ]] || build_libusb
lipo -archs "$BUILD/$LIBUSB_FILE" | grep -qw "$ARCH" \
  || fail "The libusb in build/ is not built for $ARCH; delete it and rerun"

# ffmpeg: built from the release sources with the configuration above. The build is
# reused while build/ffmpeg-<version>-<arch>/configure.txt matches that configuration.
build_ffmpeg() {
  local source="$BUILD/ffmpeg-$FFMPEG_VERSION"
  rm -rf "$source" "$FFMPEG_OUT"
  mkdir -p "$FFMPEG_OUT"
  tar -xJf "$FFMPEG_TARBALL" -C "$BUILD"
  (
    cd "$source"
    export MACOSX_DEPLOYMENT_TARGET="$MIN_MACOS"
    ./configure "${FFMPEG_CONFIGURE[@]}" >"$FFMPEG_OUT/configure.log" \
      || { tail -20 "$FFMPEG_OUT/configure.log" >&2; exit 1; }
    make -j "$MAKE_JOBS" >/dev/null
  )
  cp "$source/ffmpeg" "$FFMPEG"
  print -r -- "$FFMPEG_LINE" >"$FFMPEG_OUT/configure.txt"
}
fetch_verified "$FFMPEG_URL" "$FFMPEG_TARBALL" "$FFMPEG_SHA256"
if [[ ! -x "$FFMPEG" || ! -f "$FFMPEG_OUT/configure.txt" \
  || "$(<"$FFMPEG_OUT/configure.txt")" != "$FFMPEG_LINE" ]]; then
  build_ffmpeg
fi

require_ffmpeg_feature() {  # listing flag, feature names
  local listing name
  listing="$("$FFMPEG" -hide_banner "$1" 2>/dev/null)"
  shift
  for name in "$@"; do
    # Listing rows are a flag column and the name; -protocols rows are the name alone.
    print -r -- "$listing" | grep -qE "^ [A-Zd.| ]{0,8} $name( |\$)" \
      || fail "The bundled ffmpeg lacks $name"
  done
}
check_ffmpeg() {
  require_ffmpeg_feature -devices avfoundation
  require_ffmpeg_feature -demuxers mjpeg rawvideo image2
  require_ffmpeg_feature -decoders mjpeg png rawvideo pcm_f32be pcm_f32le pcm_s16be \
    pcm_s16le pcm_s24be pcm_s24le pcm_s32be pcm_s32le
  require_ffmpeg_feature -encoders h264_videotoolbox aac_at
  require_ffmpeg_feature -muxers mov mp4 matroska avi
  require_ffmpeg_feature -filters scale format aformat aresample null anull
  require_ffmpeg_feature -protocols file pipe fd
  # Recording pipes frames into standard input: a JPEG piped through a stream copy checks
  # the input protocol, the MJPEG demuxer and decoder and the MOV muxer together.
  local smoke="$FFMPEG_OUT/smoke.mov"
  local jpeg="import sys, cv2, numpy; image = numpy.zeros((16, 16, 3), numpy.uint8)"
  jpeg="$jpeg; sys.stdout.buffer.write(cv2.imencode('.jpg', image)[1].tobytes())"
  rm -f "$smoke"
  "$PY" -c "$jpeg" | "$FFMPEG" -hide_banner -loglevel error -y -f mjpeg -i - \
    -c:v copy "$smoke" || fail "The bundled ffmpeg cannot stream-copy piped MJPEG"
  [[ -s "$smoke" ]] || fail "The bundled ffmpeg wrote no file from piped MJPEG"
  if "$FFMPEG" -hide_banner -buildconf | grep -qE -- "--enable-(gpl|version3|nonfree|lib)"
  then
    fail "The bundled ffmpeg is not an LGPL build without external libraries"
  fi
  "$FFMPEG" -hide_banner -L | grep -q "GNU Lesser General Public" \
    || fail "The bundled ffmpeg does not report the LGPL"
  if otool -L "$FFMPEG" | tail -n +2 | grep -vqE "^[[:space:]]+/(usr/lib|System/Library)/"
  then
    fail "The bundled ffmpeg links a library outside macOS"
  fi
  lipo -archs "$FFMPEG" | grep -qw "$ARCH" || fail "The bundled ffmpeg is not for $ARCH"
  [[ "$(otool -l "$FFMPEG" | awk '/minos/ {print $2; exit}')" == "$MIN_MACOS" ]] \
    || fail "The bundled ffmpeg does not target macOS $MIN_MACOS"
}
check_ffmpeg

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

EXCLUDE_ARGS=()
for module in "${EXCLUDED_MODULES[@]}"; do
  EXCLUDE_ARGS+=(--exclude-module "$module")
done
rm -rf "$BUILD/pyinstaller" "$DIST/$APP_NAME" "$APP"
"$PY" -m PyInstaller --noconfirm --log-level WARN --windowed --name "$APP_NAME" \
  --icon "$BUILD/icon.icns" --osx-bundle-identifier "$BUNDLE_ID" \
  --add-data "$ROOT/.env.example:." \
  --add-binary "$FFMPEG:bin" \
  --add-binary "$BUILD/$LIBUSB_FILE:." \
  --collect-submodules tower_borescope \
  --hidden-import qrcode --hidden-import anthropic \
  "${EXCLUDE_ARGS[@]}" \
  --distpath "$DIST" --workpath "$BUILD/pyinstaller" --specpath "$BUILD" \
  "$ROOT/scripts/app_entry.py"

prune_qt() {
  local name
  rm -rf "$APP/Contents/Frameworks/PySide6/Qt/plugins/platforminputcontexts"
  for name in "${PRUNED_QT[@]}"; do
    rm -rf "$APP/Contents/Frameworks/PySide6/Qt/lib/$name.framework" \
      "$APP/Contents/Resources/PySide6/Qt/lib/$name.framework" \
      "$APP/Contents/Frameworks/$name" "$APP/Contents/Resources/$name"
  done
}
prune_qt
leftovers="$(find "$APP/Contents" | grep -E "$LEFTOVERS" || true)"
if [[ -n "$leftovers" ]]; then
  print -r -- "$leftovers" | head -20 >&2
  fail "Excluded components remain in the bundle"
fi

# License texts: this project, the Python distributions PyInstaller bundled, CPython,
# Qt for Python, OpenCV (from its wheel), ffmpeg with its configure line, and libusb.
collect_licenses() {
  local ffmpeg_dir="ffmpeg-$FFMPEG_VERSION"
  rm -rf "$LICENSES"
  mkdir -p "$LICENSES/ffmpeg" "$LICENSES/libusb" "$LICENSES/qt-for-python"
  cp "$ROOT/LICENSE" "$ROOT/THIRD_PARTY_NOTICES.md" "$LICENSES/"
  tar -xJf "$FFMPEG_TARBALL" -C "$LICENSES/ffmpeg" --strip-components 1 \
    "$ffmpeg_dir/COPYING.LGPLv2.1" "$ffmpeg_dir/LICENSE.md" \
    "$ffmpeg_dir/COPYING.LGPLv3" "$ffmpeg_dir/COPYING.GPLv3"
  cp "$FFMPEG_OUT/configure.txt" "$LICENSES/ffmpeg/configure.txt"
  mv "$LICENSES/ffmpeg/COPYING.LGPLv3" "$LICENSES/LGPL-3.0.txt"
  mv "$LICENSES/ffmpeg/COPYING.GPLv3" "$LICENSES/GPL-3.0.txt"
  echo "$LGPL3_SHA256  $LICENSES/LGPL-3.0.txt" | shasum -a 256 -c - >/dev/null \
    || fail "The LGPL-3.0 text differs from the Qt for Python copy"
  echo "$GPL3_SHA256  $LICENSES/GPL-3.0.txt" | shasum -a 256 -c - >/dev/null \
    || fail "The GPL-3.0 text differs from the Qt for Python copy"
  cp "$LICENSES/LGPL-3.0.txt" "$LICENSES/qt-for-python/LGPL-3.0-only.txt"
  cp "$LICENSES/GPL-3.0.txt" "$LICENSES/qt-for-python/GPL-3.0-only.txt"
  tar -xjf "$LIBUSB_TARBALL" -C "$LICENSES/libusb" --strip-components 1 \
    "libusb-$LIBUSB_VERSION/COPYING"
  # PySide6 and shiboken6 wheels carry no license file; their texts are qt-for-python/.
  "$PY" "$ROOT/scripts/collect_licenses.py" "$BUILD/pyinstaller/$APP_NAME" "$APP" \
    "$LICENSES" --include pyinstaller --covered pyside6 --covered pyside6-essentials \
    --covered pyside6-addons --covered shiboken6
}
collect_licenses

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

descendants() {  # pid; prints it and every descendant process, parents first
  local child
  print -r -- "$1"
  for child in $(pgrep -P "$1" || true); do
    descendants "$child"
  done
}

run_with_limit() {  # seconds, command and arguments; a timed-out run returns 124
  local limit="$1" pid waited=0
  local -a tree
  shift
  "$@" &
  pid=$!
  while kill -0 "$pid" 2>/dev/null; do
    if ((waited >= limit)); then
      echo "Timed out after $limit s: $1; stopping it and its child processes" >&2
      tree=($(descendants "$pid"))
      kill -TERM "${tree[@]}" 2>/dev/null || true
      sleep 2
      tree+=($(descendants "$pid"))
      kill -KILL "${tree[@]}" 2>/dev/null || true
      wait "$pid" 2>/dev/null || true
      return 124
    fi
    sleep 1
    waited=$((waited + 1))
  done
  wait "$pid"
}

# The built application must open a window and save a picture of it within the time
# limit; a hung application is stopped with its child processes and fails the build.
SHOT="$BUILD/test_shot.png"
rm -f "$SHOT"
run_with_limit "$TEST_SHOT_SECONDS" "$APP/Contents/MacOS/$APP_NAME" --test-shot "$SHOT" \
  || fail "The built application did not complete --test-shot"
[[ -s "$SHOT" ]] || fail "The built application did not render a window"
echo "Built $APP"

STAGE="$BUILD/dmg"
rm -rf "$STAGE" && mkdir -p "$STAGE"
cp -R "$APP" "$STAGE/"
cp "$ROOT/LICENSE" "$ROOT/THIRD_PARTY_NOTICES.md" "$STAGE/"
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
