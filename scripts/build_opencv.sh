#!/bin/zsh
# Builds the OpenCV wheel that the downloadable application bundles.
#   scripts/build_opencv.sh        build unless build/ holds a wheel for these options;
#                                  the last line printed is the path of the wheel
#   scripts/build_opencv.sh --key  print the cache key, the folder name below build/
#
# Every opencv-python wheel on PyPI for macOS links a GPL-configured FFmpeg through the
# videoio module. The application therefore bundles this build: the opencv-python sdist,
# pinned by SHA-256, compiled with only the OpenCV modules the application calls, without
# video I/O, plugins or libraries from outside the OpenCV sources apart from macOS
# frameworks and, on arm64, Arm KleidiCV. Development and CI keep the PyPI wheel.
#
# build/<key>/ (key: opencv-<version>-<arch>-<hash of the options>) holds the wheel,
# cmake-args.txt, build-information.txt (cv2.getBuildInformation()), build.log,
# build-seconds.txt and licenses/: the OpenCV license and the license files of every
# third-party library compiled into cv2. The wheel's LICENSE-3RD-PARTY.txt carries the
# same texts, because the sdist copy describes the libraries of the PyPI wheels.
set -euo pipefail
unset VIRTUAL_ENV

ROOT="${0:A:h:h}"
BUILD="$ROOT/build"
MIN_MACOS="13.0"
ARCH="$(uname -m)"
MAKE_JOBS=4
PYTHON_VERSION="3.12"
OPENCV_VERSION="5.0.0.93"
OPENCV_SHA256="66aac3e5b5faa48d4025816592f3af19e4bfc2c68dec067bae2dbb4ca10aa9e2"
OPENCV_URL="https://files.pythonhosted.org/packages/79/4c"
OPENCV_URL="$OPENCV_URL/a438d23e09ce2033c09f7b784ad2fbdb0adf529e434101ed28f142226f98"
OPENCV_URL="$OPENCV_URL/opencv_python-$OPENCV_VERSION.tar.gz"
OPENCV_TARBALL="$BUILD/opencv_python-$OPENCV_VERSION.tar.gz"
SOURCE="$BUILD/opencv_python-$OPENCV_VERSION"
TOOLS="$BUILD/opencv-tools"
# KleidiCV 26.03 (Apache-2.0), Arm's image processing kernels, which the PyPI arm64 wheel
# also uses. OpenCV downloads it with an MD5 check only; this script fetches it with a
# SHA-256 check and places it in OpenCV's download cache, so CMake downloads nothing.
KLEIDICV_VERSION="26.03"
KLEIDICV_MD5="b85a745bfe0e87e67e30be9533eb6b24"
KLEIDICV_SHA256="1bb4078fd215565f3906c33f76a00e7b843328965230d765afcd0d51141c434f"
KLEIDICV_URL="https://gitlab.arm.com/kleidi/kleidicv/-/archive/$KLEIDICV_VERSION"
KLEIDICV_URL="$KLEIDICV_URL/kleidicv-$KLEIDICV_VERSION.tar.gz"
KLEIDICV_TARBALL="$BUILD/kleidicv-$KLEIDICV_VERSION.tar.gz"
# Build requirements of the sdist, pinned; numpy 2.0.2 is the sdist's own pin for 3.12.
BUILD_TOOLS=(
  cmake==3.31.6 scikit-build==0.18.1 setuptools==69.5.1 numpy==2.0.2 wheel==0.48.0
  packaging==26.3 pip==26.2.1
)
# Modules: core, imgproc, imgcodecs and video declare the functions the application calls
# (findTransformECC and MOTION_TRANSLATION are in video); OpenCV 5 moved approxPolyDP and
# arcLength into geometry, which imgproc requires and which requires flann. python3 is the
# cv2 extension. videoio, highgui, dnn and the other modules stay out.
MODULES="core,flann,geometry,imgproc,imgcodecs,video,python3"
BUILT_MODULES="core flann geometry imgcodecs imgproc python3 video"
THIRD_PARTY=(ittnotify libjpeg-turbo libopenjp2 libpng libtiff libwebp zlib)
if [[ "$ARCH" == arm64 ]]; then
  THIRD_PARTY+=(kleidicv kleidicv_hal kleidicv_thread tegra_hal)
fi

