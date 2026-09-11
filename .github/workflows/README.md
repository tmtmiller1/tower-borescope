# workflows

GitHub Actions workflows.

## Files

- `ci.yml`: runs ruff, mypy, radon and the offline pytest suite on every push and pull request.
- `release.yml`: builds the application bundle and disk image on Apple silicon and Intel runners; a version tag publishes both images on a GitHub release.
