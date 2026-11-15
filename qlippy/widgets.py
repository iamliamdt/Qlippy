"""Overlay widgets: the character and its speech bubble.

Both are plain child widgets of the QGIS main window (not top-level windows),
so they stay inside it, move with it and work on Wayland. Each one sets a
mask matching what it draws, so clicks outside the drawing reach QGIS.
"""

from qgis.PyQt.QtCore import QPoint, QRect, QRectF, QTimer, Qt, pyqtSignal
from qgis.PyQt.QtGui import QColor, QCursor, QPainter, QPainterPath, QPainterPathStroker, QPen, QRegion, QTransform
from qgis.PyQt.QtWidgets import (
    QApplication,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from .character import DEFAULT_POSE, LOGICAL_H, LOGICAL_W, Renderer
from .compat import event_global_pos, event_pos

from .character import FACE_ONLY_KEYS


def _overlap_area(a, b):
    both = a.intersected(b)
    return max(0, both.width()) * max(0, both.height())


def _region_from_path(path):
    region = QRegion()
    for polygon in path.toFillPolygons():
        region = region.united(QRegion(polygon.toPolygon(), Qt.FillRule.WindingFill))
    return region


class CharacterWidget(QWidget):
    clicked = pyqtSignal(float, float)  # logical coordinates of the click
    doubleClicked = pyqtSignal()
    menuRequested = pyqtSignal(QPoint)
    dragStarted = pyqtSignal()
    dragMoved = pyqtSignal(int)  # horizontal delta since last move
    dragFinished = pyqtSignal()

    def __init__(self, parent):
        super().__init__(parent)
        self.setObjectName("QlippyCharacter")
        # No WA_NoSystemBackground / WA_TranslucentBackground: Qt must repaint
        # the QGIS widgets behind us every frame, or old frames leave trails.
        self.setAutoFillBackground(False)
        self.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.setCursor(Qt.CursorShape.OpenHandCursor)
        self.setToolTip("")
        self.renderer = Renderer()
        self.pose = dict(DEFAULT_POSE)
        self.pose["look_x"] = 0.0
        self.pose["look_y"] = 0.0
        self._scale = 1.0
        self._pose_key = None
        self._shape_key = None
        self._press_global = None
        self._press_pos = None
        self._last_drag_x = 0
        self._dragging = False
        self._click_pos = (0.0, 0.0)
        self._hit = QRegion()
        self._renderer_tint = True
        self._click_timer = QTimer(self)
        self._click_timer.setSingleShot(True)
        self._click_timer.timeout.connect(lambda: self.clicked.emit(*self._click_pos))
        self.set_scale(1.0)

    # ------------------------------------------------------------ public
    @property
    def scale(self):
        return self._scale

    def set_scale(self, scale):
        self._scale = scale
        self.resize(int(LOGICAL_W * scale), int(LOGICAL_H * scale))
        self._shape_key = None
        self._update_mask()
        self.update()

    def set_tint(self, tint):
        self.renderer.set_tint(tint)
        self.update()

    def set_pose(self, pose):
        key = tuple(round(value, 3) if isinstance(value, float) else value for value in pose.values())
        if key == self._pose_key:
            return
        self._pose_key = key
        self.pose = pose
        self._update_mask()
        self.update()

    def eye_center(self):
        """Approximate eye-centre point in widget coordinates."""
        return QPoint(int(100 * self._scale), int(88 * self._scale))

    def anchor_rect(self):
        """Head area in parent coordinates (for the speech bubble)."""
        geometry = self.geometry()
        scale = self._scale
        return QRectF(geometry.x() + 50 * scale, geometry.y() + 48 * scale, 100 * scale, 140 * scale)

    # ----------------------------------------------------------- painting
    def _update_mask(self):
        """Recompute the clickable silhouette.

        It is deliberately NOT applied with setMask(): changing a widget mask
        every frame leaves stale pixels on screen with Qt 6. Instead,
        hit_test() makes the widget transparent to the mouse whenever the
        cursor is outside the silhouette.
        """
        key = tuple(round(value, 1) for key_name, value in self.pose.items()
                    if key_name not in FACE_ONLY_KEYS and isinstance(value, float))
        if key == self._shape_key:
            return
        self._shape_key = key
        path = self.renderer.shape(self.pose)
        transform = QTransform()
        transform.scale(self._scale, self._scale)
        self._hit = _region_from_path(transform.map(path))

    def hit_region(self):
        return self._hit

    def hit_test(self, global_pos=None):
        """Let clicks through unless the cursor is over the drawing."""
        if self._press_global is not None or not self.isVisible():
            return
        if global_pos is None:
            global_pos = QCursor.pos()
        inside = self._hit.contains(self.mapFromGlobal(global_pos))
        if self.testAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents) == inside:
            self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, not inside)

    def paintEvent(self, _ev):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform, True)
        painter.scale(self._scale, self._scale)
        self.renderer.paint(painter, self.pose)
        painter.end()

    # -------------------------------------------------------------- mouse
    def mousePressEvent(self, ev):
        if ev.button() == Qt.MouseButton.LeftButton:
            self._press_global = event_global_pos(ev)
            self._press_local = event_pos(ev)
            self._press_pos = self.pos()
            self._last_drag_x = self._press_global.x()
            self._dragging = False
            ev.accept()
        else:
            super().mousePressEvent(ev)

    def mouseMoveEvent(self, ev):
        if self._press_global is None:
            return
        global_pos = event_global_pos(ev)
        delta = global_pos - self._press_global
        if not self._dragging and delta.manhattanLength() > QApplication.startDragDistance():
            self._dragging = True
            self._click_timer.stop()
            self.setCursor(Qt.CursorShape.ClosedHandCursor)
            self.dragStarted.emit()
        if self._dragging:
            self.move(self.clamped(self._press_pos + delta))
            self.dragMoved.emit(global_pos.x() - self._last_drag_x)
            self._last_drag_x = global_pos.x()
        ev.accept()

    def mouseReleaseEvent(self, ev):
        if ev.button() != Qt.MouseButton.LeftButton or self._press_global is None:
            return
        self._press_global = None
        if self._dragging:
            self._dragging = False
            self.setCursor(Qt.CursorShape.OpenHandCursor)
            self.dragFinished.emit()
        else:
            local_pos = self._press_local
            self._click_pos = (local_pos.x() / self._scale, local_pos.y() / self._scale)
            self._click_timer.start(QApplication.doubleClickInterval())
        ev.accept()

    def mouseDoubleClickEvent(self, ev):
        if ev.button() == Qt.MouseButton.LeftButton:
            self._click_timer.stop()
            self.doubleClicked.emit()
            ev.accept()

    def contextMenuEvent(self, ev):
        self.menuRequested.emit(ev.globalPos())
        ev.accept()

    def clamped(self, pos):
        parent = self.parentWidget()
        if parent is None:
            return pos
        x = max(0, min(pos.x(), parent.width() - self.width()))
        y = max(0, min(pos.y(), parent.height() - self.height()))
        return QPoint(x, y)


