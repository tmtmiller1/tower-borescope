"""Tests for scripts/mutation_score.py: statuses, areas, floors and the gate."""

from __future__ import annotations

import json
from pathlib import Path

import mutation_score
import pytest
from mutation_score import Counters


def _meta(mutants: Path, source: str, codes: dict[str, int | None]) -> None:
    path = mutants / "src" / "tower_borescope" / f"{source}.meta"
    path.parent.mkdir(parents=True, exist_ok=True)
    record = {
        "exit_code_by_key": codes,
        "hash_by_function_name": {},
        "type_check_error_by_key": {},
        "durations_by_key": {},
        "estimated_durations_by_key": {},
    }
    path.write_text(json.dumps(record))


def _codes(killed: int, survived: int) -> dict[str, int | None]:
    codes: dict[str, int | None] = {f"k{index}": 1 for index in range(killed)}
    codes.update({f"s{index}": 0 for index in range(survived)})
    return codes


def _run(tmp_path: Path, *options: str) -> int:
    paths = ["--mutants", str(tmp_path / "mutants")]
    paths += ["--baseline", str(tmp_path / "baseline.json")]
    return mutation_score.main([*paths, *options])


def test_statuses_follow_mutmut_exit_codes(tmp_path: Path) -> None:
    codes = {"a": 1, "b": 0, "c": None, "d": 33, "e": 36, "f": -11, "g": 34, "h": 37}
    _meta(tmp_path / "mutants", "jpeg.py", {**codes, "i": 99})
    counters = mutation_score.read_counters(tmp_path / "mutants")["tower_borescope"]
    expected = Counters(
        killed=2,
        survived=1,
        no_tests=1,
        timeout=1,
        suspicious=1,
        segfault=1,
        skipped=1,
        not_checked=1,
    )
    assert counters == expected
    assert counters.evaluated == 7
    assert counters.score == pytest.approx(2 / 7)


def test_areas_follow_the_first_subpackage(tmp_path: Path) -> None:
    mutants = tmp_path / "mutants"
    _meta(mutants, "jpeg.py", _codes(1, 0))
    _meta(mutants, "imaging/color.py", _codes(2, 0))
    _meta(mutants, "imaging/enhance.py", _codes(1, 1))
    _meta(mutants, "app/window/menus.py", _codes(0, 1))
    areas = mutation_score.read_counters(mutants)
    assert sorted(areas) == ["app", "imaging", "tower_borescope"]
    assert (areas["imaging"].killed, areas["imaging"].survived) == (3, 1)
    assert mutation_score.total(areas).evaluated == 6


def test_record_outside_the_package_is_rejected(tmp_path: Path) -> None:
    stray = tmp_path / "mutants" / "scripts" / "check_limits.py.meta"
    with pytest.raises(ValueError, match="tower_borescope"):
        mutation_score.area_of(stray, tmp_path / "mutants")


def test_empty_counters_score_zero() -> None:
    assert Counters().score == 0.0


def test_gate_allows_one_point_of_noise(tmp_path: Path) -> None:
    (tmp_path / "baseline.json").write_text(json.dumps({"areas": {"imaging": 0.8}}))
    _meta(tmp_path / "mutants", "imaging/color.py", _codes(159, 41))
    assert _run(tmp_path, "--gate") == 0
    _meta(tmp_path / "mutants", "imaging/color.py", _codes(39, 11))
    assert _run(tmp_path, "--gate") == mutation_score.EXIT_BELOW_FLOOR


def test_incomplete_run_fails_the_gate_and_keeps_the_floors(tmp_path: Path) -> None:
    _meta(tmp_path / "mutants", "ai/http.py", {"a": 1, "b": None})
    assert _run(tmp_path, "--gate") == mutation_score.EXIT_BELOW_FLOOR
    assert _run(tmp_path, "--update-baseline") == mutation_score.EXIT_BELOW_FLOOR
    assert not (tmp_path / "baseline.json").exists()


def test_update_baseline_rounds_the_floors_down(tmp_path: Path) -> None:
    _meta(tmp_path / "mutants", "ai/http.py", _codes(2, 1))
    assert _run(tmp_path, "--update-baseline") == 0
    baseline = json.loads((tmp_path / "baseline.json").read_text())
    assert baseline["areas"] == {"ai": 0.6666}
    assert baseline["overall_score"] == 0.6666
    assert baseline["measured"]["ai"]["survived"] == 1
    assert _run(tmp_path, "--gate") == 0


def test_missing_results_exit_with_two(tmp_path: Path) -> None:
    assert _run(tmp_path) == mutation_score.EXIT_NO_RESULTS


def test_report_lists_every_area_and_the_total(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    _meta(tmp_path / "mutants", "device/packets.py", _codes(3, 1))
    assert _run(tmp_path) == 0
    lines = capsys.readouterr().out.splitlines()
    assert lines[0].split()[:3] == ["area", "score", "floor"]
    assert lines[1].split()[:4] == ["device", "75.00%", "-", "3"]
    assert lines[2].split()[:2] == ["overall", "75.00%"]