# CMake options, added to those of the sdist's setup.py (static libraries, the limited
# Python API, no tests, documentation, apps or Java):
# - BUILD_LIST: the modules above. The minimum macOS version and the architecture.
# - No video I/O: FFmpeg, GStreamer, AVFoundation, FireWire, Orbbec and the videoio and
#   highgui plugin loaders are off. The GUI toolkits are off as in the headless wheel; the
#   sdist's version.py pins the non-headless flavour, so ENABLE_HEADLESS alone does not.
# - Image codecs from OpenCV's 3rdparty sources: zlib, libjpeg-turbo with SIMD, libpng,
#   libtiff, libwebp and OpenJPEG, and the built-in GIF, HDR, Sun raster, PNM and PFM
#   codecs. OpenCV 5 carries no OpenEXR or libavif source (the PyPI wheel links Homebrew
#   builds of both), so EXR and AVIF are off. JasPer, libspng and JPEG XL are off as in
#   the wheel. CMAKE_IGNORE_PREFIX_PATH keeps CMake from finding Homebrew libraries.
# - Off: Intel IPP (a separate download under the Intel Simplified Software License), the
#   WenQuanYi Micro Hei font download (GPL-3.0 with a font exception or Apache-2.0), and
#   protobuf, flatbuffers, ONNX Runtime, OpenVINO, Eigen, VTK, TBB, OpenMP, GDAL and GDCM,
#   which the built modules do not use.
# - Kept as in the wheel: Apple Accelerate for LAPACK, the OpenCL framework, Grand Central
#   Dispatch and Intel ITT tracing (bundled, GPL-2.0-only OR BSD-3-Clause, used under
#   BSD-3-Clause).
# - carotene (bundled, BSD-3-Clause) and KleidiCV are Arm code: on arm64 both are on as in
#   the wheel. On x86_64 both are off; left on, OpenCV downloads KleidiCV by itself and
#   compiles its NEON sources with Arm-only compiler flags, which stops the build. The
#   options sit last in the list, so the arm64 list and its cache key stay the same.
if [[ "$ARCH" == arm64 ]]; then
  ARM_ACCELERATION=(-DWITH_CAROTENE=ON -DWITH_KLEIDICV=ON)
else
  ARM_ACCELERATION=(-DWITH_CAROTENE=OFF -DWITH_KLEIDICV=OFF)
