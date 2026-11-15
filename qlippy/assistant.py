"""Qlippy's brain: animation playback, idle behaviour, speech and menus."""

import math
import random
import time

from qgis.PyQt.QtCore import QEvent, QObject, QPoint, QPointF, Qt, QTimer, pyqtSignal
from qgis.PyQt.QtGui import QCursor, QPolygonF, QTransform
from qgis.PyQt.QtWidgets import QDockWidget, QMenu

from . import messages
from .animations import BY_NAME, pick_idle, sleep_pose
from .character import BODY_CENTER, DEFAULT_POSE, MAP_U, MAP_V, RING_R, TAIL_A, TAIL_TIP
from .settings import IDLE_SLEEP_SECONDS, LEVEL_NAMES
from .peeking import DialogPeeker
from .wander import Wanderer
from .widgets import CharacterWidget, SpeechBubble

FRAME_MS = 33
# Useful advice held back by the gap between comments is dropped after this long.
QUEUED_NOTICE_MAX_AGE_SECONDS = 300
# minimum seconds between event-triggered messages, per level


class Assistant(QObject):
    visibilityChanged = pyqtSignal(bool)
    settingsRequested = pyqtSignal()

    def __init__(self, iface, settings, parent=None):
        super().__init__(parent)
        self.iface = iface
        self.settings = settings
        self.mw = iface.mainWindow()
        # Randomness only picks jokes and animations; SystemRandom keeps security scanners quiet.
        self.rng = random.SystemRandom()

        self.char = CharacterWidget(self.mw)
        self.char.set_tint(self.settings.tint)
        messages.set_personality(self.settings.personality)
        self.char.hide()
        self.bubble = SpeechBubble(self.mw)
        self.char.clicked.connect(self._on_click)
        self.char.doubleClicked.connect(self._on_double_click)
        self.char.menuRequested.connect(self.show_menu)
        self.char.dragStarted.connect(self._on_drag_started)
        self.char.dragMoved.connect(self._on_drag_moved)
        self.char.dragFinished.connect(self._on_drag_finished)

        self._t0 = time.monotonic()
        self._anim = None
        self._anim_start = 0.0
        self._anim_done = None
        self._anim_ctx = None
        self._dead_until = 0.0
        self._sleeping = False
        self._sleep_start = 0.0
        self._dragging = False
        self._drag_rot = 0.0
        self._look = [0.0, 0.0]
        self._blink_at = self._t0 + 2.0
        self._blink_start = None
        self._last_cursor = QCursor.pos()
        self._last_activity = self._t0
        self._snooze_until = 0.0
        self._last_event_say = 0.0
        self._clicks = []
        self._shown = False
        self._hiding = False

        self._tick = QTimer(self)
        self._tick.setInterval(FRAME_MS)
        self._tick.timeout.connect(self._on_tick)
        self._anim_timer = QTimer(self)
        self._anim_timer.setSingleShot(True)
        self._anim_timer.timeout.connect(self._random_animation)
        self._remark_timer = QTimer(self)
        self._remark_timer.setSingleShot(True)
        self._remark_timer.timeout.connect(self._random_remark)

        self._alive = True
        self.wanderer = Wanderer(self)
        self.peeker = DialogPeeker(self)
        self.bubble.avoid_provider = self.peeker.dialog_rects
        self._held_speech = None  # (time, say() arguments) while Qlippy is covered
        self._queued_notice = None  # (time, rule id, text, title, anim) waiting for the gap to pass
        self.mw.installEventFilter(self)
        self.char.set_scale(self.settings.scale)

    # ============================================================ lifecycle
    def start(self):
        if self.settings.visible:
            self.set_visible(True, greet=True)

    def shutdown(self):
        """Plugin unloading: stop everything and delete the widgets.

        Anything still scheduled (delayed comments, timers, panel signals)
        checks is_alive() and does nothing afterwards.
        """
        self._alive = False
        self.wanderer.stop()
        for timer in (self._tick, self._anim_timer, self._remark_timer):
            timer.stop()
        try:
            self.mw.removeEventFilter(self)
        except RuntimeError:
            pass
        self.bubble.dismiss()
        for widget in (self.bubble, self.char):
            widget.hide()
            widget.setParent(None)
            widget.deleteLater()

    def is_alive(self):
        return self._alive

    @property
    def level(self):
        return self.settings.level

    def is_visible(self):
        return self._shown

    def is_hiding(self):
        return self._hiding

    def is_dragging(self):
        return self._dragging

    def current_animation(self):
        return self._anim

    def is_sleeping(self):
        return self._sleeping

    def last_activity(self):
        return self._last_activity

    def set_visible(self, visible, greet=False):
        if visible == self._shown and not self._hiding:
            return
        if visible:
            self._hiding = False
            self._shown = True
            self.settings.visible = True
            self._restore_position()
            self.char.show()
            self.char.raise_()
            self._tick.start()
            self.play("enter", done=lambda: self.play("land"))
            self._schedule_animation()
            self._schedule_remark()
            self.wanderer.schedule()
            if greet:
                QTimer.singleShot(1600, self._greet)
        else:
            self.settings.visible = False
            self.bubble.dismiss()
            self._anim_timer.stop()
            self._remark_timer.stop()
            self.wanderer.stop()
            self.wanderer.away = False
            self._hiding = True
            self._sleeping = False
            self.play("exit", done=self._finish_hide)
        self.visibilityChanged.emit(visible)

    def _finish_hide(self):
        if not self._hiding:
            return
        self._hiding = False
        self._shown = False
        self._tick.stop()
        self.char.hide()

    def apply_settings(self):
        messages.set_personality(self.settings.personality)
        self.char.set_scale(self.settings.scale)
        self.char.set_tint(self.settings.tint)
        self._clamp_position()
        self._schedule_animation()
        self._schedule_remark()
        self.wanderer.schedule()
        if self.bubble.isVisible():
            self.bubble.place(self.char.anchor_rect())

    def set_level(self, level):
        self.settings.level = level
        self._schedule_remark()
        text, anim = messages.LEVEL_CHANGE[level]
        self.say(text, title=LEVEL_NAMES[level], anim=anim, force=True)

    # ============================================================ animation
    def play(self, name, done=None, ctx=None):
        if not self._alive:
            return
        anim = BY_NAME.get(name)
        if anim is None:
            return
        if self._sleeping and name not in ("wake", "exit"):
            self._sleeping = False
        self._anim = anim
        self._anim_start = time.monotonic()
        self._anim_done = done
        self._anim_ctx = ctx
        if self._shown and not self._tick.isActive():
            self._tick.start()

    def _finish_anim(self):
        anim, done = self._anim, self._anim_done
        self._anim = None
        self._anim_done = None
        if done is not None:
            done()
        elif anim is not None and anim.follow and self.rng.random() < anim.follow[1]:
            self.play(anim.follow[0])

    def _on_tick(self):
        if not self._alive:
            return
        now = time.monotonic()
        pose = dict(DEFAULT_POSE)
        if self._sleeping:
            pose.update(sleep_pose(now - self._sleep_start))
        if self._anim is not None:
            elapsed = now - self._anim_start
            progress = elapsed / self._anim.duration
            if progress >= 1.0 and not self._anim.loop:
                pose.update(self._anim.pose(1.0, self._anim.duration, self._anim_ctx))
                self._finish_anim()
                if self._anim is not None:  # a chained animation started
                    pose = dict(DEFAULT_POSE)
                    pose.update(self._anim.pose(0.0, 0.0, self._anim_ctx))
            else:
                pose["phase"] = elapsed
                pose.update(self._anim.pose(progress % 1.0, elapsed, self._anim_ctx))
            if self._anim is not None and self._anim.name == "play_dead" and now > self._dead_until:
                self.play("get_up")
        self.wanderer.apply(pose, now)
        self.peeker.check(now)
        self._deliver_queued_notice(now)
        if self._dragging:
            self._held_overlay(pose)
        else:
            self._drag_rot *= 0.8
        self._blink(pose, now)
        self._update_look(pose)
        self._idle_check(now)
        self.char.set_pose(pose)
        cursor = QCursor.pos()
        self.char.hit_test(cursor)
        self.bubble.hit_test(cursor)

    def _held_overlay(self, pose):
        self._drag_rot *= 0.85
        pose["rotation"] += self._drag_rot
        pose["eye_scale"] = max(pose["eye_scale"], 1.2)
        pose["pupil_scale"] = 0.8
        pose["brow_l"] = max(pose["brow_l"], 1.0)
        pose["brow_r"] = max(pose["brow_r"], 1.0)
        pose["offset_y"] -= 6.0
        pose["scale_y"] *= 1.04
        pose["look_x"], pose["look_y"] = 0.0, -0.2
        if self.level >= 2:
            pose["sweat"] = 1.0
            pose["phase"] = time.monotonic() - self._t0

    def _blink(self, pose, now):
        if self._sleeping or pose["lid"] > 0.5 or pose["happy"] > 0.5:
            return
        if self._blink_start is None and now >= self._blink_at:
            self._blink_start = now
        if self._blink_start is not None:
            blink_progress = (now - self._blink_start) / 0.16
            if blink_progress >= 1.0:
                self._blink_start = None
                # sometimes a double blink
                self._blink_at = now + (0.25 if self.rng.random() < 0.15 else self.rng.uniform(2.5, 6.5))
            else:
                pose["lid"] = max(pose["lid"], math.sin(math.pi * blink_progress))

    def _update_look(self, pose):
        target_x, target_y = pose["look_x"], pose["look_y"]
        if target_x is None or target_y is None:
            cursor_x, cursor_y = self._cursor_look()
            target_x = cursor_x if target_x is None else target_x
            target_y = cursor_y if target_y is None else target_y
        follow_speed = 0.35
        self._look[0] += (target_x - self._look[0]) * follow_speed
        self._look[1] += (target_y - self._look[1]) * follow_speed
        if abs(self._look[0] - target_x) < 0.01:
            self._look[0] = target_x
        if abs(self._look[1] - target_y) < 0.01:
            self._look[1] = target_y
        pose["look_x"], pose["look_y"] = round(self._look[0], 3), round(self._look[1], 3)

    def _cursor_look(self):
        if not self.settings.follow_cursor:
            return 0.0, 0.0
        center = self.char.mapToGlobal(self.char.eye_center())
        offset = QCursor.pos() - center
        dist = math.hypot(offset.x(), offset.y())
        if dist < 1.0:
            return 0.0, 0.0
        reach = min(1.0, dist / (140.0 * self.char.scale))
        return offset.x() / dist * reach, offset.y() / dist * reach

    # ========================================================== idle/sleep
    def _idle_check(self, now):
        cur = QCursor.pos()
        if cur != self._last_cursor:
            self._last_cursor = cur
            self._last_activity = now
            if self._sleeping:
                self.wake()
            return
        if (self.settings.doze and not self._sleeping and self._anim is None and not self._dragging
                and not self.wanderer.busy() and not self.bubble.isVisible()
                and now - self._last_activity > IDLE_SLEEP_SECONDS):
            self.fall_asleep()

    def fall_asleep(self):
        def asleep():
            self._sleeping = True
            self._sleep_start = time.monotonic()
        self.play("doze", done=asleep)

    def wake(self, quip=True):
        self._sleeping = False
        self.play("wake")
        if quip and self.level >= 1 and self.rng.random() < 0.4:
            QTimer.singleShot(1300, lambda: self.say(messages.pick(messages.WAKE, self.level, self.rng)))

    def _random_animation(self):
        if (self._shown and self._anim is None and not self._sleeping and not self._dragging
                and not self.wanderer.busy() and not self.peeker.is_covered()):
            self.play(pick_idle(self.level, self.rng).name)
        self._schedule_animation()

    def _schedule_animation(self):
        self._anim_timer.stop()
        interval = self.settings.animation_interval(self.level)
        if interval is None or not self._shown:
            return
        self._anim_timer.start(int(self.rng.uniform(*interval) * 1000))

    def _random_remark(self):
        if (self._can_talk() and not self._sleeping and not self.bubble.isVisible()
                and not self.peeker.is_covered()):
            self.remark()
        self._schedule_remark()

    def _schedule_remark(self):
        self._remark_timer.stop()
        if not self.settings.random_remarks or not self._shown:
            return
        shortest, longest = self.settings.remark_interval(self.level)
        self._remark_timer.start(int(self.rng.uniform(shortest, longest) * 1000))

    # ============================================================== speech
    def is_snoozed(self):
        return time.monotonic() < self._snooze_until

    def _can_talk(self):
        return self._shown and not self._hiding and not self.is_snoozed()

    def say(self, text, title=None, anim=None, buttons=None, force=False, timeout_ms=None):
        """Show a speech bubble. Returns True if shown (or held until Qlippy is visible again)."""
        if not self._alive:
            return False
        if not self._shown or self._hiding or (self.is_snoozed() and not force):
            return False
        if not force and self.peeker.is_covered():
            # Nobody can see Qlippy: keep the latest message for when it's visible again.
            self._held_speech = (time.monotonic(), dict(text=text, title=title, anim=anim, buttons=buttons,
                                                        timeout_ms=timeout_ms))
            return True
        if self._sleeping:
            self.wake(quip=False)
        if anim and not force:
            anim = messages.personality_anim(anim, self.rng)
        if buttons is None:
            buttons = [(messages.DISMISS_LABEL[self.level], None, True)]
        self.bubble.show_message(text, title, buttons, timeout_ms, self.char.anchor_rect())
        self.char.raise_()
        if anim:
            self.play(anim)
        return True

    def flush_held_speech(self, max_age_seconds=60.0):
        """Say what was held back while Qlippy was covered. Returns True if something was said."""
        held, self._held_speech = self._held_speech, None
        if held is None or time.monotonic() - held[0] > max_age_seconds:
            return False
        if self.peeker.is_covered() or self.bubble.isVisible():
            self._held_speech = held
            return False
        return self.say(**held[1])

    def notify(self, rule_id, text, title=None, anim=None):
        """Event-triggered advice (from the rule engine); rate limited.

        If it can't be said right now (another bubble is showing, or the gap
        between comments hasn't passed), useful advice (comments that also
        appear at the Helpful level) is kept and said once there's room.
        Teasing is simply dropped. Returns True if said or kept for later.
        """
        if not self._alive:
            return False
        now = time.monotonic()
        if not self._can_talk():
            return False
        if self.bubble.isVisible() or now - self._last_event_say < self.settings.event_gap(self.level):
            if messages.RULES.get(rule_id, {}).get("min_level", 1) == 0:
                self._queued_notice = (now, rule_id, text, title, anim)
                return True
            return False
        return self._deliver_notice(rule_id, text, title, anim)

    def _deliver_notice(self, rule_id, text, title, anim):
        buttons = [
            (messages.DISMISS_LABEL[self.level], None, True),
            (messages.DISABLE_LABEL[self.level], lambda: self.settings.disable_rule(rule_id), True),
        ]
        if self.say(text, title=title, anim=anim, buttons=buttons):
            self._last_event_say = time.monotonic()
            return True
        return False

    def _deliver_queued_notice(self, now):
        """Say kept-back advice once the gap has passed (and it isn't stale)."""
        queued = self._queued_notice
        if queued is None:
            return
        queued_at, rule_id, text, title, anim = queued
        if now - queued_at > QUEUED_NOTICE_MAX_AGE_SECONDS or not self.settings.comment_enabled(rule_id):
            self._queued_notice = None
            return
        if (not self._can_talk() or self.bubble.isVisible() or self._dragging
                or now - self._last_event_say < self.settings.event_gap(self.level)
                or self.peeker.is_covered()):
            return
        self._queued_notice = None
        self._deliver_notice(rule_id, text, title, anim)

    def react(self, anim):
        """Animation-only reaction (no speech)."""
        if not self._alive:
            return False
        if self._shown and not self._hiding and self._anim is None and not self._dragging:
            self.play(anim)

    def remark(self, force=False, animate=True):
        text, title, anim = messages.random_remark(self.level, self.rng)
        buttons = [(messages.DISMISS_LABEL[self.level], None, True),
                   (messages.ANOTHER_LABEL[self.level], lambda: self.remark(force=True), True)]
        self.say(text, title=title, anim=anim if animate else None, buttons=buttons, force=force)

    def _greet(self):
        self.say(messages.greeting(self.level, rng=self.rng), anim="wave")

    def snooze(self, minutes):
        """minutes=None snoozes for the rest of the session."""
        if minutes is None:
            self._snooze_until = float("inf")
            duration = "the rest of this session"
        else:
            self._snooze_until = time.monotonic() + minutes * 60
            duration = "{} minutes".format(minutes) if minutes < 60 else "{} hour(s)".format(minutes // 60)
        self.say(messages.pick(messages.SNOOZE, self.level, self.rng, duration=duration),
                 anim="sad" if self.level >= 2 else "nod", force=True, timeout_ms=4000)

    def unsnooze(self):
        self._snooze_until = 0.0
        self.say(messages.pick(messages.UNSNOOZE, self.level, self.rng), anim="bounce")

    # ======================================================= interaction
    def _on_click(self, x, y):
        now = time.monotonic()
        self._clicks = [click_time for click_time in self._clicks if now - click_time < 4.0] + [now]
        click_count = len(self._clicks)
        level = self.level
        if self._anim is not None and self._anim.name == "play_dead":
            self._dead_until = now + 3.0
            return
        if self._sleeping:
            self.wake(quip=True)
            return
        if level >= 1 and click_count >= 7:
            self._clicks = []
            if level >= 3:
                self._dead_until = now + 3.0
                self.bubble.dismiss()
                self.play("play_dead")
                if self.rng.random() < 0.5:
                    QTimer.singleShot(900, lambda: self.say(messages.pick(messages.DEAD, 3, self.rng),
                                                            force=True, timeout_ms=3000))
            else:
                self.wanderer.dodge(mode="teleport" if level >= 2 else "hop")
            return
        if level >= 1 and click_count == 5:
            self.wanderer.dodge()
            if self.rng.random() < 0.5:
                QTimer.singleShot(500, lambda: self.say(messages.pick(messages.POKE, level, self.rng),
                                                        force=True, timeout_ms=3500))
            return
        if level >= 1 and click_count == 3:
            self.play("annoyed" if level >= 2 else "shake_off")
            if self.rng.random() < 0.6:
                self.say(messages.pick(messages.POKE, level, self.rng), force=True, timeout_ms=3500)
            return
        if self.bubble.isVisible():
            self.bubble.dismiss()
        self._click_reaction(x, y)
        if (self.settings.comment_enabled("click_remarks")
                and self.rng.random() < messages.CLICK_TEXT_CHANCE[level]):
            QTimer.singleShot(500, lambda: self.remark(force=True, animate=False))

    def click_zone(self, x, y):
        """Which part of Qlippy was clicked: head, tail, ring or paper."""
        pose = self.char.pose
        renderer = self.char.renderer
        inverse, invertible = renderer.body_transform(pose).inverted()
        point = QPointF(x, y)
        local = inverse.map(point) if invertible else point
        local_x, local_y = local.x(), local.y()
        if 58 <= local_x <= 142 and 54 <= local_y <= 108:
            return "head", None
        tail_ax, tail_ay, tail_bx, tail_by = TAIL_A.x(), TAIL_A.y(), TAIL_TIP.x(), TAIL_TIP.y()
        tail_dx, tail_dy = tail_bx - tail_ax, tail_by - tail_ay
        along = max(0.0, min(1.0, ((local_x - tail_ax) * tail_dx + (local_y - tail_ay) * tail_dy) / (tail_dx * tail_dx + tail_dy * tail_dy)))
        if math.hypot(local_x - (tail_ax + along * tail_dx), local_y - (tail_ay + along * tail_dy)) < 9:
            return "tail", None
        if math.hypot(local_x - BODY_CENTER.x(), local_y - BODY_CENTER.y()) <= RING_R + 6:
            return "ring", None
        to_screen = renderer.paper_mapper(pose)
        inset = QPolygonF([to_screen(MAP_U[0], MAP_V[0]), to_screen(MAP_U[1], MAP_V[0]), to_screen(MAP_U[1], MAP_V[1]),
                           to_screen(MAP_U[0], MAP_V[1])])
        if inset.containsPoint(point, Qt.FillRule.OddEvenFill):
            src = QPolygonF([QPointF(-180, 90), QPointF(180, 90), QPointF(180, -90), QPointF(-180, -90)])
            transform = QTransform()
            if QTransform.quadToQuad(inset, src, transform):
                lonlat = transform.map(point)
                return "paper", (max(-180.0, min(180.0, lonlat.x())), max(-90.0, min(90.0, lonlat.y())))
            return "paper", None
        sheet = QPolygonF([to_screen(0, 0), to_screen(1, 0), to_screen(1, 1), to_screen(0, 1)])
        if sheet.containsPoint(point, Qt.FillRule.OddEvenFill):
            return "paper", None
        return "ring", None

    def _click_reaction(self, x, y):
        zone, lonlat = self.click_zone(x, y)
        side = 1.0 if x >= 100 else -1.0
        if zone == "head":
            name = self.rng.choice(["flinch", "blink_hard", "shake_off"])
            self.play(name, ctx={"dir": side})
        elif zone == "tail":
            self.play(self.rng.choice(["tail_yank", "wave"]))
        elif zone == "paper":
            options = ["paper_flip", "pat_map"] + (["pin_here", "pin_here"] if lonlat else [])
            name = self.rng.choice(options)
            ctx = {"dir": side}
            if lonlat:
                ctx.update(lon=lonlat[0], lat=lonlat[1])
            self.play(name, ctx=ctx)
        else:
            self.play(self.rng.choice(["boing", "giggle", "spin"]))

    def _on_double_click(self):
        if self._sleeping:
            self.wake(quip=False)
            return
        self.play(pick_idle(self.level, self.rng).name)

    def _on_drag_started(self):
        self.wanderer.cancel()
        if self._anim is not None and self._anim.name == "play_dead":
            self._anim = None
        self._dragging = True
        self._last_activity = time.monotonic()
        if self.level >= 2 and self.rng.random() < 0.3 and not self.bubble.isVisible():
            self.say(messages.pick(messages.DRAG, self.level, self.rng), timeout_ms=2500)

    def _on_drag_moved(self, dx):
        self._drag_rot = max(-25.0, min(25.0, self._drag_rot - dx * 0.9))
        if self.bubble.isVisible():
            self.bubble.place(self.char.anchor_rect())

    def _on_drag_finished(self):
        self._dragging = False
        self.peeker.on_dropped()
        self.save_position()
        self.play("land")
        if self.bubble.isVisible():
            self.bubble.place(self.char.anchor_rect())

    def show_menu(self, global_pos):
        menu = QMenu(self.mw)
        say_action = menu.addAction("Say something")
        say_action.triggered.connect(lambda _=False: self.remark(force=True))
        explore_action = menu.addAction("Go exploring")
        explore_action.triggered.connect(lambda _=False: self.wanderer.explore() or self.say(
            "Nothing interesting to visit right now.", force=True, timeout_ms=3000))
        if self.wanderer.away:
            home_action = menu.addAction("Go home")
            home_action.triggered.connect(lambda _=False: self.wanderer.go_home())
        animate_action = menu.addAction("Animate")
        animate_action.triggered.connect(lambda _=False: self.play(pick_idle(self.level, self.rng).name))
        level_menu = menu.addMenu("Help / Harass")
        for level_index, name in enumerate(LEVEL_NAMES):
            action = level_menu.addAction("{} - {}".format(level_index, name))
            action.setCheckable(True)
            action.setChecked(level_index == self.level)
            action.triggered.connect(lambda _=False, level_index=level_index: self.set_level(level_index))
        snooze_menu = menu.addMenu("Snooze")
        for label, minutes in (("15 minutes", 15), ("1 hour", 60), ("Rest of session", None)):
            action = snooze_menu.addAction(label)
            action.triggered.connect(lambda _=False, minutes_value=minutes: self.snooze(minutes_value))
        snooze_menu.addSeparator()
        unsnooze_action = snooze_menu.addAction("Unsnooze")
        unsnooze_action.setEnabled(self.is_snoozed())
        unsnooze_action.triggered.connect(lambda _=False: self.unsnooze())
        menu.addSeparator()
        settings_action = menu.addAction("Settings…")
        settings_action.triggered.connect(lambda _=False: self.settingsRequested.emit())
        hide_action = menu.addAction("Hide Qlippy")
        hide_action.triggered.connect(lambda _=False: self.set_visible(False))
        menu.exec(global_pos)
        menu.deleteLater()

    # ============================================================ placement
    def eventFilter(self, obj, ev):
        if obj is self.mw:
            event_type = ev.type()
            if event_type == QEvent.Type.Resize:
                QTimer.singleShot(0, self._clamp_position)
            elif event_type == QEvent.Type.ChildAdded:
                QTimer.singleShot(0, self._raise)
                child = ev.child()
                if isinstance(child, QDockWidget):
                    QTimer.singleShot(800, self.wanderer.schedule_watch)
        return False

    def _raise(self):
        try:
            if self.char.isVisible():
                self.char.raise_()
            if self.bubble.isVisible():
                self.bubble.raise_()
        except RuntimeError:
            pass

    def _free_space(self):
        return (max(1, self.mw.width() - self.char.width()),
                max(1, self.mw.height() - self.char.height()))

    def _restore_position(self):
        relative = self.settings.position
        if relative is None:
            self.char.move(self._default_position())
        else:
            free_width, free_height = self._free_space()
            self.char.move(self.char.clamped(QPoint(int(relative[0] * free_width), int(relative[1] * free_height))))

    def _default_position(self):
        canvas = self.iface.mapCanvas()
        try:
            bottom_right = canvas.mapTo(self.mw, QPoint(canvas.width(), canvas.height()))
        except (RuntimeError, AttributeError, TypeError):
            bottom_right = QPoint(self.mw.width(), self.mw.height())
        return self.char.clamped(QPoint(bottom_right.x() - self.char.width() - 16, bottom_right.y() - self.char.height() - 8))

    def home_position(self):
        relative = self.settings.position
        if relative is None:
            return self._default_position()
        free_width, free_height = self._free_space()
        return self.char.clamped(QPoint(int(relative[0] * free_width), int(relative[1] * free_height)))

    def save_position(self):
        free_width, free_height = self._free_space()
        self.settings.position = (self.char.x() / free_width, self.char.y() / free_height)

    def reset_position(self):
        self.wanderer.cancel()
        self.settings.position = None
        self.char.move(self._default_position())
        if self.bubble.isVisible():
            self.bubble.place(self.char.anchor_rect())

    def _clamp_position(self):
        try:
            if self.wanderer.away or self.wanderer.busy():
                self.char.move(self.char.clamped(self.char.pos()))
            elif self.settings.position is not None:
                self._restore_position()
            else:
                self.char.move(self._default_position())
            if self.bubble.isVisible():
                self.bubble.place(self.char.anchor_rect())
        except RuntimeError:
            pass
