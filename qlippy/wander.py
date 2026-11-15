"""Wandering: Qlippy travels around the main window, visits interesting
places (panels, the save button, the status bar, the map) and comments on
what it finds there.
"""

import math
import time
from collections import namedtuple

from qgis.PyQt.QtCore import QObject, QPoint, QRect, QTimer
from qgis.PyQt.QtGui import QCursor
from qgis.PyQt.QtWidgets import QDockWidget, QToolButton

from . import messages
from .animations import clamp, envelope, smooth

MODES = ["hop", "carpet", "skate", "roll", "teleport"]
MODE_WEIGHTS = [3, 2, 2, 1.5, 1]
SPEED = {"hop": 220.0, "carpet": 300.0, "skate": 340.0, "roll": 280.0}
ARRIVE_ANIMS = {
    "layers": "reading", "save_dirty": "tap_glass", "save_clean": "nod", "statusbar": "search",
    "canvas": "look_around", "processing": "thinking", "browser": "reading", "attribute": "search",
    "messagebar": "nervous", "plugins": "brow_wiggle", "selection": "suspicious",
}


class Place(namedtuple("Place", "key rect weight details")):
    """Somewhere to visit: what it is, where it is (main-window coords), how
    likely it is to be picked, and the facts to fill into the comment."""


class Trip:
    def __init__(self, start, end, mode, duration, on_arrive=None):
        self.start = QPoint(start)
        self.end = QPoint(end)
        self.mode = mode
        self.duration = max(0.6, duration)
        self.t0 = time.monotonic()
        self.on_arrive = on_arrive
        offset_x = end.x() - start.x()
        self.dir = 1.0 if offset_x >= 0 else -1.0
        self.dist = math.hypot(offset_x, end.y() - start.y())