_BUBBLE_CSS = """
#QlippyBubble QLabel { color: #1d1d1d; background: transparent; }
#QlippyBubble QLabel#QlippyTitle { font-weight: bold; }
#QlippyBubble QPushButton {
    color: #1d1d1d; background: #f4f4f4; border: 1px solid #8c8c8c;
    border-radius: 3px; padding: 3px 10px; min-height: 18px;
}
#QlippyBubble QPushButton:hover { background: #fff3b0; }
#QlippyBubble QPushButton:pressed { background: #e6d98a; }
#QlippyBubble QToolButton { color: #666666; border: none; background: transparent; padding: 0px 2px; }
#QlippyBubble QToolButton:hover { color: #000000; }
"""

BUBBLE_FILL = QColor("#ffffe1")
BUBBLE_BORDER = QColor("#6b6b6b")


class SpeechBubble(QWidget):
    """Retro tooltip-style speech bubble with a tail pointing at Qlippy."""

    dismissed = pyqtSignal()

    TAIL = 14
    RADIUS = 9
    MAX_WIDTH = 300

    def __init__(self, parent):
        super().__init__(parent)
        self.setObjectName("QlippyBubble")
        self.setAutoFillBackground(False)
        self.setStyleSheet(_BUBBLE_CSS)
        self._tail_bottom = True
        self._tail_x = 40.0
        self.avoid_provider = None  # callable -> [QRect in parent coords] to stay clear of
        self._hit = QRegion()
        self._buttons = []

        self._title = QLabel(self)
        self._title.setObjectName("QlippyTitle")
        self._close = QToolButton(self)
        self._close.setText("✕")
        self._close.setToolTip("Close")
        self._close.setCursor(Qt.CursorShape.PointingHandCursor)
        self._close.clicked.connect(self.dismiss)
        self._text = QLabel(self)
        self._text.setWordWrap(True)
        self._text.setTextFormat(Qt.TextFormat.RichText)
        self._text.setOpenExternalLinks(False)
        self._text.setTextInteractionFlags(Qt.TextInteractionFlag.NoTextInteraction)

        self._layout = QVBoxLayout(self)
        self._layout.setSpacing(6)
        header = QHBoxLayout()
        header.setContentsMargins(0, 0, 0, 0)
        header.addWidget(self._title, 1)
        header.addWidget(self._close, 0, Qt.AlignmentFlag.AlignTop)
        self._layout.addLayout(header)
        self._layout.addWidget(self._text)
        self._btn_row = QHBoxLayout()
        self._btn_row.setContentsMargins(0, 2, 0, 0)
        self._btn_row.addStretch(1)
        self._layout.addLayout(self._btn_row)

        self._timer = QTimer(self)
        self._timer.setSingleShot(True)
        self._timer.timeout.connect(self.dismiss)
        self._timeout_ms = 0
        self.hide()

    # ------------------------------------------------------------ public
    def show_message(self, text, title=None, buttons=None, timeout_ms=None, anchor=None):
        """buttons: list of (label, callback or None, close_after: bool)."""
        for button in self._buttons:
            self._btn_row.removeWidget(button)
            button.deleteLater()
        self._buttons = []
        for label, callback, close in buttons or []:
            button = QPushButton(label, self)
            button.setCursor(Qt.CursorShape.PointingHandCursor)
            button.setFocusPolicy(Qt.FocusPolicy.NoFocus)
            button.clicked.connect(lambda _=False, callback=callback, close=close: self._on_button(callback, close))
            self._btn_row.addWidget(button)
            self._buttons.append(button)
        self._title.setText(title or "")
        self._title.setVisible(bool(title))
        self._text.setText(text)
        if timeout_ms is None:
            plain_len = len(self._text.text())
            timeout_ms = int(min(30000, 7000 + 55 * plain_len))
        self._timeout_ms = timeout_ms
        self.show()
        self.raise_()
        if anchor is not None:
            self.place(anchor)
        self._timer.start(self._timeout_ms)

    def dismiss(self):
        self._timer.stop()
        if self.isVisible():
            self.hide()
            self.dismissed.emit()

    def place(self, anchor):
        """Position next to anchor (QRectF in parent coords).

        Tries above and below the anchor, shifted left, centred and right, and
        picks the spot least covered by other windows (see avoid_provider).
        """
        parent = self.parentWidget()
        if parent is None:
            return
        parent_width, parent_height = parent.width(), parent.height()
        width = max(160, min(self.MAX_WIDTH, parent_width - 16))
        self._set_margins(True)
        self.setFixedWidth(width)
        self._layout.activate()
        height = self.heightForWidth(width)
        if height <= 0:
            height = self.sizeHint().height()
        avoid = []
        if self.avoid_provider is not None:
            try:
                avoid = list(self.avoid_provider())
            except RuntimeError:
                avoid = []
        tip_x = anchor.center().x()
        best = None
        for tail_bottom in (True, False):
            # extra_gap moves the bubble further from Qlippy, for when a window sits right next to it
            for extra_gap in (0, 60, 120, 200):
                wanted_y = (anchor.top() - height - extra_gap) if tail_bottom else (anchor.bottom() + extra_gap)
                y = max(2.0, min(wanted_y, parent_height - height - 2.0))
                # share_left > 1 or < 0 puts the bubble entirely to one side of Qlippy
                for share_left in (0.72, 0.5, 0.28, 1.0, 0.0, 1.35, -0.35):
                    x = max(6.0, min(tip_x - width * share_left, parent_width - width - 6.0))
                    rect = QRect(int(x), int(y), int(width), int(height))
                    covered = sum(_overlap_area(rect, other) for other in avoid)
                    score = (covered * 10.0                        # hidden behind another window: worst
                             + abs(y - wanted_y) * width            # pushed onto Qlippy by the window edge
                             + (0.0 if tail_bottom else width * 3)  # prefer above Qlippy
                             + extra_gap * width * 0.02             # prefer close to Qlippy
                             + abs(share_left - 0.72) * width)      # prefer the usual left-leaning spot
                    if best is None or score < best[0]:
                        best = (score, tail_bottom, x, y)
        _score, tail_bottom, x, y = best
        self._set_margins(tail_bottom)
        self._tail_bottom = tail_bottom
        self._tail_x = max(self.RADIUS + 14.0, min(tip_x - x, width - self.RADIUS - 14.0))
        self.setFixedSize(int(width), int(height))
        self.move(int(x), int(y))
        self._update_mask()
        self.update()

    # ----------------------------------------------------------- internals
    def _set_margins(self, tail_bottom):
        if tail_bottom:
            self._layout.setContentsMargins(12, 8, 8, 10 + self.TAIL)
        else:
            self._layout.setContentsMargins(12, 8 + self.TAIL, 8, 10)

    def _on_button(self, callback, close):
        if close:
            self.dismiss()
        if callback is not None:
            callback()

    def _bubble_path(self):
        width, height, tail_size, radius = float(self.width()), float(self.height()), float(self.TAIL), float(self.RADIUS)
        if self._tail_bottom:
            body = QRectF(0.5, 0.5, width - 4, height - tail_size - 1)
        else:
            body = QRectF(0.5, tail_size + 0.5, width - 4, height - tail_size - 4)
        path = QPainterPath()
        path.addRoundedRect(body, radius, radius)
        tail_x = self._tail_x
        tail = QPainterPath()
        if self._tail_bottom:
            tail.moveTo(tail_x - 12, body.bottom() - 1)
            tail.lineTo(tail_x + 6, height - 1.0)
            tail.lineTo(tail_x + 2, body.bottom() - 1)
        else:
            tail.moveTo(tail_x - 12, body.top() + 1)
            tail.lineTo(tail_x + 6, 1.0)
            tail.lineTo(tail_x + 2, body.top() + 1)
        tail.closeSubpath()
        return path.united(tail)

    def _update_mask(self):
        """Clickable area of the bubble (not applied as a mask, see CharacterWidget)."""
        path = self._bubble_path()
        stroker = QPainterPathStroker()
        stroker.setWidth(4)
        full = QPainterPath(path)
        full.addPath(stroker.createStroke(path))
        full.setFillRule(Qt.FillRule.WindingFill)
        self._hit = _region_from_path(full)

    def hit_test(self, global_pos=None):
        if not self.isVisible():
            return
        if global_pos is None:
            global_pos = QCursor.pos()
        inside = self._hit.contains(self.mapFromGlobal(global_pos))
        if self.testAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents) == inside:
            self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, not inside)

    def paintEvent(self, _ev):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        path = self._bubble_path()
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QColor(0, 0, 0, 50))
        painter.drawPath(path.translated(2.5, 2.5))
        painter.setBrush(BUBBLE_FILL)
        painter.setPen(QPen(BUBBLE_BORDER, 1.2))
        painter.drawPath(path)
        painter.end()

    def enterEvent(self, ev):
        self._timer.stop()
        super().enterEvent(ev)

    def leaveEvent(self, ev):
        if self.isVisible():
            self._timer.start(max(4000, self._timeout_ms // 2))
        super().leaveEvent(ev)

    def resizeEvent(self, ev):
        self._update_mask()
        super().resizeEvent(ev)