fi
CMAKE_OPTIONS=(
  "-DBUILD_LIST=$MODULES" -DPYTHON3_LIMITED_API=ON
  "-DCMAKE_OSX_DEPLOYMENT_TARGET=$MIN_MACOS" "-DCMAKE_OSX_ARCHITECTURES=$ARCH"
  -DWITH_FFMPEG=OFF -DWITH_GSTREAMER=OFF -DWITH_AVFOUNDATION=OFF -DWITH_1394=OFF
  -DWITH_OBSENSOR=OFF -DVIDEOIO_ENABLE_PLUGINS=OFF -DHIGHGUI_ENABLE_PLUGINS=OFF
  -DWITH_QT=OFF -DWITH_GTK=OFF -DWITH_WIN32UI=OFF -DWITH_MSMF=OFF
  -DWITH_ZLIB_NG=OFF -DBUILD_ZLIB=ON -DWITH_JPEG=ON -DBUILD_JPEG=ON
  -DENABLE_LIBJPEG_TURBO_SIMD=ON -DWITH_PNG=ON -DBUILD_PNG=ON -DWITH_TIFF=ON
  -DBUILD_TIFF=ON -DWITH_WEBP=ON -DBUILD_WEBP=ON -DWITH_OPENJPEG=ON -DBUILD_OPENJPEG=ON
  -DWITH_IMGCODEC_GIF=ON -DWITH_IMGCODEC_HDR=ON -DWITH_IMGCODEC_SUNRASTER=ON
  -DWITH_IMGCODEC_PXM=ON -DWITH_IMGCODEC_PFM=ON
  -DWITH_OPENEXR=OFF -DWITH_AVIF=OFF -DWITH_JASPER=OFF -DWITH_SPNG=OFF -DWITH_JPEGXL=OFF
  "-DCMAKE_IGNORE_PREFIX_PATH=/opt/homebrew;/usr/local"
  -DWITH_IPP=OFF -DBUILD_IPP_IW=OFF -DWITH_UNIFONT=OFF -DWITH_PROTOBUF=OFF
  -DWITH_FLATBUFFERS=OFF -DWITH_ONNXRUNTIME=OFF -DWITH_OPENVINO=OFF -DWITH_EIGEN=OFF
  -DWITH_VTK=OFF -DWITH_TBB=OFF -DBUILD_TBB=OFF -DWITH_OPENMP=OFF -DWITH_GDAL=OFF
  -DWITH_GDCM=OFF -DBUILD_CLAPACK=OFF
  -DWITH_LAPACK=ON -DWITH_OPENCL=ON -DWITH_ITT=ON -DBUILD_ITT=ON
  "${ARM_ACCELERATION[@]}"
)
# One change to the sdist, in its build tooling only. OpenCV's typing stub generator
# refines functions of modules this build leaves out (features, calib) and defines aliases
# of their classes (FeatureDetector is Feature2D); it stops on the first missing one, and
# setup.py then fails on the missing py.typed. The patched generator skips refinements and
# aliases of symbols that were not built, so the wheel keeps the stubs of the built
# modules. STUB_PATCHES holds file, text and replacement triples; each text must occur
# exactly once.
STUB_DIR="opencv/modules/python/src2/typing_stubs_generation"
STUB_PATCHES=(
  "$STUB_DIR/api_refinement.py"
  "        refine_symbol(root, symbol_name)"
  "        try:
            refine_symbol(root, symbol_name)
        except (ScopeNotFoundError, SymbolNotFoundError):
            continue"
  "$STUB_DIR/api_refinement.py"
  "from .types_conversion import create_type_node"
  "from .types_conversion import create_type_node
from .ast_utils import ScopeNotFoundError, SymbolNotFoundError"
  "$STUB_DIR/generation.py"
  "        node.resolve(root)
        if isinstance(node, AliasTypeNode):"
  "        try:
            node.resolve(root)
        except TypeResolutionError:
            continue
        if isinstance(node, AliasTypeNode):"
  "$STUB_DIR/generation.py"
  "from .predefined_types import PREDEFINED_TYPES"
  "from .predefined_types import PREDEFINED_TYPES
from .nodes.type_node import TypeResolutionError"
)

patch_stub_generator() {  # applies STUB_PATCHES below SOURCE, or fails
  "$TOOLS/bin/python" - "$SOURCE" "${STUB_PATCHES[@]}" <<'EOF' || fail "Stub patch failed"
import sys
from pathlib import Path

source, *triples = sys.argv[1:]
for index in range(0, len(triples), 3):
    name, old, new = triples[index : index + 3]
    path = Path(source) / name
    text = path.read_text()
    if text.count(old) != 1:
        sys.exit(f"{old!r} does not occur exactly once in {path}")
    path.write_text(text.replace(old, new))
EOF
}
OPTIONS_HASH="$(print -rl -- "$OPENCV_VERSION" "$OPENCV_SHA256" "$PYTHON_VERSION" \
  "$MIN_MACOS" "$ARCH" "$KLEIDICV_SHA256" "${BUILD_TOOLS[@]}" "${CMAKE_OPTIONS[@]}" \
  "${THIRD_PARTY[@]}" "${STUB_PATCHES[@]}" | shasum -a 256 | cut -c 1-16)"
KEY="opencv-$OPENCV_VERSION-$ARCH-$OPTIONS_HASH"
OUT="$BUILD/$KEY"

if [[ "${1:-}" == --key ]]; then
  print -r -- "$KEY"
  exit 0
fi

fail() {  # message
  echo "$1" >&2
  exit 1
}

fetch_verified() {  # url, file, sha256
  [[ -f "$2" ]] || curl -fsSL -o "$2" "$1"
  echo "$3  $2" | shasum -a 256 -c - >/dev/null \
    || fail "Checksum mismatch for $2; delete it and rerun"
}

