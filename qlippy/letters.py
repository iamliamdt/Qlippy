"""Letter shapes the wire can bend itself into (for spelling animations).

Each letter is a single continuous polyline (a wire can retrace itself),
resampled to N points so letters can be interpolated into each other.
"""

import math

from qgis.PyQt.QtCore import QPointF
from qgis.PyQt.QtGui import QPainterPath

N = 180
WORDS = ["QGIS", "GPKG", "SHP"]
TOP, BOTTOM = 70.0, 178.0


def sequence(word_index):
    """Shapes visited when spelling a word: starts and ends as the Q."""
    word = WORDS[int(round(word_index)) % len(WORDS)]
    letters = list(word[1:]) if word.startswith("Q") else list(word)
    return ["Q"] + letters + ["Q"]


def _arc(center_x, center_y, radius_x, radius_y, start_angle, end_angle, steps=40):
    return [(center_x + radius_x * math.cos(math.radians(start_angle + (end_angle - start_angle) * i / steps)),
             center_y + radius_y * math.sin(math.radians(start_angle + (end_angle - start_angle) * i / steps))) for i in range(steps + 1)]


def _letter(letter):
    if letter == "G":
        outline = _arc(100, 124, 52, 54, -40, -350, 60)
        end = outline[-1]
        return outline + [(end[0], 128), (112, 128)]
    if letter == "I":
        return [(74, TOP), (126, TOP), (100, TOP), (100, BOTTOM), (74, BOTTOM), (126, BOTTOM)]
    if letter == "S":
        top = _arc(100, 97, 34, 27, -15, -270, 40)
        bottom = _arc(100, 151, 36, 27, -90, 160, 40)
        return top + bottom
    if letter == "P":
        bowl = _arc(108, 98, 30, 28, -90, 90, 30)
        return [(68, BOTTOM), (68, TOP), (108, TOP)] + bowl + [(68, 126)]
    if letter == "K":
        return [(68, TOP), (68, BOTTOM), (68, 130), (134, TOP), (90, 112), (136, BOTTOM)]
    if letter == "H":
        return [(66, BOTTOM), (66, TOP), (66, 124), (134, 124), (134, TOP), (134, BOTTOM)]
    raise KeyError(letter)


def points(letter):
    """N evenly spaced points along letter ch."""
    outline = _letter(letter)
    path = QPainterPath(QPointF(*outline[0]))
    for x, y in outline[1:]:
        path.lineTo(QPointF(x, y))
    return [path.pointAtPercent(i / (N - 1)) for i in range(N)]
