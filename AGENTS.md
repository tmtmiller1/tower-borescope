# tower_borescope agent guide

Operating notes for agentic tools working in this repository. The code follows the Tower coding
standards (`tower-agent/.github/instructions/coding_standards.instructions.md`); the limits that
tooling enforces are restated here so the repository stays self-contained.

## Layout

- `src/tower_borescope/`: the package. Subpackages `device`, `imaging`, `measure`, `capture`,
  `remote`, `ai` and `app`; shared modules `config`, `errors`, `image_types`, `jpeg` and `cli`.
- `tests/`: pytest suite. `conftest.py` sandboxes every data location; `synthetic.py` generates
  frames and USB packets; `fakes.py` holds the camera reader and AI backend doubles.
- `scripts/`: environment setup, application bundle build and the limits checker.
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
scripts/build_app.sh
```

`scripts/check_limits.py` measures the size and complexity limits in the table below and
exits 1 on any finding; CI runs it after radon.
`--camera` tests need the borescope attached and no running Tower Borescope process.
`--live-ai` tests need a local Ollama server with a vision model. `scripts/build_app.sh` needs
the `build` dependency group (`uv sync --all-groups`) and produces the signed bundle and the
disk image in `dist/`; `.github/workflows/release.yml` runs it for both architectures.

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