wheel_in() {  # folder; prints its only wheel, or returns 1
  local -a found
  found=("$1"/*.whl(N))
  ((${#found} == 1)) || return 1
  print -r -- "${found[1]}"
}

mkdir -p "$BUILD"
if [[ -d "$OUT" ]] && WHEEL="$(wheel_in "$OUT")"; then
  print -r -- "$WHEEL"
  exit 0
fi

# The sdist with its bundled 3rdparty sources; on arm64 the verified KleidiCV tarball goes
# where OpenCV's download step looks first.
prepare_source() {
  local cache="$SOURCE/.download-cache/kleidicv"
  rm -rf "$SOURCE"
  tar -xzf "$OPENCV_TARBALL" -C "$BUILD"
  if [[ "$ARCH" == arm64 ]]; then
    mkdir -p "$cache"
    cp "$KLEIDICV_TARBALL" "$cache/$KLEIDICV_MD5-kleidicv-$KLEIDICV_VERSION.tar.gz"
  fi
}

# License files of OpenCV and of each library in THIRD_PARTY. carotene states its license
# only in its source headers, so the header comment is the license file.
collect_licenses() {  # destination folder
  local opencv="$SOURCE/opencv" third="$1/3rdparty"
  mkdir -p "$third"/{zlib,libjpeg-turbo,libpng,libtiff,libwebp,openjpeg,ittnotify}
  cp "$opencv/LICENSE" "$1/LICENSE"
  cp "$opencv/3rdparty/zlib/LICENSE" "$third/zlib/"
  cp "$opencv/3rdparty/libjpeg-turbo/"{LICENSE.md,README.ijg} "$third/libjpeg-turbo/"
  cp "$opencv/3rdparty/libpng/LICENSE" "$third/libpng/"
  cp "$opencv/3rdparty/libtiff/LICENSE.md" "$third/libtiff/"
  cp "$opencv/3rdparty/libwebp/COPYING" "$third/libwebp/"
  cp "$opencv/3rdparty/openjpeg/LICENSE" "$third/openjpeg/"
  cp "$opencv/3rdparty/ittnotify/src/ittnotify/BSD-3-Clause.txt" "$third/ittnotify/"
  if [[ "$ARCH" == arm64 ]]; then
    mkdir -p "$third/carotene" "$third/kleidicv"
    sed -n '1,/\*\//p' "$opencv/hal/carotene/include/carotene/functions.hpp" \
      >"$third/carotene/LICENSE"
    tar -xzf "$KLEIDICV_TARBALL" -C "$third/kleidicv" --strip-components 2 \
      "kleidicv-$KLEIDICV_VERSION/LICENSES/Apache-2.0.txt"
  fi
}

write_wheel_notice() {  # licenses folder, output file
  local file
  {
    print -r -- "This opencv-python $OPENCV_VERSION wheel was built from the"
    print -r -- "opencv-python sdist by scripts/build_opencv.sh of Tower Borescope. cv2"
    print -r -- "contains OpenCV"
    print -r -- "${OPENCV_VERSION%.*} (Apache-2.0) and the third-party libraries whose"
    print -r -- "license files follow. It contains no FFmpeg, GStreamer or other video"
    print -r -- "I/O library."
    for file in $(cd "$1" && find . -type f | sort); do
      print -r -- "----------------------------------------------------------------------"
      print -r -- "${file#./}"
      print
      cat "$1/$file"
    done
  } >"$2"
}

build_wheel() {  # stage folder
  (
    cd "$SOURCE"
    export ENABLE_HEADLESS=1 ENABLE_CONTRIB=0 ENABLE_JAVA=0 ENABLE_ROLLING=0
    export OPENCV_PYTHON_SKIP_GIT_COMMANDS=1 CMAKE_GENERATOR="Unix Makefiles"
    export MACOSX_DEPLOYMENT_TARGET="$MIN_MACOS" CMAKE_OSX_ARCHITECTURES="$ARCH"
    export CMAKE_BUILD_PARALLEL_LEVEL="$MAKE_JOBS" MAKEFLAGS="-j$MAKE_JOBS"
    export OPENCV_DOWNLOAD_PATH="$SOURCE/.download-cache"
    export CMAKE_ARGS="${CMAKE_OPTIONS[*]}" PATH="$TOOLS/bin:$PATH"
    "$TOOLS/bin/python" -m pip wheel --no-build-isolation --no-deps --no-cache-dir -v \
      --wheel-dir "$1" . >"$1/build.log" 2>&1 \
      || {
        # With parallel jobs the first compiler error scrolls far above the log's end.
        echo "The OpenCV build failed. Errors in $1/build.log:" >&2
        grep -nE "error:|fatal error|\*\*\* \[" "$1/build.log" | head -60 >&2 || true
        echo "Last lines of the log:" >&2
        tail -40 "$1/build.log" >&2
        exit 1
      }
  )
}

check_downloads() {
  local -a logs
  logs=("$SOURCE"/_skbuild/*/cmake-build/CMakeDownloadLog.txt(N))
  ((${#logs} > 0)) || fail "The OpenCV build left no download log"
  if grep -q "^#cmake_download" "${logs[@]}"; then
    grep "^#cmake_download" "${logs[@]}" >&2
    fail "The OpenCV build downloaded files that are not pinned by this script"
  fi
}

sorted_words() {  # words; prints them sorted on one line
  print -rl -- "$@" | sort | tr '\n' ' '
}

# Linkage, architecture and minimum macOS version of the extension, then the modules,
# video I/O backends and third-party libraries that cv2.getBuildInformation() reports.
check_wheel() {  # stage folder, wheel
  local probe="$1/probe" info="$1/build-information.txt" libraries
  local -a extension
  rm -rf "$probe"
  mkdir -p "$probe"
  unzip -q "$2" -d "$probe"
  extension=("$probe"/cv2/cv2*.so)
  if otool -L "${extension[1]}" | tail -n +2 \
    | grep -vqE "^[[:space:]]+/(usr/lib|System/Library)/"; then
    fail "cv2 links a library outside macOS"
  fi
  lipo -archs "${extension[1]}" | grep -qw "$ARCH" || fail "cv2 is not built for $ARCH"
  [[ "$(otool -l "${extension[1]}" | awk '/minos/ {print $2; exit}')" == "$MIN_MACOS" ]] \
    || fail "cv2 does not target macOS $MIN_MACOS"
  PYTHONPATH="$probe" "$TOOLS/bin/python" -c \
    "import cv2; print(cv2.getBuildInformation())" >"$info"
  grep -qE "^ +To be built: +$BUILT_MODULES\$" "$info" \
    || fail "OpenCV built modules other than: $BUILT_MODULES"
  if grep -qiE "^ +(FFMPEG|GStreamer|AVFoundation|avcodec|avformat): +YES" "$info"; then
    fail "OpenCV was built with a video I/O backend"
  fi
  libraries="$(sed -nE 's/^ +3rdparty dependencies: +//p' "$info")"
  [[ "$(sorted_words ${=libraries})" == "$(sorted_words "${THIRD_PARTY[@]}")" ]] \
    || fail "OpenCV compiled in other third-party libraries: $libraries"
  rm -rf "$probe"
}

fetch_verified "$OPENCV_URL" "$OPENCV_TARBALL" "$OPENCV_SHA256"
if [[ "$ARCH" == arm64 ]]; then
  fetch_verified "$KLEIDICV_URL" "$KLEIDICV_TARBALL" "$KLEIDICV_SHA256"
else
  # libjpeg-turbo's x86 SIMD code needs NASM, a build tool that is not bundled.
  ASM_NASM="$(command -v nasm)" || fail "nasm is required on Intel: brew install nasm"
  export ASM_NASM
fi
SECONDS=0
STAGE="$OUT.partial"
echo "Building OpenCV $OPENCV_VERSION for $ARCH with $MAKE_JOBS jobs" >&2
echo "Log: $STAGE/build.log" >&2
uv venv --quiet --allow-existing --python "$PYTHON_VERSION" "$TOOLS"
uv pip install --quiet --python "$TOOLS/bin/python" "${BUILD_TOOLS[@]}"
# Separate commands: set -e does not stop on a failure inside an && list.
rm -rf "$STAGE"
mkdir -p "$STAGE"
prepare_source
patch_stub_generator
collect_licenses "$STAGE/licenses"
write_wheel_notice "$STAGE/licenses" "$SOURCE/LICENSE-3RD-PARTY.txt"
print -rl -- "${CMAKE_OPTIONS[@]}" >"$STAGE/cmake-args.txt"
build_wheel "$STAGE"
check_downloads
WHEEL="$(wheel_in "$STAGE")" || fail "The OpenCV build produced no wheel"
check_wheel "$STAGE" "$WHEEL"
print -r -- "$SECONDS" >"$STAGE/build-seconds.txt"
rm -rf "$OUT"
mv "$STAGE" "$OUT"
rm -rf "$SOURCE"
echo "Built the OpenCV wheel in $SECONDS s" >&2
print -r -- "$OUT/${WHEEL:t}"
