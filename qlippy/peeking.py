"""Notices dialogs (Processing algorithm windows and others) covering Qlippy,
moves out from behind them and peeks around their edges.

Dialogs are separate windows, so they always sit on top of Qlippy, which
lives inside the main window. While Qlippy's face is covered it keeps quiet:
the assistant holds back speech until it can be seen again.

On Wayland, applications can't find out where their windows are, so overlap
can't be measured. There Qlippy simply goes quiet while any dialog is open.
"""

import re
import time

from qgis.PyQt.QtCore import QPoint, QRect
from qgis.PyQt.QtGui import QGuiApplication
from qgis.PyQt.QtWidgets import QApplication, QDialog

from . import messages

CHECK_INTERVAL_SECONDS = 0.5
NEARBY_FRACTION = 0.2  # this much of Qlippy behind a dialog: it notices the dialog
MAX_HIDDEN_FRACTION = 0.45  # more than this hidden (or the face hidden): it moves out
RETRY_MOVE_SECONDS = 3.0  # still stuck behind a dialog after this long: try again
COMMENT_CHANCE = {0: 0.5, 1: 0.5, 2: 0.6, 3: 0.75}
FIDGET_ANIMATIONS = ("peek_around", "knock_window", "wait_impatiently")
# The face (eyes and brows, with room for raised brows), in Qlippy's logical coordinates.
FACE_RECT = (56, 40, 92, 72)
TITLE_SUFFIX_RE = re.compile(r"\s*[-–—|:]\s*QGIS\b.*$", re.IGNORECASE)


def _area(rect):
    return max(0, rect.width()) * max(0, rect.height())


def is_processing_dialog(dialog):
    cls = type(dialog)
    return "algorithm" in cls.__name__.lower() or cls.__module__.startswith("processing")


def clean_title(title):
    """'Buffer — QGIS' -> 'Buffer'."""
    return TITLE_SUFFIX_RE.sub("", title or "").strip()


def window_positions_known():
    """False on Wayland, where Qt can't report where windows are."""
    return not QGuiApplication.platformName().lower().startswith("wayland")


