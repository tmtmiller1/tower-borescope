"""Mutation scores for each area of tower_borescope from a finished mutmut run.

``mutmut run`` records the exit code of every mutant in ``mutants/<source>.meta``.
This script turns those records into a score for each subpackage (``app``, ``ai``,
``device`` and the rest, with the modules directly under the package reported as
``tower_borescope``) and compares each score with the floor recorded in
``docs/mutation_baseline.json``.

The score is the fraction of evaluated mutants the suite killed. Evaluated mutants
are the ones killed, survived, reached by no test, timed out, suspicious or crashed;
skipped mutants are out of scope. A mutant the type checker rejects counts as killed.
A run that still has unchecked mutants is incomplete: the gate fails and the floors
are not rewritten from it.

Usage::

    python scripts/mutation_score.py                    report the scores
    python scripts/mutation_score.py --gate             exit 1 below a floor
    python scripts/mutation_score.py --update-baseline  record the scores as floors
"""

from __future__ import annotations

import argparse
import json
import math
from collections.abc import Mapping, Sequence
from dataclasses import asdict, dataclass, fields
from pathlib import Path
from types import MappingProxyType
from typing import Final

PACKAGE = "tower_borescope"
SOURCE_PREFIX = ("src", PACKAGE)
ROOT = Path(__file__).resolve().parent.parent
DEFAULT_MUTANTS = ROOT / "mutants"
DEFAULT_BASELINE = ROOT / "docs" / "mutation_baseline.json"
# A mutant that races or times out can flip between killed and survived from one run
# to the next; one point absorbs that without hiding a real regression.
SCORE_TOLERANCE = 0.01
EXIT_BELOW_FLOOR = 1
EXIT_NO_RESULTS = 2
UNKNOWN_STATUS = "suspicious"
COLUMNS = ("killed", "survived", "no_tests", "timeout", "suspicious", "segfault")
BASELINE_NOTE = (
    "Minimum mutation score for each area of tower_borescope. A run may equal these "
    "floors but not fall more than one point below any of them. Regenerate with "
    "'python scripts/mutation_score.py --update-baseline' after a complete run."
)

# Exit codes as mutmut 3.7 classifies them in mutmut.__main__.status_by_exit_code.
STATUS_BY_EXIT_CODE: Final[Mapping[int | None, str]] = MappingProxyType(
    {
        None: "not_checked",
        0: "survived",
        1: "killed",
        2: "not_checked",
        3: "killed",
        5: "no_tests",
        33: "no_tests",
        34: "skipped",
        35: "suspicious",
        36: "timeout",
        37: "killed",
        24: "timeout",
        -24: "timeout",
        152: "timeout",
        255: "timeout",
        -11: "segfault",
        -9: "segfault",
    }
)


@dataclass(slots=True)
class Counters:
    """Mutant outcomes for one area.

    Attributes:
        killed: Mutants a test or the type checker caught.
        survived: Mutants every test ran past without failing.
        no_tests: Mutants in code no test reaches.
        timeout: Mutants whose tests ran past the time limit.
        suspicious: Mutants mutmut could not classify.
        segfault: Mutants whose test process crashed.
        skipped: Mutants excluded by configuration.
        not_checked: Mutants the run has not reached yet.
    """

    killed: int = 0
    survived: int = 0
    no_tests: int = 0
    timeout: int = 0
    suspicious: int = 0
    segfault: int = 0
    skipped: int = 0
    not_checked: int = 0

    def record(self, status: str) -> None:
        """Count one mutant with ``status``, a field name of this class."""
        setattr(self, status, getattr(self, status) + 1)

    def merge(self, other: Counters) -> None:
        """Add every count of ``other`` to this one."""
        for field in fields(self):
            setattr(
                self, field.name, getattr(self, field.name) + getattr(other, field.name)
            )

    @property
    def evaluated(self) -> int:
        """Mutants that count toward the score."""
        return sum(getattr(self, column) for column in COLUMNS)

    @property
    def score(self) -> float:
        """Fraction of evaluated mutants killed, from 0.0 to 1.0."""
        return self.killed / self.evaluated if self.evaluated else 0.0


def area_of(meta_path: Path, mutants: Path) -> str:
    """Subpackage a ``.meta`` record belongs to, or the package for its own modules.

    Args:
        meta_path: Path of a record, such as
            ``mutants/src/tower_borescope/ai/http.py.meta``.
        mutants: The mutmut working directory the record lives under.

    Returns:
        The first subpackage name, or ``tower_borescope`` for top-level modules.

    Raises:
        ValueError: When the record is not under ``src/tower_borescope``.
    """
    parts = meta_path.relative_to(mutants).parts
    if parts[: len(SOURCE_PREFIX)] != SOURCE_PREFIX:
        raise ValueError(f"{meta_path} is not a record of the {PACKAGE} package")
    inner = parts[len(SOURCE_PREFIX) :]
    return inner[0] if len(inner) > 1 else PACKAGE


