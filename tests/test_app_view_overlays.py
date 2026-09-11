"""Tests for tower_borescope.app.view.overlays: items, undo history and snapshots."""

from __future__ import annotations

from tower_borescope.app.view.overlays import OverlayModel
from tower_borescope.measure.shapes import Annotation, Measurement, OverlaySnapshot


def _model():
    changes = []
    return OverlayModel(lambda: changes.append(1)), changes


def _distance():
    return Measurement("distance", [(0.0, 0.0), (10.0, 0.0)])


def test_finished_items_go_to_their_lists():
    model, changes = _model()
    distance = _distance()
    arrow = Annotation("arrow", [(0.0, 0.0), (5.0, 5.0)])
    model.finish_item(distance)
    model.finish_item(arrow)
    assert model.measurements == [distance]
    assert model.annotations == [arrow]
    assert len(changes) == 2


def test_undo_drops_the_item_in_progress_first():
    model, changes = _model()
    model.finish_item(_distance())
    model.current = Measurement("angle", [(1.0, 1.0)])
    model.undo()
    assert model.current is None
    assert len(model.measurements) == 1
    model.undo()
    assert model.measurements == []
    model.undo()
    assert len(changes) == 4


def test_undo_removes_by_identity_in_reverse_order():
    model, _ = _model()
    first, second = _distance(), _distance()
    note = Annotation("text", [(3.0, 3.0)], "a")
    for item in (first, note, second):
        model.finish_item(item)
    model.undo()
    assert model.measurements == [first] and model.measurements[0] is first
    model.undo()
    assert model.annotations == []
    assert model.measurements[0] is first


def test_clear_empties_everything():
    model, changes = _model()
    model.finish_item(_distance())
    model.current = Annotation("arrow", [(0.0, 0.0)])
    model.clear()
    assert (model.measurements, model.annotations, model.current) == ([], [], None)
    model.undo()
    assert changes


def test_clearing_one_kind_keeps_the_other_and_its_history():
    model, _ = _model()
    distance, arrow = _distance(), Annotation("arrow", [(0.0, 0.0), (1.0, 1.0)])
    model.finish_item(distance)
    model.finish_item(arrow)
    model.clear_annotations()
    assert model.annotations == [] and model.measurements == [distance]
    model.undo()
    assert model.measurements == []
    model.finish_item(arrow)
    model.finish_item(distance)
    model.clear_measurements()
    model.undo()
    assert model.annotations == []


def test_snapshot_copies_the_lists():
    model = OverlayModel()
    model.finish_item(_distance())
    snapshot = model.snapshot(0.1, "in")
    assert isinstance(snapshot, OverlaySnapshot)
    assert snapshot.has_items and snapshot.mm_per_px == 0.1 and snapshot.unit == "in"
    model.clear()
    assert len(snapshot.measurements) == 1
    assert not model.snapshot(None, "mm").has_items