class Wanderer(QObject):
    def __init__(self, assistant, parent=None):
        super().__init__(parent)
        self.assistant = assistant
        self.rng = assistant.rng
        self.trip = None
        self.away = False
        self._last_flee = 0.0
        self._timer = QTimer(self)
        self._timer.setSingleShot(True)
        self._timer.timeout.connect(self._on_timer)
        self._home_timer = QTimer(self)
        self._home_timer.setSingleShot(True)
        self._home_timer.timeout.connect(self._maybe_go_home)
        self._watched = set()
        self._dock_connections = []  # (dock, slot) so they can be disconnected on unload
        self._stopped = False

    # ------------------------------------------------------------ control
    @property
    def settings(self):
        return self.assistant.settings

    def schedule(self):
        self._timer.stop()
        if self._stopped:
            return
        rng = self.settings.wander_interval(self.assistant.level)
        if rng is None or not self.assistant.is_visible():
            return
        self._timer.start(int(self.rng.uniform(*rng) * 1000))
        self._watch_docks()

    def schedule_watch(self):
        self._watch_docks()

    def stop(self):
        """Stop for good (plugin unloading): timers off, panel connections removed."""
        self._stopped = True
        self._timer.stop()
        self._home_timer.stop()
        self.trip = None
        for dock, slot in self._dock_connections:
            try:
                dock.visibilityChanged.disconnect(slot)
            except (TypeError, RuntimeError):
                pass  # the panel (or the connection) is already gone
        self._dock_connections = []
        self._watched = set()

    def pause(self):
        """Stop moving for now (Qlippy hidden); can be scheduled again later."""
        self._timer.stop()
        self._home_timer.stop()
        self.trip = None

    def cancel(self):
        """Abort travel where we are (e.g. the user grabbed Qlippy)."""
        self.trip = None
        self._home_timer.stop()
        self.away = False

    def busy(self):
        return self.trip is not None

    def _can_wander(self):
        assistant = self.assistant
        if self._stopped or not assistant.is_alive():
            return False
        if not assistant.is_visible() or assistant.is_hiding() or assistant.is_dragging() or assistant.is_sleeping() or self.trip:
            return False
        if assistant.bubble.isVisible() or not self.settings.wander or assistant.peeker.blocking_dialog is not None:
            return False
        if self.settings.wander_idle_only and time.monotonic() - assistant.last_activity() < 30:
            return False
        return True

    def _on_timer(self):
        if self._can_wander():
            self.explore()
        self.schedule()

    def on_event(self, key):
        """Something happened at a place worth visiting."""
        if not self._can_wander():
            return
        if self.rng.random() < self.settings.wander_event_chance():
            QTimer.singleShot(700, lambda: self._can_wander() and self.explore(key))

    def _watch_docks(self):
        if self._stopped:
            return
        for dock in self.assistant.mw.findChildren(QDockWidget):
            name = dock.objectName()
            if name in self._watched:
                continue
            if name in ("ProcessingToolbox", "Browser") or "AttributeTable" in type(dock.widget()).__name__:
                key = {"ProcessingToolbox": "processing", "Browser": "browser"}.get(name, "attribute")
                def on_visibility_changed(visible, place=key):
                    if visible:
                        self.on_event(place)
                dock.visibilityChanged.connect(on_visibility_changed)
                self._dock_connections.append((dock, on_visibility_changed))
                self._watched.add(name)

    # ------------------------------------------------------------- trips
    def go(self, target, mode=None, on_arrive=None, speed=1.0):
        char = self.assistant.char
        target = char.clamped(target)
        start = char.pos()
        dist = math.hypot(target.x() - start.x(), target.y() - start.y())
        if dist < 8:
            if on_arrive:
                on_arrive()
            return
        if mode is None:
            mode = self.rng.choices(MODES, weights=MODE_WEIGHTS)[0]
            if dist > 900 and self.rng.random() < 0.5:
                mode = "teleport"
        duration = 1.3 if mode == "teleport" else clamp(dist / (SPEED[mode] * speed), 0.8, 6.0)
        self.assistant.bubble.dismiss()
        self.trip = Trip(start, target, mode, duration, on_arrive)

    def go_home(self, mode=None):
        self._home_timer.stop()

        def arrived():
            self.away = False
        self.go(self.assistant.home_position(), mode, arrived)

    def return_home_soon(self, delay_ms=1500):
        if self.away and not self.trip:
            self._home_timer.start(delay_ms)

    def _maybe_go_home(self):
        if not self.away or self.trip or self.assistant.is_dragging():
            return
        if self.assistant.bubble.isVisible():
            self._home_timer.start(3000)
            return
        if self.settings.wander_return_home:
            self.go_home()
        else:
            self.away = False
            self.assistant.save_position()

    def dodge(self, cursor_pos=None, mode="hop"):
        """Hop away from the cursor."""
        char = self.assistant.char
        main_window = self.assistant.mw
        if cursor_pos is None:
            cursor_pos = main_window.mapFromGlobal(QCursor.pos())
        zone = char.geometry()
        offset_x = zone.center().x() - cursor_pos.x()
        step = 170 if offset_x >= 0 else -170
        target = QPoint(zone.x() + step, zone.y())
        if char.clamped(target).x() == zone.x():  # stuck against an edge
            target = QPoint(zone.x() - step, zone.y() + self.rng.choice((-120, 120)))
        self.away = True
        self.go(target, mode, lambda: self._home_timer.start(6000), speed=1.8)

    def explore(self, key=None):
        places = self.destinations()
        if key is not None:
            places = [place for place in places if place.key == key] or places
        if not places:
            return False
        place = self.rng.choices(places, weights=[place.weight for place in places])[0]
        target = self._spot(place.rect, place.key)
        self.away = True
        self.go(target, None, lambda: self._arrive(place.key, place.details))
        return True

    def _arrive(self, key, details):
        assistant = self.assistant
        anim = ARRIVE_ANIMS.get(key, "look_around")
        text = messages.wander_text(key, assistant.level, assistant.rng, **details)
        if text and self.settings.comment_enabled("wander_comments") and not assistant.is_snoozed():
            assistant.say(text, anim=anim)
        else:
            assistant.play(anim)
        self._home_timer.start(9000)

    # ------------------------------------------------------- per-frame
    def apply(self, pose, now):
        trip = self.trip
        if trip is None:
            if self.away and now - self._last_flee > 2.5 and not self.assistant.is_dragging():
                self._flee_check(now)
            return
        progress = clamp((now - trip.t0) / trip.duration)
        char = self.assistant.char
        mode = trip.mode
        if mode == "teleport":
            pos = trip.start if progress < 0.5 else trip.end
        else:
            eased = progress if mode == "hop" else smooth(progress)
            pos = QPoint(int(trip.start.x() + (trip.end.x() - trip.start.x()) * eased),
                         int(trip.start.y() + (trip.end.y() - trip.start.y()) * eased))
        if pos != char.pos():
            char.move(pos)
            if self.assistant.bubble.isVisible():
                self.assistant.bubble.place(char.anchor_rect())
        getattr(self, "_pose_" + mode)(pose, progress, now - trip.t0, trip)
        if progress >= 1.0:
            self.trip = None
            if trip.on_arrive:
                trip.on_arrive()

    def _flee_check(self, now):
        main_window = self.assistant.mw
        cursor = main_window.mapFromGlobal(QCursor.pos())
        zone = self.assistant.char.geometry().adjusted(-25, -25, 25, 25)
        if zone.contains(cursor):
            self._last_flee = now
            self._home_timer.stop()
            self.dodge(cursor)

    # locomotion poses ---------------------------------------------------
    @staticmethod
    def _pose_hop(pose, progress, elapsed, trip):
        hop_count = max(2, int(round(trip.dist / 70.0)))
        hop_phase = (progress * hop_count) % 1.0
        landing = 1.0 - clamp(min(hop_phase, 1.0 - hop_phase) / 0.12)
        pose["offset_y"] += -math.sin(math.pi * hop_phase) * 18.0
        pose["scale_y"] *= 1.0 - 0.12 * landing + 0.05 * (1 - landing)
        pose["scale_x"] *= 1.0 + 0.08 * landing
        pose["rotation"] += 5.0 * trip.dir
        pose["paper_dx"] += -trip.dir * 5.0 * math.sin(math.pi * hop_phase)
        pose["look_x"] = trip.dir
        pose["look_y"] = 0.1

    @staticmethod
    def _pose_carpet(pose, progress, elapsed, trip):
        fade = envelope(progress, 0, 1, 0.18)
        pose["offset_y"] += -24.0 * fade
        pose["paper_lift"] += 24.0 * fade
        pose["paper_wave"] = 0.7 * fade
        pose["phase"] = elapsed
        pose["rotation"] += 8.0 * trip.dir * fade
        pose["look_x"] = trip.dir * fade
        pose["look_y"] = 0.2 * fade
        pose["happy"] = 1.0 if 0.3 < progress < 0.7 else pose["happy"]
        pose["brow_l"] += 0.5 * fade
        pose["brow_r"] += 0.5 * fade

    @staticmethod
    def _pose_skate(pose, progress, elapsed, trip):
        fade = envelope(progress, 0, 1, 0.15)
        pose["rotation"] += 10.0 * trip.dir * fade
        pose["offset_y"] += -2.0 * abs(math.sin(2 * math.pi * 3 * progress)) * fade
        pose["look_x"] = trip.dir * fade
        pose["brow_l"] += 0.6 * fade
        pose["brow_r"] += 0.6 * fade
        pose["paper_dy"] += 1.0 * math.sin(2 * math.pi * 6 * progress) * fade

    @staticmethod
    def _pose_roll(pose, progress, elapsed, trip):
        fade = envelope(progress, 0, 1, 0.12)
        pose["paper_alpha"] *= 1.0 - fade
        travelled = trip.dist * smooth(progress)
        pose["rotation"] += trip.dir * travelled / (2 * math.pi * 56.0) * 360.0 * fade
        pose["spiral"] = 1.0 if progress > 0.75 and progress < 0.98 else pose["spiral"]
        pose["phase"] = elapsed

    @staticmethod
    def _pose_teleport(pose, progress, elapsed, trip):
        if progress < 0.4:
            grow = smooth(progress / 0.4)
            scale = 1.0 - 0.97 * grow
            pose["sparkle"] = grow
        elif progress < 0.6:
            scale = 0.03
            pose["sparkle"] = 1.0
        else:
            grow = smooth((progress - 0.6) / 0.4)
            scale = 0.03 + 0.97 * grow + 0.12 * math.sin(grow * math.pi * 3) * (1 - grow)
            pose["sparkle"] = 1.0 - grow
        pose["scale_x"] *= scale
        pose["scale_y"] *= scale
        pose["paper_alpha"] *= clamp(scale)
        pose["phase"] = elapsed

    # ------------------------------------------------------ destinations
    def _rect_of(self, widget):
        main_window = self.assistant.mw
        try:
            if widget is None or not widget.isVisible() or widget.window() is not main_window:
                return None
            top_left = widget.mapTo(main_window, QPoint(0, 0))
        except (RuntimeError, AttributeError, TypeError):
            return None
        rect = QRect(top_left, widget.size())
        return rect if rect.width() > 20 and rect.height() > 10 else None

    def destinations(self):
        """Places worth visiting right now, as a list of Place."""
        iface = self.assistant.iface
        out = []
        info = _project_info(iface)

        def add(key, widget, weight, details=None):
            rect = self._rect_of(widget)
            if rect is not None and details is not None:
                out.append(Place(key, rect, weight, details))

        try:
            add(info.get("layers_key", "layers"), iface.layerTreeView(), 2.0, info.get("layers"))
        except AttributeError:
            pass
        save_btn = None
        try:
            save_action = iface.actionSaveProject()
            for button in self.assistant.mw.findChildren(QToolButton):
                if button.defaultAction() is save_action and button.isVisible():
                    save_btn = button
                    break
        except (AttributeError, RuntimeError):
            pass
        if info.get("dirty") is not None:
            add("save_dirty" if info["dirty"] else "save_clean", save_btn, 4.0 if info["dirty"] else 0.5, {})
        try:
            add(info.get("status_key", "statusbar"), self.assistant.mw.statusBar(), 1.0, info.get("status"))
        except AttributeError:
            pass
        try:
            add(info.get("canvas_key", "canvas"), iface.mapCanvas(), 2.0, info.get("canvas"))
        except AttributeError:
            pass
        if info.get("selection"):
            try:
                add("selection", iface.mapCanvas(), 3.0, info["selection"])
            except AttributeError:
                pass
        for dock in self.assistant.mw.findChildren(QDockWidget):
            name = dock.objectName()
            if name == "ProcessingToolbox":
                add("processing", dock, 1.0, {})
            elif name == "Browser":
                add("browser", dock, 0.7, {})
            elif "AttributeTable" in type(dock.widget()).__name__:
                add("attribute", dock, 2.0, info.get("attribute"))
        try:
            message_bar = iface.messageBar()
            if message_bar.currentItem() is not None:
                add("messagebar", message_bar, 2.0, {})
        except (AttributeError, RuntimeError):
            pass
        try:
            add("plugins", iface.pluginToolBar(), 0.4, {})
        except AttributeError:
            pass
        return out

    def _spot(self, rect, key):
        """A position near the edge of rect, inside the main window."""
        char = self.assistant.char
        main_window = self.assistant.mw
        width, height = char.width(), char.height()
        window_width, window_height = main_window.width(), main_window.height()
        center_x, center_y = rect.center().x(), rect.center().y()
        along = self.rng.uniform(0.15, 0.85)
        if key.startswith("canvas") or key == "selection":
            edge = self.rng.choice(("left", "right", "bottom", "top"))
            if edge == "left":
                return QPoint(rect.left() - int(width * 0.3), rect.top() + int((rect.height() - height) * along))
            if edge == "right":
                return QPoint(rect.right() - int(width * 0.7), rect.top() + int((rect.height() - height) * along))
            if edge == "top":
                return QPoint(rect.left() + int((rect.width() - width) * along), rect.top() - int(height * 0.25))
            return QPoint(rect.left() + int((rect.width() - width) * along), rect.bottom() - int(height * 0.8))
        if rect.height() < 80 and center_y > window_height * 0.6:  # status bar
            return QPoint(rect.right() - width - 40, rect.top() - int(height * 0.88))
        if rect.height() < 80 or (rect.width() < 60 and center_y < window_height * 0.3):  # toolbar or button
            return QPoint(center_x - width // 2, rect.bottom() - int(height * 0.22))
        if center_x < window_width / 2:  # left dock: straddle its right edge
            return QPoint(rect.right() - int(width * 0.4), rect.top() + int(max(0, rect.height() - height) * along))
        return QPoint(rect.left() - int(width * 0.6), rect.top() + int(max(0, rect.height() - height) * along))


def _project_info(iface):
    """Facts about the current project for the comments. Empty without QGIS."""
    info = {}
    try:
        from qgis.core import (
            QgsCoordinateReferenceSystem,
            QgsCoordinateTransform,
            QgsProject,
            QgsVectorLayer,
        )

        from .rules import DEFAULT_NAME_RE
    except ImportError:
        return info
    try:
        project = QgsProject.instance()
        layers = list(project.mapLayers().values())
        root = project.layerTreeRoot()
        nodes = root.findLayers()
        hidden = sum(1 for selected in nodes if not selected.isVisible())
        lazy = [map_layer.name() for map_layer in layers if DEFAULT_NAME_RE.match(map_layer.name().strip())]
        info["layers"] = {"count": len(layers), "hidden": hidden, "groups": len(root.findGroups(True)),
                          "name": lazy[-1] if lazy else "", "lazy": len(lazy)}
        if not layers:
            info["layers_key"] = "layers_empty"
        elif len(lazy) >= 2:
            info["layers_key"] = "layers_lazy"
        elif hidden >= 3:
            info["layers_key"] = "layers_hidden"
        info["dirty"] = project.isDirty()

        crs = project.crs()
        info["status"] = {"crs": crs.authid() or crs.description() or "no CRS"}
        if crs.authid() in ("EPSG:3857", "EPSG:900913"):
            info["status_key"] = "statusbar_mercator"
        elif crs.isValid() and crs.isGeographic():
            info["status_key"] = "statusbar_geographic"

        canvas = iface.mapCanvas()
        scale = canvas.scale()
        center = canvas.extent().center()
        lat = lon = None
        try:
            to_wgs84 = QgsCoordinateTransform(canvas.mapSettings().destinationCrs(),
                                        QgsCoordinateReferenceSystem("EPSG:4326"), project)
            center_wgs84 = to_wgs84.transform(center)
            lon, lat = center_wgs84.x(), center_wgs84.y()
        except Exception:  # noqa: BLE001 - without a transform the comment just skips the coordinates
            lat = lon = None
        canvas_info = {"scale": "{:,.0f}".format(scale)}
        if lat is not None:
            canvas_info.update(lat="{:.1f}°{}".format(abs(lat), "N" if lat >= 0 else "S"),
                       lon="{:.1f}°{}".format(abs(lon), "E" if lon >= 0 else "W"))
        info["canvas"] = canvas_info
        if not layers:
            info["canvas_key"] = "canvas_empty"
        elif lat is not None and abs(lat) < 2 and abs(lon) < 2:
            info["canvas_key"] = "canvas_null"
        elif canvas.rotation():
            info["canvas_key"] = "canvas_rotated"
        elif scale < 1000:
            info["canvas_key"] = "canvas_close"
        elif scale > 30_000_000:
            info["canvas_key"] = "canvas_world"
        elif lat is None:
            info["canvas_key"] = "canvas_scale"

        layer = iface.activeLayer()
        if isinstance(layer, QgsVectorLayer):
            info["attribute"] = {"name": layer.name(), "fields": len(layer.fields()),
                                 "features": "{:,}".format(max(0, layer.featureCount()))}
            selected = layer.selectedFeatureCount()
            if selected:
                info["selection"] = {"count": "{:,}".format(selected), "name": layer.name()}
        else:
            info["attribute"] = {"name": "this layer", "fields": "some", "features": "some"}
    except (RuntimeError, AttributeError):
        pass
    return info