def read_counters(mutants: Path) -> dict[str, Counters]:
    """Counters for each area from every record under ``mutants/src``.

    Args:
        mutants: The mutmut working directory.

    Returns:
        Counters keyed by area name; empty when there are no records.
    """
    areas: dict[str, Counters] = {}
    for meta_path in sorted((mutants / "src").rglob("*.py.meta")):
        exit_codes = json.loads(meta_path.read_text())["exit_code_by_key"]
        counters = areas.setdefault(area_of(meta_path, mutants), Counters())
        for exit_code in exit_codes.values():
            counters.record(STATUS_BY_EXIT_CODE.get(exit_code, UNKNOWN_STATUS))
    return areas


def total(areas: Mapping[str, Counters]) -> Counters:
    """All areas combined."""
    combined = Counters()
    for counters in areas.values():
        combined.merge(counters)
    return combined


def floor_4dp(value: float) -> float:
    """``value`` rounded down to four decimal places, so a floor never exceeds it."""
    return math.floor(value * 10_000) / 10_000


def load_floors(path: Path) -> dict[str, float]:
    """Recorded floors keyed by area, or an empty mapping when there is no baseline."""
    if not path.exists():
        return {}
    areas = json.loads(path.read_text()).get("areas", {})
    return {str(name): float(score) for name, score in areas.items()}


def write_baseline(path: Path, areas: Mapping[str, Counters]) -> None:
    """Record each area's score as its floor, with the counts behind it."""
    ordered = sorted(areas.items())
    payload = {
        "note": BASELINE_NOTE,
        "overall_score": floor_4dp(total(areas).score),
        "areas": {name: floor_4dp(counters.score) for name, counters in ordered},
        "measured": {name: asdict(counters) for name, counters in ordered},
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2) + "\n")


def gate_problems(
    areas: Mapping[str, Counters], floors: Mapping[str, float]
) -> list[str]:
    """Reasons the run fails the gate: unchecked mutants or a score below its floor."""
    problems: list[str] = []
    for name, counters in sorted(areas.items()):
        if counters.not_checked:
            count = counters.not_checked
            problems.append(f"{name}: {count} mutants not checked; the run is incomplete")
        floor = floors.get(name, 0.0)
        if counters.score < floor - SCORE_TOLERANCE:
            problems.append(f"{name}: score {counters.score:.2%} is below {floor:.2%}")
    return problems


def _row(name: str, counters: Counters, floor: float | None) -> str:
    """One table row: area, score, floor and every counted outcome."""
    floor_text = "-" if floor is None else f"{floor:.2%}"
    values = " ".join(f"{getattr(counters, column):>10}" for column in COLUMNS)
    checked = f"{counters.not_checked:>11}"
    return f"{name:16} {counters.score:>7.2%} {floor_text:>7} {values} {checked}"


def render(areas: Mapping[str, Counters], floors: Mapping[str, float]) -> str:
    """Text table of every area and the overall score."""
    labels = " ".join(f"{column:>10}" for column in COLUMNS)
    lines = [f"{'area':16} {'score':>7} {'floor':>7} {labels} {'not_checked':>11}"]
    lines.extend(
        _row(name, counters, floors.get(name)) for name, counters in sorted(areas.items())
    )
    lines.append(_row("overall", total(areas), None))
    return "\n".join(lines)


def _parser() -> argparse.ArgumentParser:
    """Command-line options."""
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--mutants", type=Path, default=DEFAULT_MUTANTS)
    parser.add_argument("--baseline", type=Path, default=DEFAULT_BASELINE)
    parser.add_argument("--gate", action="store_true", help="exit 1 below a floor")
    parser.add_argument("--update-baseline", action="store_true")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    """Report the scores, then apply the gate or record new floors when asked.

    Args:
        argv: Command-line arguments; ``sys.argv`` when None.

    Returns:
        0 on success, 1 when the gate fails or the floors cannot be recorded, and 2
        when there are no mutmut results.
    """
    args = _parser().parse_args(argv)
    areas = read_counters(args.mutants)
    if not areas:
        print(f"mutation_score: no mutmut results under {args.mutants}")
        return EXIT_NO_RESULTS
    floors = load_floors(args.baseline)
    print(render(areas, floors))
    problems = gate_problems(areas, floors) if args.gate else []
    if args.update_baseline:
        if total(areas).not_checked:
            problems.append("floors not recorded: the run is incomplete")
        else:
            write_baseline(args.baseline, areas)
            print(f"mutation_score: floors recorded in {args.baseline}")
    for problem in problems:
        print(f"mutation_score: {problem}")
    return EXIT_BELOW_FLOOR if problems else 0


if __name__ == "__main__":
    raise SystemExit(main())
