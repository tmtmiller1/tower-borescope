"""Issue boxes taken from an AI analysis, in fractions of the image."""

from __future__ import annotations

from typing import NamedTuple

from tower_borescope.ai.schema import Analysis

BOX_COORDINATES = 4


class AiBox(NamedTuple):
    """One highlighted region with its label.

    Attributes:
        x0: Left edge as a fraction of the image width.
        y0: Top edge as a fraction of the image height.
        x1: Right edge as a fraction of the image width.
        y1: Bottom edge as a fraction of the image height.
        label: Text shown next to the box.
        severity: One of ``ai.schema.SEVERITIES``; it selects the color.
    """

    x0: float
    y0: float
    x1: float
    y1: float
    label: str
    severity: str


def boxes_from_analysis(analysis: Analysis) -> list[AiBox]:
    """Boxes for the issues that carry exactly four box coordinates.

    Args:
        analysis: A structured analysis, normally already normalized.

    Returns:
        One box per located issue, in issue order.
    """
    boxes: list[AiBox] = []
    for issue in analysis.issues:
        box = issue.box
        if box is None or len(box) != BOX_COORDINATES:
            continue
        x0, y0, x1, y1 = (float(value) for value in box)
        boxes.append(AiBox(x0, y0, x1, y1, issue.label, issue.severity))
    return boxes
