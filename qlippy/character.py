"""Procedural artwork for Qlippy: a Q-shaped paperclip standing on a sheet of
paper with a world map on it.

Everything is drawn in a fixed logical coordinate space (LOGICAL_W x
LOGICAL_H) from a *pose* dict, so animations only have to change numbers.
"""

import math

from qgis.PyQt.QtCore import QPointF, QRectF, Qt
from qgis.PyQt.QtGui import (
    QBrush,
    QColor,
    QFont,
    QLinearGradient,
    QPainter,
    QPainterPath,
    QPainterPathStroker,
    QPen,
    QImage,
    QPolygonF,
    QRadialGradient,
    QTransform,
)

from . import letters, worldmap

LOGICAL_W = 200.0
LOGICAL_H = 240.0

CX, CY, RING_R = 100.0, 123.0, 56.0
# Paper corners: top-left, top-right, bottom-right, bottom-left.
PAPER_QUAD = [(38.0, 178.0), (178.0, 170.0), (194.0, 226.0), (10.0, 234.0)]
# Where the paper goes when Qlippy uses it as a blanket.
BLANKET_QUAD = [(44.0, 132.0), (156.0, 126.0), (176.0, 194.0), (28.0, 200.0)]
MAP_U = (0.08, 0.92)  # map inset on the paper, in paper (u, v) space
MAP_V = (0.11, 0.89)
BODY_CENTER = QPointF(CX, CY)  # rotation pivot
BODY_BASE = QPointF(100.0, 180.0)  # squash/stretch pivot
EYE_L = QPointF(83.0, 88.0)
EYE_R = QPointF(118.0, 88.0)
TAIL_A = QPointF(114.0, 138.0)  # inner end of the tail (the hairpin bend)
TAIL_TIP = QPointF(168.0, 196.0)

DEFAULT_POSE = {
    # body transform
    "offset_x": 0.0, "offset_y": 0.0, "rotation": 0.0, "scale_x": 1.0, "scale_y": 1.0, "alpha": 1.0,
    # face (look_* None = follow the cursor)
    "look_x": None, "look_y": None, "lid": 0.0, "squint": 0.0,
    "brow_l": 0.0, "brow_r": 0.0, "brow_tilt": 0.0,
    "eye_scale": 1.0, "pupil_scale": 1.0, "happy": 0.0, "spiral": 0.0, "x_eyes": 0.0,
    "tail_rot": 0.0,
    # letter morphing: word index into letters.WORDS, morph position 0..len+1
    "word": 0.0, "morph": 0.0,
    # paper
    "paper_curl": 0.0, "paper_dy": 0.0, "paper_dx": 0.0, "paper_lift": 0.0, "paper_rot": 0.0,
    "paper_fold1": 0.0, "paper_fold2": 0.0, "paper_wave": 0.0, "paper_roll": 0.0,
    "paper_alpha": 1.0, "blanket": 0.0,
    # animation phase in seconds (drives looping extras)
    "phase": 0.0,
    # extras (0..1 visibility)
    "bulb": 0.0, "exclaim": 0.0, "question": 0.0, "sweat": 0.0, "zzz": 0.0,
    "hearts": 0.0, "sparkle": 0.0, "steam": 0.0, "notes": 0.0,
    "glasses": 0.0, "blush": 0.0, "tears": 0.0, "hat": 0.0, "confetti": 0.0,
    "stars": 0.0, "tap": 0.0,
    "mag": 0.0, "mag_x": 100.0, "mag_y": 204.0,
    "pin": 0.0, "pin_drop": 0.0, "pin_lon": worldmap.PIN_LONLAT[0], "pin_lat": worldmap.PIN_LONLAT[1],
    "pins_n": 0.0, "route": 0.0,
    "plane": 0.0, "plane_x": 100.0, "plane_y": 120.0, "plane_rot": 0.0,
    "telescope": 0.0, "telescope_ang": -20.0,
}

# Pose keys that only change pixels inside the existing silhouette.
FACE_ONLY_KEYS = {"look_x", "look_y", "lid", "squint", "pupil_scale", "happy", "spiral", "x_eyes",
                  "blush", "phase"}

# Extras drawn relative to the body, with their logical bounding boxes
# (used for the input mask).
_BODY_EXTRA_BOUNDS = {
    "bulb": QRectF(80, -4, 40, 44),
    "exclaim": QRectF(138, 22, 32, 46),
    "question": QRectF(136, 20, 36, 48),
    "sweat": QRectF(136, 52, 18, 30),
    "zzz": QRectF(122, 4, 70, 70),
    "steam": QRectF(50, 10, 100, 50),
    "hat": QRectF(78, 14, 50, 52),
    "stars": QRectF(50, 38, 100, 40),
    "tears": QRectF(66, 96, 70, 46),
    "telescope": QRectF(96, 52, 104, 76),
}
_WORLD_EXTRA_BOUNDS = {
    "hearts": QRectF(20, 0, 160, 130),
    "notes": QRectF(10, 0, 180, 130),
    "confetti": QRectF(0, 0, 200, 200),
    "sparkle": QRectF(10, 10, 180, 180),
    "tap": QRectF(0, 0, 200, 60),
}

INK = QColor("#262626")

PIN_CITIES = [worldmap.PIN_LONLAT, (-74.0, 40.7), (139.7, 35.7), (-43.2, -22.9), (151.2, -33.9),
              (18.4, -33.9), (77.2, 28.6)]
ROUTE = [(16.4, 48.2), (-9.1, 38.7), (-40.0, 30.0), (-74.0, 40.7), (-60.0, 5.0), (-43.2, -22.9)]


def _clamp(v, lo=0.0, hi=1.0):
    return lo if v < lo else hi if v > hi else v


def _mix(color, target, amount):
    color, target = QColor(color), QColor(target)
    return QColor(int(color.red() * (1 - amount) + target.red() * amount), int(color.green() * (1 - amount) + target.green() * amount),
                  int(color.blue() * (1 - amount) + target.blue() * amount))


def _rotate_about(point, pivot, deg):
    angle = math.radians(deg)
    dx, dy = point.x() - pivot.x(), point.y() - pivot.y()
    return QPointF(pivot.x() + dx * math.cos(angle) - dy * math.sin(angle),
                   pivot.y() + dx * math.sin(angle) + dy * math.cos(angle))


def _lerp(start, end, amount):
    return QPointF(start.x() + (end.x() - start.x()) * amount, start.y() + (end.y() - start.y()) * amount)


def _bilinear(quad, u, v):
    top = _lerp(quad[0], quad[1], u)
    bot = _lerp(quad[3], quad[2], u)
    return _lerp(top, bot, v)


def _area(points):
    doubled_area = 0.0
    for i in range(len(points)):
        x1, y1 = points[i].x(), points[i].y()
        x2, y2 = points[(i + 1) % len(points)].x(), points[(i + 1) % len(points)].y()
        doubled_area += x1 * y2 - x2 * y1
    return doubled_area / 2.0


def _sub_path(path, start, end, steps=60):
    piece = QPainterPath()
    for i in range(steps + 1):
        point = path.pointAtPercent(_clamp(start + (end - start) * i / steps))
        if i == 0:
            piece.moveTo(point)
        else:
            piece.lineTo(point)
    return piece


def lonlat_to_uv(lon, lat):
    u = MAP_U[0] + (lon + 180.0) / 360.0 * (MAP_U[1] - MAP_U[0])
    v = MAP_V[0] + (90.0 - lat) / 180.0 * (MAP_V[1] - MAP_V[0])
    return u, v


class Palette:
    def __init__(self, tint=True):
        self.tint = tint
        if tint:
            green = "#589632"
            self.outline = QColor("#2f4a2a")
            self.ring = [(0.0, _mix("#f7f9f5", green, 0.35)), (0.45, _mix("#c3cad1", green, 0.55)),
                         (1.0, _mix("#8e98a3", green, 0.62))]
            self.tail = [(0.0, QColor("#ee7913")), (0.14, QColor("#f0b030")), (0.26, QColor("#f0e64a")),
                         (0.42, QColor("#9cc04a")), (0.55, QColor("#7fae55")), (1.0, QColor("#5f8a4a"))]
            self.warm = QColor("#ee7913")
        else:
            self.outline = QColor("#3a4048")
            self.ring = [(0.0, QColor("#f5f7f9")), (0.45, QColor("#c3cad1")), (1.0, QColor("#8e98a3"))]
            self.tail = [(0.0, QColor("#c3cad1")), (1.0, QColor("#8e98a3"))]
            self.warm = None


