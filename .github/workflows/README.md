# workflows

GitHub Actions workflows.

## Files

- `ci.yml`: runs ruff, mypy, radon and the offline pytest suite on every push and pull request.
- `release.yml`: builds OpenCV without FFmpeg (cached with `actions/cache` under the key from `scripts/build_opencv.sh --key`), the application bundle and the disk image on Apple silicon and Intel runners, then runs the imaging, measurement, JPEG and gallery tests against that OpenCV build and the bundled ffmpeg, failing the release when they fail; a version tag publishes both images and the ffmpeg and libusb source tarballs on a GitHub release.