class DialogPeeker:
    def __init__(self, assistant):
        self.assistant = assistant
        self.blocking_dialog = None
        self.positions_known = window_positions_known()
        self._next_check_at = 0.0
        self._next_fidget_at = 0.0
        self._last_move_attempt = 0.0
        self._moved_away = False
        self._was_covered = False

    # -------------------------------------------------------- what's open
    def open_dialogs(self):
        """Visible dialogs other than Qlippy's own settings."""
        main_window = self.assistant.mw
        dialogs = []
        for widget in QApplication.topLevelWidgets():
            if (widget is main_window or not isinstance(widget, QDialog) or not widget.isVisible()
                    or widget.isMinimized() or widget.objectName() == "QlippySettings"):
                continue
            dialogs.append(widget)
        return dialogs

    def dialog_rect(self, dialog):
        """A dialog's frame in main-window coordinates."""
        frame = dialog.frameGeometry()
        return QRect(self.assistant.mw.mapFromGlobal(frame.topLeft()), frame.size())

    def dialog_rects(self):
        """Rects (main-window coordinates) the speech bubble should stay clear of."""
        if not self.positions_known:
            return []
        return [self.dialog_rect(dialog) for dialog in self.open_dialogs()]

    def _qlippy_rect(self, position=None):
        character = self.assistant.char
        return QRect(position if position is not None else character.pos(), character.size())

    def _face_rect(self, position=None):
        character = self.assistant.char
        scale = character.scale
        x, y, width, height = FACE_RECT
        origin = position if position is not None else character.pos()
        return QRect(origin.x() + int(x * scale), origin.y() + int(y * scale), int(width * scale), int(height * scale))

    def _hidden_fraction(self, dialog_rect, position=None):
        qlippy = self._qlippy_rect(position)
        return _area(qlippy.intersected(dialog_rect)) / float(max(1, _area(qlippy)))

    def _face_hidden(self, dialog_rect, position=None):
        return self._face_rect(position).intersects(dialog_rect)

    def is_covered(self):
        """True when Qlippy's face is behind a dialog (or, on Wayland, any dialog is open)."""
        if not self.assistant.is_visible():
            return False
        dialogs = self.open_dialogs()
        if not self.positions_known:
            return bool(dialogs)
        return any(self._face_hidden(self.dialog_rect(dialog)) for dialog in dialogs)

    def _nearest_dialog(self):
        """The dialog hiding the largest part of Qlippy (if it notices it at all)."""
        best, best_hidden = None, 0.0
        for dialog in self.open_dialogs():
            rect = self.dialog_rect(dialog)
            hidden = self._hidden_fraction(rect)
            if (hidden >= NEARBY_FRACTION or self._face_hidden(rect)) and hidden >= best_hidden:
                best, best_hidden = dialog, hidden
        return best

    # ------------------------------------------------------------ polling
    def on_dropped(self):
        """The user just put Qlippy somewhere: give them a moment before moving."""
        self._last_move_attempt = time.monotonic()
        self.blocking_dialog = None

    def check(self, now=None):
        """Called every animation frame; does real work twice a second."""
        now = time.monotonic() if now is None else now
        if now < self._next_check_at:
            return
        self._next_check_at = now + CHECK_INTERVAL_SECONDS
        assistant = self.assistant
        if not assistant.is_visible() or assistant.is_hiding() or assistant.is_dragging():
            return

        covered = self.is_covered()
        if self._was_covered and not covered:
            assistant.flush_held_speech()
        self._was_covered = covered
        if not self.positions_known:
            return

        dialog = self._nearest_dialog()
        if dialog is None:
            if self.blocking_dialog is not None:
                self.blocking_dialog = None
                if self._moved_away:
                    self._moved_away = False
                    assistant.wanderer.return_home_soon()
            return

        rect = self.dialog_rect(dialog)
        must_move = self._face_hidden(rect) or self._hidden_fraction(rect) > MAX_HIDDEN_FRACTION
        if dialog is not self.blocking_dialog:
            self.blocking_dialog = dialog
            self._next_fidget_at = now + assistant.rng.uniform(7.0, 11.0)
            if must_move and now - self._last_move_attempt >= RETRY_MOVE_SECONDS:
                self._move_out(dialog, now)
            elif not must_move:
                self._peek(dialog)
            return
        if must_move:
            if now - self._last_move_attempt >= RETRY_MOVE_SECONDS and not assistant.wanderer.busy():
                self._move_out(dialog, now)
        elif (now >= self._next_fidget_at and not assistant.wanderer.busy()
              and assistant.current_animation() is None and not assistant.is_sleeping()):
            self._next_fidget_at = now + assistant.rng.uniform(6.0, 11.0)
            assistant.play(assistant.rng.choice(FIDGET_ANIMATIONS), ctx={"dir": self._side_of(dialog)})

    # ----------------------------------------------------------- reacting
    def _side_of(self, dialog):
        """+1 if the dialog is to Qlippy's right, -1 if to its left."""
        dialog_rect = self.dialog_rect(dialog)
        return 1.0 if dialog_rect.center().x() >= self.assistant.char.geometry().center().x() else -1.0

    def _move_out(self, dialog, now):
        """Move to a spot where the face is visible (whatever the wander setting)."""
        self._last_move_attempt = now
        spot = self.peek_spot(self.dialog_rect(dialog))
        if spot is None:
            return  # no room anywhere: stay put, and quiet
        self._moved_away = True
        wanderer = self.assistant.wanderer
        wanderer.away = True
        wanderer.go(spot, "skate", lambda: self._peek(dialog))

    def _peek(self, dialog):
        assistant = self.assistant
        try:
            if not dialog.isVisible():
                return
        except RuntimeError:
            return
        assistant.play("peek_around", ctx={"dir": self._side_of(dialog)})
        if assistant.flush_held_speech():
            return
        level = assistant.level
        kind = "processing" if is_processing_dialog(dialog) else "dialog"
        if kind == "dialog" and level == 0:
            return
        if (assistant.is_snoozed() or assistant.bubble.isVisible() or self.is_covered()
                or not assistant.settings.comment_enabled("peek_comments")):
            return
        if assistant.rng.random() < COMMENT_CHANCE[level]:
            title = clean_title(dialog.windowTitle()) or "that"
            assistant.say(messages.peek_text(kind, level, assistant.rng, title=title), timeout_ms=6000)

    def peek_spot(self, dialog_rect):
        """The nearest position with the face in view and at most part of the body behind the dialog."""
        character = self.assistant.char
        width, height = character.width(), character.height()
        scale = character.scale
        current = character.pos()
        face_left, face_top, face_width, face_height = (int(value * scale) for value in FACE_RECT)
        face_right = face_left + face_width
        candidates = []
        for y in (current.y(), dialog_rect.center().y() - height // 2, dialog_rect.top(),
                  dialog_rect.bottom() - height):
            candidates.append(QPoint(dialog_rect.left() - face_right - 4, y))      # peeking from the left
            candidates.append(QPoint(dialog_rect.right() - face_left + 4, y))      # peeking from the right
        for x in (current.x(), dialog_rect.left(), dialog_rect.right() - width):
            candidates.append(QPoint(x, dialog_rect.bottom() - face_top + 4))      # below, face just clear
            candidates.append(QPoint(x, dialog_rect.top() - height))               # above
        best, best_distance = None, None
        for candidate in candidates:
            spot = character.clamped(candidate)
            if self._face_hidden(dialog_rect, spot):
                continue
            if self._hidden_fraction(dialog_rect, spot) > MAX_HIDDEN_FRACTION:
                continue
            distance = (spot - current).manhattanLength()
            if best is None or distance < best_distance:
                best, best_distance = spot, distance
        return best