class Renderer:
    """Draws Qlippy for a pose. Stateless apart from geometry caches."""

    WIRE_W = 5.2

    def __init__(self, tint=True):
        self.palette = Palette(tint)
        self._land = [QPolygonF([QPointF(lon, lat) for lon, lat in ring]) for ring in worldmap.LAND]
        self._graticule = []
        for lon in range(-150, 180, 30):
            self._graticule.append((QPointF(lon, -90), QPointF(lon, 90)))
        for lat in range(-60, 90, 30):
            self._graticule.append((QPointF(-180, lat), QPointF(180, lat)))
        self._ring = None
        self._ring_clip = None
        self._crossing = None
        self._shapes = {}
        self._tail_cache = {}

    def set_tint(self, tint):
        if tint != self.palette.tint:
            self.palette = Palette(tint)

    # ------------------------------------------------------------ geometry
    def ring_path(self):
        """Spiral (inner loop -> outer loop) plus the hairpin back in to TAIL_A."""
        if self._ring is not None:
            return self._ring
        start, sweep, steps = 100.0, 630.0, 180
        points = []
        for i in range(steps + 1):
            fraction = i / steps
            ring_scale = 0.6 + 0.4 * fraction
            angle = math.radians(start + sweep * fraction)
            points.append(QPointF(CX + RING_R * ring_scale * math.cos(angle), CY + RING_R * ring_scale * math.sin(angle)))
        path = QPainterPath(points[0])
        for point in points[1:]:
            path.lineTo(point)
        end_point, previous = points[-1], points[-2]
        tangent_x, tangent_y = end_point.x() - previous.x(), end_point.y() - previous.y()
        tangent_length = math.hypot(tangent_x, tangent_y) or 1.0
        path.cubicTo(QPointF(end_point.x() + tangent_x / tangent_length * 16, end_point.y() + tangent_y / tangent_length * 16),
                     QPointF(TAIL_A.x() - 10, TAIL_A.y() - 10), TAIL_A)
        self._ring = path
        stroker = QPainterPathStroker()
        stroker.setWidth(self.WIRE_W + 3.0)
        stroker.setCapStyle(Qt.PenCapStyle.FlatCap)
        self._ring_clip = stroker.createStroke(path)
        self._crossing = self._find_crossing(path)
        return path

    @staticmethod
    def _find_crossing(ring):
        """Where the hairpin passes under the spiral: (percent on spiral, point)."""
        length = ring.length()
        hairpin_start = ring.percentAtLength(length - 64)
        spiral_end = ring.percentAtLength(length - 70)
        best = None
        hairpin_points = [ring.pointAtPercent(hairpin_start + (1 - hairpin_start) * i / 80) for i in range(81)]
        for j in range(401):
            spiral_percent = spiral_end * j / 400
            spiral_point = ring.pointAtPercent(spiral_percent)
            for hairpin_point in hairpin_points:
                distance_sq = (hairpin_point.x() - spiral_point.x()) ** 2 + (hairpin_point.y() - spiral_point.y()) ** 2
                if best is None or distance_sq < best[0]:
                    best = (distance_sq, spiral_percent, spiral_point)
        if best and best[0] < 9:
            return best[1], best[2]
        return None

    @staticmethod
    def tail_exit():
        """Point where the tail leaves the outer ring (the tail's 'elbow')."""
        dx, dy = TAIL_TIP.x() - TAIL_A.x(), TAIL_TIP.y() - TAIL_A.y()
        from_center_x, from_center_y = TAIL_A.x() - CX, TAIL_A.y() - CY
        quad_a = dx * dx + dy * dy
        quad_b = 2 * (from_center_x * dx + from_center_y * dy)
        quad_c = from_center_x * from_center_x + from_center_y * from_center_y - (RING_R * 0.98) ** 2
        along = (-quad_b + math.sqrt(max(0.0, quad_b * quad_b - 4 * quad_a * quad_c))) / (2 * quad_a)
        return QPointF(TAIL_A.x() + dx * along, TAIL_A.y() + dy * along)

    def tail_path(self, tail_rot=0.0):
        key = round(tail_rot, 1)
        path = self._tail_cache.get(key)
        if path is not None:
            return path
        path = QPainterPath(TAIL_A)
        if abs(tail_rot) < 0.05:
            path.lineTo(TAIL_TIP)
        else:
            elbow = self.tail_exit()
            tip = _rotate_about(TAIL_TIP, elbow, tail_rot)
            path.lineTo(elbow)
            path.lineTo(tip)
        if len(self._tail_cache) > 64:
            self._tail_cache.clear()
        self._tail_cache[key] = path
        return path

    def q_polyline(self):
        if "Q" not in self._shapes:
            full = QPainterPath(self.ring_path())
            full.lineTo(TAIL_TIP)
            self._shapes["Q"] = [full.pointAtPercent(i / (letters.N - 1)) for i in range(letters.N)]
        return self._shapes["Q"]

    def shape_points(self, letter):
        if letter == "Q":
            return self.q_polyline()
        if letter not in self._shapes:
            self._shapes[letter] = letters.points(letter)
        return self._shapes[letter]

    def morph_points(self, pose):
        """Interpolated letter polyline, or None when showing the normal Q."""
        shapes = letters.sequence(pose["word"])
        morph = _clamp(pose["morph"], 0.0, len(shapes) - 1.0)
        if morph < 1e-3 or morph > len(shapes) - 1 - 1e-3:
            return None
        index = min(int(morph), len(shapes) - 2)
        blend = morph - index
        alpha, b = self.shape_points(shapes[index]), self.shape_points(shapes[index + 1])
        return [QPointF(from_point.x() + (to_point.x() - from_point.x()) * blend, from_point.y() + (to_point.y() - from_point.y()) * blend)
                for from_point, to_point in zip(alpha, b)]

    @staticmethod
    def body_transform(pose):
        transform = QTransform()
        transform.translate(pose["offset_x"], pose["offset_y"])
        transform.translate(BODY_BASE.x(), BODY_BASE.y())
        transform.scale(pose["scale_x"], pose["scale_y"])
        transform.translate(-BODY_BASE.x(), -BODY_BASE.y())
        transform.translate(BODY_CENTER.x(), BODY_CENTER.y())
        transform.rotate(pose["rotation"])
        transform.translate(-BODY_CENTER.x(), -BODY_CENTER.y())
        return transform

    # paper geometry --------------------------------------------------------
    @staticmethod
    def paper_base(pose):
        blanket = _clamp(pose["blanket"])
        return [QPointF(x1 + (x2 - x1) * blanket, y1 + (y2 - y1) * blanket + pose["paper_dy"])
                for (x1, y1), (x2, y2) in zip(PAPER_QUAD, BLANKET_QUAD)]

    @staticmethod
    def paper_is_flat(pose):
        return (abs(pose["paper_fold1"]) < 1e-3 and abs(pose["paper_fold2"]) < 1e-3
                and abs(pose["paper_wave"]) < 1e-3 and abs(pose["paper_curl"]) < 1e-3
                and abs(pose["paper_roll"]) < 1e-3)

    @staticmethod
    def _deform(u, v, pose):
        """Bend a point of the paper.

        (u, v) is a position on the flat sheet (0..1 from the top-left corner).
        Returns the moved (u, v) plus how far that point is lifted off the table.
        """
        height = 0.0
        roll = pose["paper_roll"]
        if roll > 0:
            u = 1.0 - (1.0 - u) * (1.0 - _clamp(roll, 0.0, 0.97))
        fold_1 = pose["paper_fold1"]
        if fold_1 > 0 and u > 0.5:
            fold_angle = math.pi * _clamp(fold_1, 0.0, 0.995)
            distance = u - 0.5
            u = 0.5 + distance * math.cos(fold_angle)
            height += distance * math.sin(fold_angle) * 110.0
        fold_2 = pose["paper_fold2"]
        if fold_2 > 0 and v < 0.5:
            fold_angle = math.pi * _clamp(fold_2, 0.0, 0.995)
            distance = 0.5 - v
            v = 0.5 - distance * math.cos(fold_angle)
            height += distance * math.sin(fold_angle) * 45.0
        wave = pose["paper_wave"]
        if wave:
            height += wave * 9.0 * math.sin(2 * math.pi * (1.4 * u + 0.4 * v - pose["phase"] * 1.6)) * (0.3 + 0.7 * (1 - u))
        curl = pose["paper_curl"]
        if curl:
            corner = _clamp((u - 0.55) / 0.45) * _clamp((0.45 - v) / 0.45)
            height += curl * 34.0 * corner * corner
        return u, v, height

    def paper_mapper(self, pose):
        """Returns f(u, v, with_height=True) -> screen QPointF."""
        base = self.paper_base(pose)
        lift = pose["paper_lift"]
        rot = pose["paper_rot"]
        center = _bilinear(base, 0.5, 0.5)
        center = QPointF(center.x(), center.y() - lift)
        offset = pose["paper_dx"]

        def f(u, v, with_height=True):
            u2, v2, h = self._deform(u, v, pose)
            point = _bilinear(base, u2, v2)
            if with_height:
                point = QPointF(point.x(), point.y() - h - lift)
            if rot:
                point = _rotate_about(point, center, rot)
            return QPointF(point.x() + offset, point.y())
        return f

    def shape(self, pose):
        """Logical-space silhouette of everything currently drawn."""
        path = QPainterPath()
        path.setFillRule(Qt.FillRule.WindingFill)
        if pose["alpha"] <= 0.01:
            return path
        if pose["paper_alpha"] > 0.01:
            to_screen = self.paper_mapper(pose)
            columns, rows = (1, 1) if self.paper_is_flat(pose) else (6, 3)
            for j in range(rows):
                for i in range(columns):
                    u0, u1, v0, v1 = i / columns, (i + 1) / columns, j / rows, (j + 1) / rows
                    poly = QPolygonF([to_screen(u0, v0), to_screen(u1, v0), to_screen(u1, v1), to_screen(u0, v1)])
                    path.addPolygon(poly)
                    path.closeSubpath()
                    path.addPolygon(poly.translated(3, 4))
                    path.closeSubpath()
            if pose["paper_roll"] > 0.05:
                p0, p1 = to_screen(0, 0), to_screen(0, 1)
                path.addRect(QRectF(p0, p1).normalized().adjusted(-14, -10, 14, 10))
        body_xf = self.body_transform(pose)
        body = QPainterPath()
        body.setFillRule(Qt.FillRule.WindingFill)
        if pose["morph"] > 1e-3:
            body.addRect(QRectF(46, 56, 112, 136))
        else:
            body.addEllipse(BODY_CENTER, RING_R + 7, RING_R + 7)
            stroker = QPainterPathStroker()
            stroker.setWidth(16.0)
            stroker.setCapStyle(Qt.PenCapStyle.RoundCap)
            body.addPath(stroker.createStroke(self.tail_path(pose["tail_rot"])))
        eye_size = max(1.0, pose["eye_scale"])
        brow = max(0.0, pose["brow_l"], pose["brow_r"])
        top = EYE_L.y() - 20.0 * eye_size - brow * 6.0 - 14.0
        body.addRect(QRectF(EYE_L.x() - 26, top, EYE_R.x() - EYE_L.x() + 52, EYE_L.y() + 17 * eye_size + 4 - top))
        path.addPath(body_xf.map(body))
        for name, rect in _BODY_EXTRA_BOUNDS.items():
            if pose[name] > 0.01:
                extra_rect = QPainterPath()
                extra_rect.addRect(rect)
                path.addPath(body_xf.map(extra_rect))
        if pose["glasses"] > 0.01:
            extra_rect = QPainterPath()
            extra_rect.addRect(QRectF(58, 56, 86, 52))
            path.addPath(body_xf.map(extra_rect))
        for name, rect in _WORLD_EXTRA_BOUNDS.items():
            if pose[name] > 0.01:
                path.addRect(rect)
        if pose["mag"] > 0.01:
            path.addRect(QRectF(pose["mag_x"] - 22, pose["mag_y"] - 22, 58, 58))
        if pose["plane"] > 0.01:
            path.addRect(QRectF(pose["plane_x"] - 22, pose["plane_y"] - 22, 44, 44))
        if pose["pin"] > 0.01 or pose["pins_n"] > 0.01:
            # pins can drop anywhere on the map
            path.addRect(QRectF(0, 40, 200, 200))
        return path

    # ------------------------------------------------------------- drawing
    def paint(self, painter, pose):
        painter.save()
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        painter.setOpacity(_clamp(pose["alpha"]))
        blanket = pose["blanket"] > 0.5
        if not blanket:
            self._paper(painter, pose)
            if pose["route"] > 0.01:
                self._route(painter, pose)
        self._shadow(painter, pose)

        painter.save()
        painter.setTransform(self.body_transform(pose), True)
        self._wire(painter, pose)
        self._face(painter, pose)
        self._body_extras(painter, pose)
        painter.restore()

        if blanket:
            self._paper(painter, pose)
        else:
            if pose["pin"] > 0.01:
                self._pin(painter, pose, pose["pin_lon"], pose["pin_lat"], pose["pin_drop"], pose["pin"])
            if pose["pins_n"] > 0.01:
                self._pins(painter, pose)
        self._world_extras(painter, pose)
        painter.restore()

    # paper ---------------------------------------------------------------
    def _paper(self, painter, pose):
        alpha = _clamp(pose["paper_alpha"])
        if alpha <= 0.01:
            return
        painter.save()
        painter.setOpacity(painter.opacity() * alpha)
        to_screen = self.paper_mapper(pose)
        if self.paper_is_flat(pose):
            self._paper_flat(painter, pose, to_screen)
        else:
            self._paper_mesh(painter, pose, to_screen)
        painter.restore()

    TEX_SCALE = 2.0  # texture pixels per degree

    def _map_texture(self):
        texture = getattr(self, "_tex", None)
        if texture is not None:
            return texture
        pixels_per_degree = self.TEX_SCALE
        texture = QImage(int(360 * pixels_per_degree), int(180 * pixels_per_degree), QImage.Format.Format_ARGB32_Premultiplied)
        texture.fill(QColor("#cfe5f2"))
        painter = QPainter(texture)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        transform = QTransform()
        transform.scale(pixels_per_degree, -pixels_per_degree)
        transform.translate(180.0, -90.0)
        painter.setTransform(transform)
        grat = QPen(QColor(120, 165, 195, 150), 1.2)
        grat.setCosmetic(True)
        painter.setPen(grat)
        for alpha, b in self._graticule:
            painter.drawLine(alpha, b)
        land_pen = QPen(QColor("#5f8a4f"), 1.4)
        land_pen.setCosmetic(True)
        painter.setPen(land_pen)
        painter.setBrush(QColor("#a3cb8c"))
        for poly in self._land:
            painter.drawPolygon(poly)
        painter.end()
        self._tex = texture
        return texture

    def _draw_map(self, painter, lon0, lat0, lon1, lat1, quad):
        """Draw the lon/lat box of the map texture into a screen quad."""
        pixels_per_degree = self.TEX_SCALE
        source = QRectF((lon0 + 180.0) * pixels_per_degree, (90.0 - lat0) * pixels_per_degree, (lon1 - lon0) * pixels_per_degree, (lat0 - lat1) * pixels_per_degree)
        if source.width() <= 0.01 or source.height() <= 0.01:
            return
        transform = QTransform()
        poly = QPolygonF([source.topLeft(), source.topRight(), source.bottomRight(), source.bottomLeft()])
        if not QTransform.quadToQuad(poly, quad, transform):
            return
        painter.save()
        painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform, True)
        painter.setTransform(transform, True)
        painter.drawImage(source, self._map_texture(), source)
        painter.restore()

    def _paper_shadow(self, painter, pose, polys):
        if pose["blanket"] > 0.5:
            return
        lift = _clamp(pose["paper_lift"] / 40.0)
        alpha = int(45 * (1.0 - lift))
        if alpha <= 2:
            return
        shadow_path = QPainterPath()
        shadow_path.setFillRule(Qt.FillRule.WindingFill)
        for poly in polys:
            shadow_path.addPolygon(poly.translated(3, 4))
            shadow_path.closeSubpath()
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QColor(0, 0, 0, alpha))
        painter.drawPath(shadow_path)

    def _paper_flat(self, painter, pose, to_screen):
        top_left, top_right, bottom_right, bottom_left = to_screen(0, 0), to_screen(1, 0), to_screen(1, 1), to_screen(0, 1)
        dog_ear = 10.0

        def along(alpha, b, d):
            dx, dy = b.x() - alpha.x(), b.y() - alpha.y()
            length = math.hypot(dx, dy) or 1.0
            return QPointF(alpha.x() + dx / length * d, alpha.y() + dy / length * d)

        fold_a = along(top_right, top_left, dog_ear)
        fold_b = along(top_right, bottom_right, dog_ear * 0.9)
        sheet = QPolygonF([top_left, fold_a, fold_b, bottom_right, bottom_left])
        self._paper_shadow(painter, pose, [QPolygonF([to_screen(0, 0, False), to_screen(1, 0, False), to_screen(1, 1, False), to_screen(0, 1, False)])])

        grad = QLinearGradient(top_left, bottom_right)
        grad.setColorAt(0.0, QColor("#fffdf6"))
        grad.setColorAt(1.0, QColor("#ece5d3"))
        painter.setBrush(QBrush(grad))
        painter.setPen(QPen(QColor("#a9a28f"), 1.0))
        painter.drawPolygon(sheet)

        inset = QPolygonF([to_screen(MAP_U[0], MAP_V[0]), to_screen(MAP_U[1], MAP_V[0]), to_screen(MAP_U[1], MAP_V[1]),
                           to_screen(MAP_U[0], MAP_V[1])])
        self._draw_map(painter, -180.0, 90.0, 180.0, -90.0, inset)
        painter.setPen(QPen(QColor("#6f7f8c"), 0.9))
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawPolygon(inset)

        # dog-ear
        dx, dy = fold_b.x() - fold_a.x(), fold_b.y() - fold_a.y()
        length = math.hypot(dx, dy) or 1.0
        normal_x, normal_y = -dy / length, dx / length
        mid = QPointF((fold_a.x() + fold_b.x()) / 2, (fold_a.y() + fold_b.y()) / 2)
        dist = math.hypot(top_right.x() - mid.x(), top_right.y() - mid.y())
        tip = QPointF(mid.x() + normal_x * dist * 0.95, mid.y() + normal_y * dist * 0.95)
        if (tip.x() - mid.x()) * (top_right.x() - mid.x()) + (tip.y() - mid.y()) * (top_right.y() - mid.y()) > 0:
            tip = QPointF(mid.x() - normal_x * dist * 0.95, mid.y() - normal_y * dist * 0.95)
        painter.setPen(QPen(QColor("#a9a28f"), 0.9))
        gradient = QLinearGradient(mid, tip)
        gradient.setColorAt(0.0, QColor("#ddd4bd"))
        gradient.setColorAt(1.0, QColor("#fbf7ea"))
        painter.setBrush(QBrush(gradient))
        painter.drawPolygon(QPolygonF([fold_a, fold_b, tip]))

    def _paper_mesh(self, painter, pose, to_screen):
        columns, rows = 8, 4
        points = [[to_screen(col / columns, row / rows) for col in range(columns + 1)] for row in range(rows + 1)]
        heights = [[self._deform(col / columns, row / rows, pose)[2] for col in range(columns + 1)] for row in range(rows + 1)]
        floor = [[to_screen(col / columns, row / rows, False) for col in range(columns + 1)] for row in range(rows + 1)]
        reference_area = _area(self.paper_base(pose))
        cells = []
        shadows = []
        for row in range(rows):
            for col in range(columns):
                quad = [points[row][col], points[row][col + 1], points[row + 1][col + 1], points[row + 1][col]]
                height = (heights[row][col] + heights[row][col + 1] + heights[row + 1][col + 1] + heights[row + 1][col]) / 4.0
                cells.append((height, col, row, quad))
                shadows.append(QPolygonF([floor[row][col], floor[row][col + 1], floor[row + 1][col + 1], floor[row + 1][col]]))
        self._paper_shadow(painter, pose, shadows)
        cells.sort(key=lambda center: center[0])
        edge_pen = QPen(QColor("#a9a28f"), 1.0)
        for height, col, row, quad in cells:
            area = _area(quad)
            if abs(area) < 0.3:
                continue
            front = (area > 0) == (reference_area > 0)
            poly = QPolygonF(quad)
            fill = QColor("#fbf8ee") if front else QColor("#e6ddc6")
            if front and height > 2:
                fill = QColor("#fffdf6")
            painter.setPen(QPen(fill, 0.8))
            painter.setBrush(fill)
            painter.drawPolygon(poly)
            if front:
                u0, u1, v0, v1 = col / columns, (col + 1) / columns, row / rows, (row + 1) / rows
                map_u0, map_u1 = max(u0, MAP_U[0]), min(u1, MAP_U[1])
                map_v0, map_v1 = max(v0, MAP_V[0]), min(v1, MAP_V[1])
                if map_u1 > map_u0 and map_v1 > map_v0:
                    sub = QPolygonF([to_screen(map_u0, map_v0), to_screen(map_u1, map_v0), to_screen(map_u1, map_v1), to_screen(map_u0, map_v1)])
                    lon0 = -180.0 + (map_u0 - MAP_U[0]) / (MAP_U[1] - MAP_U[0]) * 360.0
                    lon1 = -180.0 + (map_u1 - MAP_U[0]) / (MAP_U[1] - MAP_U[0]) * 360.0
                    lat0 = 90.0 - (map_v0 - MAP_V[0]) / (MAP_V[1] - MAP_V[0]) * 180.0
                    lat1 = 90.0 - (map_v1 - MAP_V[0]) / (MAP_V[1] - MAP_V[0]) * 180.0
                    self._draw_map(painter, lon0, lat0, lon1, lat1, sub)
            painter.setPen(edge_pen)
            if col == 0:
                painter.drawLine(quad[0], quad[3])
            if col == columns - 1:
                painter.drawLine(quad[1], quad[2])
            if row == 0:
                painter.drawLine(quad[0], quad[1])
            if row == rows - 1:
                painter.drawLine(quad[3], quad[2])
        roll = pose["paper_roll"]
        if roll > 0.05:
            # the rolled-up part forms a scroll along the left edge
            scroll_start, scroll_end = points[0][0], points[rows][0]
            scroll_width = 4.0 + 14.0 * roll
            painter.setPen(QPen(QColor("#a9a28f"), scroll_width + 2.0, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap))
            painter.drawLine(scroll_start, scroll_end)
            painter.setPen(QPen(QColor("#f4eedd"), scroll_width, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap))
            painter.drawLine(scroll_start, scroll_end)
            painter.setPen(QPen(QColor(163, 203, 140, 200), scroll_width * 0.35, Qt.PenStyle.SolidLine, Qt.PenCapStyle.FlatCap))
            painter.drawLine(_lerp(scroll_start, scroll_end, 0.15), _lerp(scroll_start, scroll_end, 0.85))

    def _shadow(self, painter, pose):
        lift = _clamp(-pose["offset_y"] / 70.0)
        width = 36.0 * pose["scale_x"] * (1.0 - 0.45 * lift)
        height = 6.5 * (1.0 - 0.4 * lift)
        center_x = 104.0 + pose["offset_x"] * 0.6
        gradient = QRadialGradient(QPointF(center_x, 183.0), width)
        gradient.setColorAt(0.0, QColor(0, 0, 0, int(80 * (1.0 - 0.6 * lift))))
        gradient.setColorAt(1.0, QColor(0, 0, 0, 0))
        painter.save()
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QBrush(gradient))
        painter.translate(center_x, 183.0)
        painter.scale(1.0, height / width)
        painter.drawEllipse(QPointF(0, 0), width, width)
        painter.restore()

    # body ----------------------------------------------------------------
    def _ring_brush(self):
        gradient = QLinearGradient(QPointF(60, 50), QPointF(160, 190))
        for stop, color in self.palette.ring:
            gradient.setColorAt(stop, color)
        return QBrush(gradient)

    def _tail_brush(self, alpha, end):
        gradient = QLinearGradient(alpha, end)
        for stop, color in self.palette.tail:
            gradient.setColorAt(stop, color)
        return QBrush(gradient)

    def _strand(self, painter, path, brush, outline=True):
        cap, join = Qt.PenCapStyle.RoundCap, Qt.PenJoinStyle.RoundJoin
        wire_width = self.WIRE_W
        painter.setBrush(Qt.BrushStyle.NoBrush)
        if outline:
            painter.setPen(QPen(self.palette.outline, wire_width + 2.6, Qt.PenStyle.SolidLine, cap, join))
            painter.drawPath(path)
        painter.setPen(QPen(brush, wire_width, Qt.PenStyle.SolidLine, cap, join))
        painter.drawPath(path)
        painter.setPen(QPen(QColor(255, 255, 255, 200), 1.3, Qt.PenStyle.SolidLine, cap, join))
        painter.drawPath(path.translated(-0.9, -1.0))

    def _cast_shadow(self, painter, front, clip):
        painter.save()
        painter.setClipPath(clip, Qt.ClipOperation.IntersectClip)
        for width, opacity in ((13, 22), (10, 32), (7, 42)):
            painter.setPen(QPen(QColor(10, 25, 10, opacity), width, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap))
            painter.drawPath(front.translated(2.2, 3.2))
        painter.restore()

    def _wire(self, painter, pose):
        morph = self.morph_points(pose)
        if morph is not None:
            path = QPainterPath(morph[0])
            for point in morph[1:]:
                path.lineTo(point)
            self._strand(painter, path, self._ring_brush())
            return
        if abs(pose["tail_rot"]) < 0.05:
            # the resting Q is drawn once into a supersampled image and reused
            img = self._q_image()
            painter.save()
            painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform, True)
            painter.drawImage(self.Q_BOX, img, QRectF(img.rect()))
            painter.restore()
        else:
            self._draw_q(painter, pose["tail_rot"])

    Q_BOX = QRectF(30.0, 52.0, 156.0, 160.0)
    Q_SS = 3.0

    def _q_image(self):
        key = self.palette.tint
        cache = getattr(self, "_q_img", None)
        if cache is not None and cache[0] == key:
            return cache[1]
        box, supersample = self.Q_BOX, self.Q_SS
        img = QImage(int(box.width() * supersample), int(box.height() * supersample), QImage.Format.Format_ARGB32_Premultiplied)
        img.fill(0)
        image_painter = QPainter(img)
        image_painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        image_painter.scale(supersample, supersample)
        image_painter.translate(-box.x(), -box.y())
        self._draw_q(image_painter, 0.0)
        image_painter.end()
        self._q_img = (key, img)
        return img

    def _q_static(self):
        geometry = getattr(self, "_qs", None)
        if geometry is not None:
            return geometry
        ring = self.ring_path()
        length = ring.length()
        geometry = {"hair": _sub_path(ring, ring.percentAtLength(length - 64), 1.0, 40),
             "warm": _sub_path(ring, ring.percentAtLength(length - 16), 1.0, 20)}
        stroker = QPainterPathStroker()
        stroker.setWidth(self.WIRE_W + 3.0)
        geometry["hair_clip"] = stroker.createStroke(geometry["hair"])
        if self._crossing is not None:
            spiral_percent, crossing_point = self._crossing
            geometry["front"] = _sub_path(ring, max(0.0, spiral_percent - 0.03), min(1.0, spiral_percent + 0.03), 20)
            geometry["front_wide"] = _sub_path(ring, max(0.0, spiral_percent - 0.04), min(1.0, spiral_percent + 0.04), 24)
            clip = QPainterPath()
            clip.addEllipse(crossing_point, 11, 11)
            geometry["cross_clip"] = clip
        self._qs = geometry
        return geometry

    def _draw_q(self, painter, tail_rot):
        """Knot-style drawing: one continuous stroke, then the front strands
        are redrawn where wires cross, with soft shadows on what's behind."""
        cap, join = Qt.PenCapStyle.RoundCap, Qt.PenJoinStyle.RoundJoin
        wire_width = self.WIRE_W
        palette = self.palette
        ring = self.ring_path()
        tail = self.tail_path(tail_rot)
        tip = tail.pointAtPercent(1.0)
        full = QPainterPath(ring)
        full.connectPath(tail)
        ring_brush = self._ring_brush()

        # 1. whole wire as one stroke (no seams)
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.setPen(QPen(palette.outline, wire_width + 2.6, Qt.PenStyle.SolidLine, cap, join))
        painter.drawPath(full)
        painter.setPen(QPen(ring_brush, wire_width, Qt.PenStyle.SolidLine, cap, join))
        painter.drawPath(ring)
        painter.setPen(QPen(self._tail_brush(TAIL_A, tip), wire_width, Qt.PenStyle.SolidLine, Qt.PenCapStyle.FlatCap, join))
        painter.drawPath(tail)
        painter.setPen(QPen(QColor(255, 255, 255, 200), 1.3, Qt.PenStyle.SolidLine, cap, join))
        painter.drawPath(full.translated(-0.9, -1.0))

        # 2. the hairpin (back) is shaded; colour warms towards the bend
        geometry = self._q_static()
        shade = QLinearGradient(geometry["hair"].pointAtPercent(0), geometry["hair"].pointAtPercent(1))
        shade.setColorAt(0.0, QColor(15, 35, 10, 0))
        shade.setColorAt(0.35, QColor(15, 35, 10, 80))
        shade.setColorAt(1.0, QColor(15, 35, 10, 105))
        painter.setPen(QPen(QBrush(shade), wire_width, Qt.PenStyle.SolidLine, Qt.PenCapStyle.FlatCap, join))
        painter.drawPath(geometry["hair"])
        if palette.warm is not None:
            gradient = QLinearGradient(geometry["warm"].pointAtPercent(0), TAIL_A)
            transparent = QColor(palette.warm)
            transparent.setAlpha(0)
            gradient.setColorAt(0.0, transparent)
            gradient.setColorAt(1.0, palette.warm)
            painter.setPen(QPen(QBrush(gradient), wire_width, Qt.PenStyle.SolidLine, Qt.PenCapStyle.FlatCap, join))
            painter.drawPath(geometry["warm"])

        # 3. the spiral passes over the hairpin
        if self._crossing is not None:
            self._cast_shadow(painter, geometry["front"], geometry["hair_clip"])
            painter.save()
            painter.setClipPath(geometry["cross_clip"], Qt.ClipOperation.IntersectClip)
            self._strand(painter, geometry["front_wide"], ring_brush)
            painter.restore()

        # 4. the tail passes in front of the spiral
        self._cast_shadow(painter, tail, self._ring_clip)
        outline_color = palette.outline
        outline_gradient = QLinearGradient(TAIL_A, tip)
        outline_gradient.setColorAt(0.0, QColor(outline_color.red(), outline_color.green(), outline_color.blue(), 0))
        outline_gradient.setColorAt(0.12, QColor(outline_color.red(), outline_color.green(), outline_color.blue(), 0))
        outline_gradient.setColorAt(0.22, outline_color)
        painter.setPen(QPen(QBrush(outline_gradient), wire_width + 2.6, Qt.PenStyle.SolidLine, cap, join))
        painter.drawPath(tail)
        painter.setPen(QPen(self._tail_brush(TAIL_A, tip), wire_width, Qt.PenStyle.SolidLine, cap, join))
        painter.drawPath(tail)
        painter.setPen(QPen(QColor(255, 255, 255, 200), 1.3, Qt.PenStyle.SolidLine, cap, join))
        painter.drawPath(tail.translated(-0.9, -1.0))

    def _face(self, painter, pose):
        self._eye(painter, EYE_L, pose, -1)
        self._eye(painter, EYE_R, pose, 1)
        eye_size = pose["eye_scale"]
        self._brow(painter, EYE_L, pose["brow_l"], pose["brow_tilt"], -1, eye_size)
        self._brow(painter, EYE_R, pose["brow_r"], pose["brow_tilt"], 1, eye_size)
        if pose["blush"] > 0.01:
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(QColor(255, 120, 140, int(120 * _clamp(pose["blush"]))))
            painter.drawEllipse(QPointF(EYE_L.x() - 6, EYE_L.y() + 20), 8, 4)
            painter.drawEllipse(QPointF(EYE_R.x() + 6, EYE_R.y() + 20), 8, 4)
        if pose["glasses"] > 0.01:
            self._glasses(painter, pose)
        if pose["telescope"] > 0.01:
            self._telescope(painter, pose)

    def _eye(self, painter, center, pose, side):
        eye_size = pose["eye_scale"]
        radius_x, radius_y = 12.5 * eye_size, 14.5 * eye_size
        rect = QRectF(center.x() - radius_x, center.y() - radius_y, 2 * radius_x, 2 * radius_y)
        if pose["happy"] > 0.5:
            path = QPainterPath(QPointF(center.x() - 11, center.y() + 7))
            path.quadTo(QPointF(center.x(), center.y() - 15), QPointF(center.x() + 11, center.y() + 7))
            painter.setBrush(QColor(255, 255, 255, 235))
            painter.setPen(QPen(QColor(255, 255, 255, 220), 7.5, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap))
            painter.drawPath(path)
            painter.setPen(QPen(INK, 4.6, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap))
            painter.drawPath(path)
            return

        eye_shape = QPainterPath()
        eye_shape.addEllipse(rect)
        painter.setPen(Qt.PenStyle.NoPen)
        gradient = QRadialGradient(QPointF(center.x() - 3, center.y() - 4), radius_y * 1.2)
        gradient.setColorAt(0.0, QColor("#ffffff"))
        gradient.setColorAt(1.0, QColor("#e4e7ea"))
        painter.setBrush(QBrush(gradient))
        painter.drawPath(eye_shape)

        painter.save()
        painter.setClipPath(eye_shape, Qt.ClipOperation.IntersectClip)
        look_x = pose["look_x"] or 0.0
        look_y = pose["look_y"] or 0.0
        pupil_center = QPointF(center.x() + look_x * (radius_x - 6.0), center.y() + look_y * (radius_y - 6.5))
        if pose["x_eyes"] > 0.5:
            painter.setPen(QPen(INK, 3.0, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap))
            cross_size = 6.0 * eye_size
            painter.drawLine(QPointF(center.x() - cross_size, center.y() - cross_size), QPointF(center.x() + cross_size, center.y() + cross_size))
            painter.drawLine(QPointF(center.x() - cross_size, center.y() + cross_size), QPointF(center.x() + cross_size, center.y() - cross_size))
            painter.setPen(Qt.PenStyle.NoPen)
        elif pose["spiral"] > 0.5:
            self._spiral(painter, center, pose["phase"] * (8.0 if side > 0 else -8.0))
        else:
            pupil_radius = 5.4 * pose["pupil_scale"] * eye_size
            painter.setBrush(INK)
            painter.drawEllipse(pupil_center, pupil_radius, pupil_radius)
            painter.setBrush(QColor(255, 255, 255, 230))
            painter.drawEllipse(QPointF(pupil_center.x() - pupil_radius * 0.35, pupil_center.y() - pupil_radius * 0.4), pupil_radius * 0.32, pupil_radius * 0.32)
        lid = _clamp(pose["lid"])
        squint = _clamp(pose["squint"])
        lid_col = QColor("#d9dcdf")
        if lid > 0.01:
            lid_height = 2 * radius_y * lid
            painter.setBrush(lid_col)
            painter.drawRect(QRectF(rect.left() - 1, rect.top() - 1, rect.width() + 2, lid_height + 1))
            painter.setPen(QPen(INK, 1.6))
            painter.drawLine(QPointF(rect.left(), rect.top() + lid_height), QPointF(rect.right(), rect.top() + lid_height))
            painter.setPen(Qt.PenStyle.NoPen)
        if squint > 0.01:
            lid_height = 2 * radius_y * squint * 0.5
            painter.setBrush(lid_col)
            painter.drawRect(QRectF(rect.left() - 1, rect.bottom() - lid_height, rect.width() + 2, lid_height + 1))
            painter.setPen(QPen(INK, 1.4))
            painter.drawLine(QPointF(rect.left(), rect.bottom() - lid_height), QPointF(rect.right(), rect.bottom() - lid_height))
            painter.setPen(Qt.PenStyle.NoPen)
        painter.restore()
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.setPen(QPen(INK, 1.8))
        painter.drawEllipse(rect)
        if lid > 0.95:
            painter.setPen(QPen(INK, 2.4, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap))
            path = QPainterPath(QPointF(center.x() - 10, center.y() + 2))
            path.quadTo(QPointF(center.x(), center.y() + 9), QPointF(center.x() + 10, center.y() + 2))
            painter.drawPath(path)

    @staticmethod
    def _spiral(painter, center, rot):
        path = QPainterPath()
        for i in range(60):
            alpha = math.radians(rot * 20 + i * 18)
            radius = 0.3 + i * 0.17
            point = QPointF(center.x() + radius * math.cos(alpha), center.y() + radius * math.sin(alpha))
            if i == 0:
                path.moveTo(point)
            else:
                path.lineTo(point)
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.setPen(QPen(INK, 1.6))
        painter.drawPath(path)
        painter.setPen(Qt.PenStyle.NoPen)

    @staticmethod
    def _brow(painter, center, raise_, tilt, side, eye_size):
        y = center.y() - 20.0 * eye_size - raise_ * 6.0
        inner_x = center.x() - side * 9.0
        outer_x = center.x() + side * 13.0
        inner_y = y + tilt * 5.0
        outer_y = y - tilt * 3.0
        path = QPainterPath(QPointF(outer_x, outer_y + 2))
        path.quadTo(QPointF((inner_x + outer_x) / 2, min(inner_y, outer_y) - 5.0), QPointF(inner_x, inner_y))
        painter.setBrush(Qt.BrushStyle.NoBrush)
        # thin white halo keeps the brows readable on dark backgrounds
        painter.setPen(QPen(QColor(255, 255, 255, 225), 7.6, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap))
        painter.drawPath(path)
        painter.setPen(QPen(INK, 5.0, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap))
        painter.drawPath(path)

    @staticmethod
    def _glasses(painter, pose):
        alpha = _clamp(pose["glasses"])
        drop = (1.0 - alpha) * -30.0
        painter.save()
        painter.translate(0, drop)
        painter.setOpacity(painter.opacity() * alpha)
        painter.setPen(QPen(QColor("#1e1e1e"), 2.4))
        painter.setBrush(QColor(170, 210, 255, 50))
        painter.drawEllipse(EYE_L, 15, 15)
        painter.drawEllipse(EYE_R, 15, 15)
        painter.setBrush(Qt.BrushStyle.NoBrush)
        bridge = QPainterPath(QPointF(EYE_L.x() + 15, EYE_L.y() - 2))
        bridge.quadTo(QPointF((EYE_L.x() + EYE_R.x()) / 2, EYE_L.y() - 8), QPointF(EYE_R.x() - 15, EYE_R.y() - 2))
        painter.drawPath(bridge)
        painter.drawLine(QPointF(EYE_L.x() - 15, EYE_L.y() - 3), QPointF(EYE_L.x() - 22, EYE_L.y() - 6))
        painter.drawLine(QPointF(EYE_R.x() + 15, EYE_R.y() - 3), QPointF(EYE_R.x() + 22, EYE_R.y() - 6))
        painter.restore()

    @staticmethod
    def _telescope(painter, pose):
        """The rolled-up map held up to the right eye."""
        alpha = _clamp(pose["telescope"])
        painter.save()
        painter.setOpacity(painter.opacity() * alpha)
        painter.translate(EYE_R.x() + 4, EYE_R.y())
        painter.rotate(pose["telescope_ang"])
        painter.scale(0.6 + 0.4 * alpha, 0.6 + 0.4 * alpha)
        body = QRectF(6, -9, 62, 18)
        gradient = QLinearGradient(QPointF(0, -9), QPointF(0, 9))
        gradient.setColorAt(0.0, QColor("#fffdf6"))
        gradient.setColorAt(0.5, QColor("#efe7d2"))
        gradient.setColorAt(1.0, QColor("#cfc5ab"))
        painter.setPen(QPen(QColor("#8f8670"), 1.0))
        painter.setBrush(QBrush(gradient))
        painter.drawRoundedRect(body, 3, 3)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QColor(163, 203, 140, 210))
        for x in (16, 34, 52):
            painter.drawRect(QRectF(x, -9, 6, 18))
        painter.setPen(QPen(QColor("#8f8670"), 1.0))
        painter.setBrush(QColor("#3a4a5a"))
        painter.drawEllipse(QPointF(68, 0), 3.5, 9)
        painter.setBrush(QColor("#f4eedd"))
        painter.drawEllipse(QPointF(6, 0), 3.5, 9)
        painter.restore()

    # body-attached extras --------------------------------------------------
    def _body_extras(self, painter, pose):
        phase = pose["phase"]
        if pose["bulb"] > 0.01:
            self._bulb(painter, pose["bulb"], phase)
        if pose["exclaim"] > 0.01:
            self._glyph(painter, "!", QPointF(154, 46), QColor("#d62828"), pose["exclaim"], 34)
        if pose["question"] > 0.01:
            bob = math.sin(phase * 3.0) * 2.5
            self._glyph(painter, "?", QPointF(154, 46 + bob), QColor("#1f6fd1"), pose["question"], 34)
        if pose["sweat"] > 0.01:
            self._sweat(painter, pose["sweat"], phase)
        if pose["tears"] > 0.01:
            self._tears(painter, pose["tears"], phase)
        if pose["zzz"] > 0.01:
            self._zzz(painter, pose["zzz"], phase)
        if pose["steam"] > 0.01:
            self._steam(painter, pose["steam"], phase)
        if pose["hat"] > 0.01:
            self._hat(painter, pose["hat"])
        if pose["stars"] > 0.01:
            self._orbit_stars(painter, pose["stars"], phase)

    @staticmethod
    def _glyph(painter, text, pos, color, alpha, size):
        alpha = _clamp(alpha)
        font = QFont()
        font.setBold(True)
        font.setPixelSize(int(size * (0.6 + 0.4 * alpha)))
        painter.save()
        painter.setOpacity(painter.opacity() * alpha)
        painter.setFont(font)
        path = QPainterPath()
        path.addText(QPointF(0, 0), font, text)
        bottom_right = path.boundingRect()
        path.translate(pos.x() - bottom_right.center().x(), pos.y() - bottom_right.center().y())
        painter.setPen(QPen(QColor("#ffffff"), 3.0))
        painter.setBrush(color)
        painter.drawPath(path)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.drawPath(path)
        painter.restore()

    @staticmethod
    def _bulb(painter, alpha, phase):
        alpha = _clamp(alpha)
        center = QPointF(100, 14)
        painter.save()
        painter.setOpacity(painter.opacity() * alpha)
        painter.translate(center)
        scale = 0.5 + 0.5 * alpha
        painter.scale(scale, scale)
        glow = QRadialGradient(QPointF(0, 0), 26)
        glow.setColorAt(0.0, QColor(255, 236, 120, 200))
        glow.setColorAt(1.0, QColor(255, 236, 120, 0))
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QBrush(glow))
        painter.drawEllipse(QPointF(0, 0), 26, 26)
        painter.setPen(QPen(QColor("#9a7b00"), 1.4))
        painter.setBrush(QColor("#ffe45c"))
        painter.drawEllipse(QPointF(0, -2), 11, 12)
        painter.setBrush(QColor("#9aa3ad"))
        painter.drawRect(QRectF(-6, 9, 12, 8))
        painter.setPen(QPen(QColor("#ffffff"), 1.6))
        painter.drawArc(QRectF(-7, -9, 9, 9), 90 * 16, 90 * 16)
        # rays
        painter.setPen(QPen(QColor(230, 180, 0, 200), 2.0, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap))
        pulse = 1.0 + 0.15 * math.sin(phase * 10)
        for i in range(7):
            ang = math.radians(-180 + i * 30)
            r1, r2 = 16 * pulse, 21 * pulse
            painter.drawLine(QPointF(r1 * math.cos(ang), r1 * math.sin(ang) - 2),
                       QPointF(r2 * math.cos(ang), r2 * math.sin(ang) - 2))
        painter.restore()

    @staticmethod
    def _drop(painter, center, size, color):
        path = QPainterPath(QPointF(center.x(), center.y() - size * 1.6))
        path.cubicTo(QPointF(center.x() + size * 0.3, center.y() - size * 0.8),
                     QPointF(center.x() + size, center.y() - size * 0.2), QPointF(center.x() + size, center.y() + size * 0.3))
        path.arcTo(QRectF(center.x() - size, center.y() - size * 0.7, 2 * size, 2 * size), 0, -180)
        path.cubicTo(QPointF(center.x() - size, center.y() - size * 0.2),
                     QPointF(center.x() - size * 0.3, center.y() - size * 0.8), QPointF(center.x(), center.y() - size * 1.6))
        painter.setPen(QPen(QColor("#2a6fb0"), 1.0))
        painter.setBrush(color)
        painter.drawPath(path)

    def _sweat(self, painter, alpha, phase):
        painter.save()
        painter.setOpacity(painter.opacity() * _clamp(alpha))
        y = 62 + (phase * 18.0) % 14.0
        self._drop(painter, QPointF(145, y), 4.5, QColor(140, 200, 255, 230))
        painter.restore()

    def _tears(self, painter, alpha, phase):
        painter.save()
        painter.setOpacity(painter.opacity() * _clamp(alpha))
        for i, (eye_x, offset) in enumerate(((EYE_L.x() - 4, 0.0), (EYE_R.x() + 4, 0.5))):
            fall = (phase * 0.9 + offset) % 1.0
            self._drop(painter, QPointF(eye_x, 106 + fall * 30), 3.2, QColor(140, 200, 255, int(230 * (1 - fall))))
        painter.restore()

    @staticmethod
    def _zzz(painter, alpha, phase):
        font = QFont()
        font.setBold(True)
        painter.save()
        painter.setPen(QColor("#4a5a8a"))
        for i in range(3):
            rise = (phase * 0.45 + i / 3.0) % 1.0
            size = 10 + 10 * rise
            font.setPixelSize(int(size))
            painter.setFont(font)
            painter.setOpacity(_clamp(alpha) * math.sin(math.pi * rise))
            painter.drawText(QPointF(134 + 34 * rise + 4 * math.sin(rise * 6), 66 - 56 * rise), "z")
        painter.restore()

    @staticmethod
    def _steam(painter, alpha, phase):
        painter.save()
        for side in (-1, 1):
            for i in range(2):
                rise = (phase * 1.2 + i * 0.5) % 1.0
                painter.setOpacity(_clamp(alpha) * (1.0 - rise) * 0.85)
                painter.setPen(QPen(QColor("#c9c9c9"), 1.0))
                painter.setBrush(QColor("#f2f2f2"))
                x = 100 + side * (38 + 10 * rise)
                y = 52 - 34 * rise
                radius = 5 + 6 * rise
                painter.drawEllipse(QPointF(x, y), radius, radius)
        painter.restore()

    @staticmethod
    def _hat(painter, alpha):
        alpha = _clamp(alpha)
        painter.save()
        painter.translate(0, 20 + (1 - alpha) * -40)
        painter.setOpacity(painter.opacity() * alpha)
        cone = QPolygonF([QPointF(84, 44), QPointF(120, 40), QPointF(108, 2)])
        gradient = QLinearGradient(QPointF(84, 44), QPointF(120, 2))
        gradient.setColorAt(0, QColor("#e63946"))
        gradient.setColorAt(1, QColor("#ffb703"))
        painter.setPen(QPen(QColor("#7a1d24"), 1.2))
        painter.setBrush(QBrush(gradient))
        painter.drawPolygon(cone)
        painter.setPen(QPen(QColor(255, 255, 255, 200), 2.0))
        painter.drawLine(QPointF(91, 33), QPointF(115, 30))
        painter.drawLine(QPointF(97, 21), QPointF(112, 19))
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QColor("#ffd60a"))
        painter.drawEllipse(QPointF(108, 2), 4.5, 4.5)
        painter.restore()

    @staticmethod
    def _star_path(center, radius, points=5, inner=0.45):
        path = QPainterPath()
        for i in range(points * 2):
            ang = math.radians(-90 + i * 180.0 / points)
            point_radius = radius if i % 2 == 0 else radius * inner
            point = QPointF(center.x() + point_radius * math.cos(ang), center.y() + point_radius * math.sin(ang))
            if i == 0:
                path.moveTo(point)
            else:
                path.lineTo(point)
        path.closeSubpath()
        return path

    def _orbit_stars(self, painter, alpha, phase):
        painter.save()
        painter.setOpacity(painter.opacity() * _clamp(alpha))
        painter.setPen(QPen(QColor("#8a6d00"), 0.8))
        painter.setBrush(QColor("#ffd60a"))
        for i in range(4):
            ang = phase * 4.0 + i * math.pi / 2
            center = QPointF(100 + 46 * math.cos(ang), 58 + 9 * math.sin(ang))
            painter.drawPath(self._star_path(center, 6))
        painter.restore()

    # world-space extras ----------------------------------------------------
    def _world_extras(self, painter, pose):
        phase = pose["phase"]
        if pose["mag"] > 0.01:
            self._magnifier(painter, pose)
        if pose["hearts"] > 0.01:
            self._hearts(painter, pose["hearts"], phase)
        if pose["notes"] > 0.01:
            self._notes(painter, pose["notes"], phase)
        if pose["sparkle"] > 0.01:
            self._sparkles(painter, pose["sparkle"], phase)
        if pose["confetti"] > 0.01:
            self._confetti(painter, pose["confetti"], phase)
        if pose["tap"] > 0.01:
            self._tap(painter, pose["tap"], phase)
        if pose["plane"] > 0.01:
            self._plane(painter, pose)

    def _pin_point(self, pose, lon, lat):
        to_screen = self.paper_mapper(pose)
        u, v = lonlat_to_uv(lon, lat)
        return to_screen(u, v)

    def _pin(self, painter, pose, lon, lat, drop, alpha):
        base = self._pin_point(pose, lon, lat)
        opacity = _clamp(alpha) * _clamp(pose["paper_alpha"])
        if opacity <= 0.01:
            return
        painter.save()
        painter.setOpacity(painter.opacity() * opacity)
        shadow_size = _clamp(1.0 - drop / 120.0)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QColor(0, 0, 0, int(70 * shadow_size)))
        painter.drawEllipse(base, 4 * shadow_size + 1, 1.6 * shadow_size + 0.5)
        painter.translate(base.x(), base.y() - drop)
        path = QPainterPath(QPointF(0, 0))
        path.cubicTo(QPointF(-3, -8), QPointF(-9, -12), QPointF(-9, -19))
        path.arcTo(QRectF(-9, -28, 18, 18), 180, -180)
        path.cubicTo(QPointF(9, -12), QPointF(3, -8), QPointF(0, 0))
        gradient = QLinearGradient(QPointF(-9, -28), QPointF(9, 0))
        gradient.setColorAt(0, QColor("#ff6b6b"))
        gradient.setColorAt(1, QColor("#b5121b"))
        painter.setPen(QPen(QColor("#6d0a10"), 1.0))
        painter.setBrush(QBrush(gradient))
        painter.drawPath(path)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QColor("#ffffff"))
        painter.drawEllipse(QPointF(0, -19), 3.6, 3.6)
        painter.restore()

    def _pins(self, painter, pose):
        from .animations import out_bounce
        count = pose["pins_n"]
        fade = _clamp(len(PIN_CITIES) + 1.5 - count)
        for index, (lon, lat) in enumerate(PIN_CITIES):
            if count <= index:
                break
            drop_progress = _clamp(count - index)
            drop = 110.0 * (1.0 - out_bounce(drop_progress))
            self._pin(painter, pose, lon, lat, drop, fade)

    def _route(self, painter, pose):
        to_screen = self.paper_mapper(pose)
        points = []
        for (lon_a, lat_a), (lon_b, lat_b) in zip(ROUTE, ROUTE[1:]):
            for step in range(8):
                fraction = step / 8.0
                points.append(to_screen(*lonlat_to_uv(lon_a + (lon_b - lon_a) * fraction, lat_a + (lat_b - lat_a) * fraction)))
        points.append(to_screen(*lonlat_to_uv(*ROUTE[-1])))
        drawn = max(2, int(round(len(points) * _clamp(pose["route"]))))
        path = QPainterPath(points[0])
        for point in points[1:drawn]:
            path.lineTo(point)
        painter.save()
        painter.setOpacity(painter.opacity() * _clamp(pose["paper_alpha"]))
        pen = QPen(QColor("#c1121f"), 1.8, Qt.PenStyle.DashLine, Qt.PenCapStyle.RoundCap)
        painter.setPen(pen)
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawPath(path)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QColor("#c1121f"))
        painter.drawEllipse(points[0], 2.2, 2.2)
        if pose["route"] > 0.97:
            end = points[-1]
            painter.setPen(QPen(QColor("#c1121f"), 2.4, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap))
            painter.drawLine(QPointF(end.x() - 4, end.y() - 4), QPointF(end.x() + 4, end.y() + 4))
            painter.drawLine(QPointF(end.x() - 4, end.y() + 4), QPointF(end.x() + 4, end.y() - 4))
        painter.restore()

    @staticmethod
    def _plane(painter, pose):
        alpha = _clamp(pose["plane"])
        painter.save()
        painter.setOpacity(painter.opacity() * alpha)
        painter.translate(pose["plane_x"], pose["plane_y"])
        painter.rotate(pose["plane_rot"])
        painter.scale(1.4, 1.4)
        painter.setPen(QPen(QColor("#8f8670"), 1.0))
        painter.setBrush(QColor("#fbf8ee"))
        painter.drawPolygon(QPolygonF([QPointF(18, 0), QPointF(-14, -11), QPointF(-7, 0)]))
        painter.setBrush(QColor("#e6ddc6"))
        painter.drawPolygon(QPolygonF([QPointF(18, 0), QPointF(-14, 9), QPointF(-7, 0)]))
        painter.setBrush(QColor(163, 203, 140, 220))
        painter.drawPolygon(QPolygonF([QPointF(4, -4), QPointF(-6, -8), QPointF(-4, -3)]))
        painter.restore()

    @staticmethod
    def _magnifier(painter, pose):
        alpha = _clamp(pose["mag"])
        center = QPointF(pose["mag_x"], pose["mag_y"])
        painter.save()
        painter.setOpacity(painter.opacity() * alpha)
        painter.setPen(QPen(QColor("#5a3d1e"), 6.0, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap))
        painter.drawLine(QPointF(center.x() + 11, center.y() + 11), QPointF(center.x() + 30, center.y() + 30))
        painter.setPen(QPen(QColor("#2f3338"), 3.2))
        painter.setBrush(QColor(200, 230, 255, 90))
        painter.drawEllipse(center, 15, 15)
        painter.setPen(QPen(QColor(255, 255, 255, 200), 2.0))
        painter.drawArc(QRectF(center.x() - 10, center.y() - 10, 20, 20), 100 * 16, 70 * 16)
        painter.restore()

    @staticmethod
    def _heart_path(center, size):
        path = QPainterPath(QPointF(center.x(), center.y() + size))
        path.cubicTo(QPointF(center.x() - size * 1.6, center.y() - size * 0.1), QPointF(center.x() - size * 0.8, center.y() - size * 1.3),
                     QPointF(center.x(), center.y() - size * 0.45))
        path.cubicTo(QPointF(center.x() + size * 0.8, center.y() - size * 1.3), QPointF(center.x() + size * 1.6, center.y() - size * 0.1),
                     QPointF(center.x(), center.y() + size))
        return path

    def _hearts(self, painter, alpha, phase):
        painter.save()
        painter.setPen(QPen(QColor("#9d0b2b"), 1.0))
        painter.setBrush(QColor("#ff4d6d"))
        for i, x in enumerate((40, 158, 70, 136)):
            rise = (phase * 0.55 + i * 0.27) % 1.0
            painter.setOpacity(_clamp(alpha) * math.sin(math.pi * rise))
            center = QPointF(x + 6 * math.sin(rise * 9 + i), 110 - 100 * rise)
            painter.drawPath(self._heart_path(center, 6 + 3 * rise))
        painter.restore()

    @staticmethod
    def _notes(painter, alpha, phase):
        font = QFont()
        font.setPixelSize(20)
        font.setBold(True)
        painter.save()
        painter.setFont(font)
        for i, (x, note, note_color) in enumerate(((28, "♪", "#7b2cbf"), (168, "♫", "#1d4ed8"),
                                          (52, "♫", "#0f766e"), (150, "♪", "#be123c"))):
            rise = (phase * 0.6 + i * 0.25) % 1.0
            painter.setOpacity(_clamp(alpha) * math.sin(math.pi * rise))
            painter.setPen(QColor(note_color))
            painter.drawText(QPointF(x + 8 * math.sin(rise * 7), 120 - 105 * rise), note)
        painter.restore()

    def _sparkles(self, painter, alpha, phase):
        painter.save()
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QColor("#ffe066"))
        spots = ((30, 50), (170, 40), (160, 120), (38, 130), (100, 12), (180, 160), (20, 90))
        for i, (x, y) in enumerate(spots):
            twinkle = 0.5 + 0.5 * math.sin(phase * 7 + i * 1.7)
            painter.setOpacity(_clamp(alpha) * twinkle)
            painter.drawPath(self._star_path(QPointF(x, y), 3 + 5 * twinkle, 4, 0.3))
        painter.restore()

    @staticmethod
    def _confetti(painter, alpha, phase):
        colors = ("#e63946", "#ffb703", "#2a9d8f", "#3a86ff", "#8338ec", "#fb5607")
        painter.save()
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setOpacity(_clamp(alpha))
        for i in range(26):
            seed = (i * 37) % 101 / 101.0
            x = 8 + (i * 61) % 184
            fall = (phase * (0.35 + 0.3 * seed) + seed) % 1.0
            y = -5 + fall * 190
            painter.save()
            painter.translate(x + 6 * math.sin(phase * 3 + i), y)
            painter.rotate(phase * 200 * (1 if i % 2 else -1) + i * 40)
            painter.setBrush(QColor(colors[i % len(colors)]))
            painter.drawRect(QRectF(-2.5, -1.5, 5, 3))
            painter.restore()
        painter.restore()

    @staticmethod
    def _tap(painter, alpha, phase):
        font = QFont()
        font.setPixelSize(15)
        font.setBold(True)
        font.setItalic(True)
        painter.save()
        painter.setFont(font)
        painter.setPen(QColor("#333333"))
        painter.setOpacity(_clamp(alpha))
        jiggle = 1.5 * math.sin(phase * 40)
        painter.drawText(QPointF(14 + jiggle, 30), "tap")
        painter.drawText(QPointF(150 - jiggle, 22), "tap!")
        painter.restore()
