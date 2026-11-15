"""Watches QGIS and tells the assistant when there's something to say.

Qlippy only gives advice: nothing in here changes the project.

Sources of events:
- the project (layers added/removed, CRS changes, saving, layouts),
- the Processing history (every algorithm run, its parameters and its log),
- the message log and message bar (errors and warnings),
- the map canvas (slow renders, frantic zooming),
- a once-a-minute check (unsaved work, late nights, long sessions).
"""

import datetime
import re
import time
from collections import deque

from qgis.core import (
    Qgis,
    QgsApplication,
    QgsCoordinateReferenceSystem,
    QgsCoordinateTransform,
    QgsFeatureRequest,
    QgsFeatureSource,
    QgsProject,
    QgsVectorLayer,
)
from qgis.PyQt.QtCore import QDateTime, QObject, QTimer

from . import messages
from .errors import classify_error
from .processing_params import normalize_source, run_inputs, source_variants

# Names QGIS (or a lazy human) gives layers by default.
DEFAULT_NAME_RE = re.compile(
    r"^(new scratch layer|scratch layer|layer|output|output layer|untitled|buffered|clipped|"
    r"reprojected|fixed geometries|dissolved|intersection|difference|merged|centroids|"
    r"union|extracted|joined layer|matching features|vertices|refactored|"
    r"points|lines|polygons)(\s*\(?\d+\)?)?$",
    re.IGNORECASE,
)
INVALID_GEOMETRY_SAMPLE_SIZE = 200
INVALID_GEOMETRY_MAX_FEATURES = 50_000
SPATIAL_INDEX_MIN_FEATURES = 100_000
MANY_LAYERS = 75
MANY_TEMPORARY_LAYERS = 3
SLOW_RENDER_SECONDS = 6.0
PROJECT_LOADING_GRACE_SECONDS = 5.0

# Processing algorithms whose distance parameter is in layer units.
DISTANCE_ALGORITHMS = {
    "native:buffer", "native:singlesidedbuffer", "native:offsetline", "native:multiringconstantbuffer",
    "native:wedgebuffers", "native:taperedbuffer", "native:bufferbym", "native:roundness",
    "gdal:buffervectors", "gdal:onesidebuffer", "gdal:offsetcurve", "native:snapgeometries",
}
DISTANCE_PARAMETERS = ("DISTANCE", "BUFFER", "WIDTH", "TOLERANCE")
FIX_GEOMETRY_ALGORITHMS = {"native:fixgeometries", "qgis:fixgeometries"}
TEMPORARY_OUTPUT = "TEMPORARY_OUTPUT"
# Providers whose feature count is cheap to ask for (no network round trips).
CHEAP_COUNT_PROVIDERS = {"ogr", "memory", "delimitedtext", "spatialite", "virtual", "gpx"}
SCRATCH_NAME_RE = re.compile(r"^(new )?scratch layer(\s*\(?\d+\)?)?$", re.IGNORECASE)
LAYER_REGRET_SECONDS = 20
ERROR_STREAK_COUNT = 3
ERROR_STREAK_WINDOW_SECONDS = 10 * 60

HISTORY_POLL_MS = 3000
HISTORY_LOOKBACK_SECONDS = 15 * 60
REPEAT_RUN_COUNT = 3
REPEAT_RUN_WINDOW_SECONDS = 15 * 60
TEMPORARY_OUTPUTS_BEFORE_NAGGING = 3


class RuleEngine(QObject):
    def __init__(self, iface, assistant, settings, parent=None):
        super().__init__(parent)
        self.iface = iface
        self.assistant = assistant
        self.settings = settings
        self._connections = []
        self._stopped = False
        self._last_fired_at = {}
        self._fired_this_session = set()
        self._project_loading_until = 0.0
        self._project_dirty_since = None
        self._layer_edited_since = {}
        self._render_started_at = None
        self._recent_scales = deque(maxlen=24)
        self._session_started_at = time.monotonic()
        self._pending_layer_ids = []
        self._layer_added_at = {}  # layer id -> time added
        self._recent_errors = deque(maxlen=20)  # times of recent errors
        self._history_registry = None
        self._processing_runs = {}  # history entry id -> entry data
        self._history_timer = QTimer(self)
        self._history_timer.setInterval(HISTORY_POLL_MS)
        self._history_timer.timeout.connect(self._poll_processing_history)
        self._recent_algorithms = deque(maxlen=10)  # (time, algorithm id)
        self._temporary_outputs = 0
        self._minute_timer = QTimer(self)
        self._minute_timer.setInterval(60 * 1000)
        self._minute_timer.timeout.connect(self._check_every_minute)

    # ------------------------------------------------------------ wiring
    def _connect(self, signal, slot):
        signal.connect(slot)
        self._connections.append((signal, slot))

    def start(self):
        project = QgsProject.instance()
        self._connect(project.layersAdded, self._on_layers_added)
        self._connect(project.layersWillBeRemoved, self._on_layers_removed)
        self._connect(project.loadingLayer, self._on_loading_layer)
        self._connect(project.crsChanged, self._on_crs_changed)
        self._connect(project.isDirtyChanged, self._on_dirty_changed)
        self._connect(project.projectSaved, self._on_saved)
        self._connect(project.layoutManager().layoutAdded, self._on_layout_added)
        self._connect(self.iface.projectRead, self._on_project_read)
        self._connect(self.iface.newProjectCreated, self._on_new_project)
        self._connect(self.iface.layoutDesignerWillBeClosed, self._on_layout_designer_closing)
        self._connect(self.iface.messageBar().widgetAdded, self._on_message_bar_item)
        self._connect(QgsApplication.messageLog().messageReceived, self._on_log_message)
        canvas = self.iface.mapCanvas()
        self._connect(canvas.renderStarting, self._on_render_started)
        self._connect(canvas.mapCanvasRefreshed, self._on_render_finished)
        self._connect(canvas.scaleChanged, self._on_scale_changed)
        self._connect_processing_history()
        if project.isDirty():
            self._project_dirty_since = time.monotonic()
        self._minute_timer.start()

    def _connect_processing_history(self):
        """Watch the Processing history (QGIS 3.32+), which records every algorithm run.

        The history registry's entryAdded/entryUpdated signals are NOT used:
        one of their arguments cannot be converted by PyQt6 and every emission
        logs "TypeError: EnumType.__call__() missing 1 required positional
        argument". Polling queryEntries() avoids that.
        """
        try:
            from qgis.gui import QgsGui

            self._history_registry = QgsGui.historyProviderRegistry()
        except (ImportError, AttributeError):
            self._history_registry = None
            return
        # Remember runs that happened before Qlippy started, without commenting on them.
        for entry_id, data in self._recent_processing_entries():
            self._processing_runs[entry_id] = data
        self._history_timer.start()

    def _recent_processing_entries(self):
        """[(entry id, entry data)] for recent Processing runs; empty on any problem."""
        if self._history_registry is None:
            return []
        try:
            since = QDateTime.currentDateTime().addSecs(-HISTORY_LOOKBACK_SECONDS)
            entries = self._history_registry.queryEntries(since, QDateTime(), "processing")
            return [(entry.id, dict(entry.entry or {})) for entry in entries]
        except Exception:  # noqa: BLE001 - an advice plugin must never break QGIS
            self._history_timer.stop()
            return []

    def _poll_processing_history(self):
        for entry_id, data in self._recent_processing_entries():
            known = self._processing_runs.get(entry_id)
            if known is None:
                self._processing_runs[entry_id] = data
                QTimer.singleShot(0, lambda run=data: self._check_processing_run(run))
                if _has_result(data):
                    QTimer.singleShot(400, lambda run=data: self._check_processing_result(run))
            elif not _has_result(known) and _has_result(data):
                self._processing_runs[entry_id] = data
                QTimer.singleShot(0, lambda run=data: self._check_processing_result(run))
        while len(self._processing_runs) > 200:
            self._processing_runs.pop(next(iter(self._processing_runs)))

    def stop(self):
        self._stopped = True
        self._minute_timer.stop()
        self._history_timer.stop()
        for signal, slot in self._connections:
            try:
                signal.disconnect(slot)
            except (TypeError, RuntimeError):
                pass
        self._connections = []

    # ------------------------------------------------------------ firing
    def fire(self, rule_id, **values):
        """Show a rule's message if its level, cooldown and chance allow it."""
        if self._stopped or not self.assistant.is_alive():
            return False
        rule = messages.RULES[rule_id]
        level = self.settings.level
        if level < rule["min_level"] or rule_id in self.settings.disabled_rules:
            return False
        cooldown_key = rule.get("group", rule_id)
        now = time.monotonic()
        # per-level multiplier (Detailed settings > Frequency) x chattiness slider
        cooldown = rule["cooldown"] * self.settings.cooldown_factor(level)
        if now - self._last_fired_at.get(cooldown_key, -1e9) < cooldown:
            return False
        if self.assistant.rng.random() > rule.get("chance", 1.0):
            return False
        text = messages.rule_text(rule_id, level, self.assistant.rng, **values)
        if self.assistant.notify(rule_id, text, title=rule.get("title"), anim=rule.get("anim")):
            self._last_fired_at[cooldown_key] = now
            return True
        return False

    def fire_later(self, delay_ms, rule_id, **values):
        QTimer.singleShot(delay_ms, lambda: self.fire(rule_id, **values))

    def _project_is_loading(self):
        return time.monotonic() < self._project_loading_until

    # ------------------------------------------------------------ layers
    def _on_loading_layer(self, *_):
        self._project_loading_until = time.monotonic() + PROJECT_LOADING_GRACE_SECONDS

    def _on_new_project(self):
        self._project_dirty_since = None
        self._layer_edited_since = {}

    def _on_layers_added(self, layers):
        if self._project_is_loading():
            return
        now = time.monotonic()
        for layer in layers:
            self._layer_added_at[layer.id()] = now
        self._pending_layer_ids.extend(layer.id() for layer in layers)
        QTimer.singleShot(400, self._check_pending_layers)

    def _check_pending_layers(self):
        layer_ids, self._pending_layer_ids = self._pending_layer_ids, []
        project = QgsProject.instance()
        new_layers = [project.mapLayer(layer_id) for layer_id in layer_ids]
        new_layers = [layer for layer in new_layers if layer is not None]
        if not new_layers:
            return
        project_crs = project.crs()
        spatial_layer_count = sum(1 for layer in project.mapLayers().values() if layer.isSpatial())
        for layer in new_layers:
            if self._check_new_layer(layer, project_crs, spatial_layer_count):
                return  # one message per batch is plenty
        if self._check_default_names() or self._check_temporary_layers() or self._check_layer_count():
            return
        for layer in new_layers:
            if self._check_new_layer_name(layer):
                return

    def _check_new_layer(self, layer, project_crs, spatial_layer_count):
        if not layer.isSpatial():
            return False
        name = layer.name()
        crs = layer.crs()
        if not crs.isValid():
            return self.fire("no_crs", name=name)
        if spatial_layer_count > 1 and project_crs.isValid() and crs.authid() != project_crs.authid():
            if self.fire("crs_mismatch", name=name, layer_crs=crs_label(crs), project_crs=crs_label(project_crs)):
                return True
        if self._check_duplicate(layer):
            return True
        if isinstance(layer, QgsVectorLayer):
            if self._check_empty(layer) or self._check_null_island(layer):
                return True
            if self._check_spatial_index(layer) or self._check_invalid_geometries(layer):
                return True
            if is_shapefile(layer) and self.fire("shapefile", name=name):
                return True
        if layer.type() == Qgis.LayerType.Raster and layer.providerType() == "wms":
            source = layer.source().lower()
            if "openstreetmap" in source or "tile.osm.org" in source:
                return self.fire("osm_basemap")
        return False

    def _check_duplicate(self, layer):
        """The same data source is already in the project under another layer."""
        if is_temporary(layer):
            return False
        source = layer.source()
        for other in QgsProject.instance().mapLayers().values():
            if other.id() != layer.id() and other.source() == source:
                return self.fire("duplicate_layer", name=layer.name())
        return False

    def _check_empty(self, layer):
        if layer.providerType() not in CHEAP_COUNT_PROVIDERS or layer.featureCount() != 0:
            return False
        name = layer.name()
        if SCRATCH_NAME_RE.match(name.strip()):
            return self.fire("new_scratch_layer", name=name)
        if is_temporary(layer) or DEFAULT_NAME_RE.match(name.strip()):
            return self.fire("empty_output", name=name)
        return self.fire("empty_layer", name=name)

    def _check_null_island(self, layer):
        """Features crammed around 0°, 0°: usually wrong coordinates or a wrong CRS."""
        if layer.providerType() not in CHEAP_COUNT_PROVIDERS or layer.featureCount() <= 0:
            return False
        try:
            to_wgs84 = QgsCoordinateTransform(layer.crs(), QgsCoordinateReferenceSystem("EPSG:4326"),
                                              QgsProject.instance())
            extent = to_wgs84.transformBoundingBox(layer.extent())
        except Exception:  # noqa: BLE001 - odd CRSs can fail to transform; just skip the check
            return False
        center = extent.center()
        if abs(center.x()) < 1.0 and abs(center.y()) < 1.0 and extent.width() < 2.0 and extent.height() < 2.0:
            return self.fire("null_island_layer", name=layer.name())
        return False

    def _check_new_layer_name(self, layer):
        generic = bool(DEFAULT_NAME_RE.match(layer.name().strip()))
        temporary = is_temporary(layer)
        if generic and temporary:
            return self.fire("generic_temporary_layer", name=layer.name())
        if generic:
            return self.fire("generic_layer_name", name=layer.name())
        if temporary:
            return self.fire("temporary_layer_added", name=layer.name())
        return False

    def _check_spatial_index(self, layer):
        if layer.providerType() != "ogr":
            return False
        feature_count = layer.featureCount()
        if feature_count < SPATIAL_INDEX_MIN_FEATURES:
            return False
        if layer.hasSpatialIndex() != spatial_index_not_present():
            return False
        return self.fire("no_spatial_index", name=layer.name(), count="{:,}".format(feature_count))

    def _check_invalid_geometries(self, layer):
        """Check a small sample of polygons; never scans big layers."""
        if layer.geometryType() != Qgis.GeometryType.Polygon:
            return False
        feature_count = layer.featureCount()
        if feature_count <= 0 or feature_count > INVALID_GEOMETRY_MAX_FEATURES:
            return False
        request = QgsFeatureRequest()
        request.setLimit(INVALID_GEOMETRY_SAMPLE_SIZE)
        request.setNoAttributes()
        invalid = checked = 0
        for feature in layer.getFeatures(request):
            checked += 1
            geometry = feature.geometry()
            if geometry is not None and not geometry.isNull() and not geometry.isGeosValid():
                invalid += 1
        if invalid:
            return self.fire("invalid_geometries", name=layer.name(), count=invalid, sample=checked)
        return False

    def _check_default_names(self):
        names = [layer.name() for layer in QgsProject.instance().mapLayers().values()]
        default_names = [name for name in names if DEFAULT_NAME_RE.match(name.strip())]
        if len(default_names) >= 3:
            return self.fire("lazy_names", count=len(default_names), name=default_names[-1])
        return False

    def _check_temporary_layers(self):
        temporary = [layer for layer in QgsProject.instance().mapLayers().values() if is_temporary(layer)]
        if len(temporary) >= MANY_TEMPORARY_LAYERS:
            return self.fire("many_temporary_layers", count=len(temporary), name=temporary[-1].name())
        return False

    def _check_layer_count(self):
        layer_count = len(QgsProject.instance().mapLayers())
        if layer_count >= MANY_LAYERS:
            return self.fire("many_layers", count=layer_count)
        return False

    def _on_layers_removed(self, layer_ids):
        if self._project_is_loading() or not layer_ids:
            return
        layer = QgsProject.instance().mapLayer(layer_ids[0])
        if layer is not None:
            added_at = self._layer_added_at.get(layer.id())
            seconds = time.monotonic() - added_at if added_at is not None else None
            if seconds is not None and seconds < LAYER_REGRET_SECONDS:
                QTimer.singleShot(200, lambda name=layer.name(), secs=max(1, int(seconds)): (
                    self.fire("layer_regret", name=name, seconds=secs) or self.fire("layer_removed", name=name)))
            else:
                self.fire_later(200, "layer_removed", name=layer.name())
        for layer_id in layer_ids:
            self._layer_edited_since.pop(layer_id, None)
            self._layer_added_at.pop(layer_id, None)

    def _on_project_read(self):
        self._project_loading_until = 0.0
        self._project_dirty_since = None
        self._layer_edited_since = {}
        QTimer.singleShot(2000, self._after_project_read)

    def _after_project_read(self):
        layers = list(QgsProject.instance().mapLayers().values())
        shapefiles = [layer for layer in layers if isinstance(layer, QgsVectorLayer) and is_shapefile(layer)]
        if len(shapefiles) >= 5 and self.fire("many_shapefiles", count=len(shapefiles), files=len(shapefiles) * 5):
            return
        if self._check_layer_count():
            return
        self._check_default_names()

    # ----------------------------------------------------------- project
    def _on_crs_changed(self):
        if self._project_is_loading():
            return
        if QgsProject.instance().crs().authid() in ("EPSG:3857", "EPSG:900913"):
            self.fire("web_mercator")

    def _on_dirty_changed(self, dirty):
        if dirty:
            if self._project_dirty_since is None:
                self._project_dirty_since = time.monotonic()
        else:
            self._project_dirty_since = None

    def _on_saved(self):
        self._project_dirty_since = None
        temporary = [layer for layer in QgsProject.instance().mapLayers().values() if is_temporary(layer)]
        if temporary and self.fire("scratch_on_save", count=len(temporary)):
            return
        self.fire("saved_praise")

    def _on_layout_added(self, _name):
        if self._project_is_loading():
            return
        if len(QgsProject.instance().layoutManager().layouts()) == 1:
            self.fire_later(600, "first_layout")

    def _on_layout_designer_closing(self, designer):
        try:
            layout = designer.layout()
            items = layout.items() if layout is not None else []
        except RuntimeError:
            return
        for item in items:
            family = label_font_family(item)
            if family and family.lower().startswith(("comic sans", "papyrus")):
                self.fire_later(800, "comic_sans", font=family)
                return

    # -------------------------------------------------------- processing
    def _check_processing_run(self, run):
        """Called when an algorithm starts: look at what it was given."""
        algorithm_id = str(run.get("algorithm_id") or "")
        parameters = run_inputs(run.get("parameters") or {})
        if not algorithm_id or not parameters:
            return
        algorithm = algorithm_name(algorithm_id)
        input_layers = layers_from_parameters(parameters)

        # inputs in different CRSs
        crs_ids = sorted({layer.crs().authid() for layer in input_layers
                          if layer.isSpatial() and layer.crs().isValid()})
        if len(crs_ids) > 1 and self.fire("processing_crs_mismatch", algorithm=algorithm,
                                          crs_list=", ".join(crs_ids)):
            return

        # distances in degrees
        if algorithm_id in DISTANCE_ALGORITHMS:
            distance = next((parameters[key] for key in DISTANCE_PARAMETERS if key in parameters), None)
            geographic = [layer for layer in input_layers if layer.isSpatial() and layer.crs().isGeographic()]
            if geographic and _is_positive_number(distance):
                if self.fire("buffer_in_degrees", algorithm=algorithm, name=geographic[0].name(),
                             distance=distance, crs=crs_label(geographic[0].crs())):
                    return

        # temporary outputs
        if any(_is_temporary_output(value) for value in parameters.values()):
            self._temporary_outputs += 1
            if self._temporary_outputs >= TEMPORARY_OUTPUTS_BEFORE_NAGGING:
                if self.fire("processing_temporary_outputs", count=self._temporary_outputs):
                    return

        # the same algorithm again, and again
        now = time.monotonic()
        self._recent_algorithms.append((now, algorithm_id))
        same_recent_runs = [1 for started, run_id in self._recent_algorithms
                            if run_id == algorithm_id and now - started < REPEAT_RUN_WINDOW_SECONDS]
        if len(same_recent_runs) >= REPEAT_RUN_COUNT:
            if self.fire("processing_repeat", algorithm=algorithm, count=len(same_recent_runs)):
                return

        if algorithm_id in FIX_GEOMETRY_ALGORITHMS:
            self.fire("processing_fix_geometries")

    def _check_processing_result(self, run):
        """Called when an algorithm finishes: look at its log and results."""
        algorithm = algorithm_name(str(run.get("algorithm_id") or "an algorithm"))
        log_text = re.sub(r"<[^>]+>", " ", str(run.get("log") or ""))  # the log may be HTML
        log = log_text.lower()
        failed = not run.get("results") and ("execution failed" in log or "error" in log or "cancel" in log)
        if failed and self.report_error(log_text, fallback="processing_error"):
            return
        if "invalid geometr" in log or "has invalid geometry" in log:
            if self.fire("processing_invalid_geometries_log", algorithm=algorithm):
                return
        if run.get("results") and "warning" in log:
            if self.fire("processing_warnings", algorithm=algorithm):
                return
        if run.get("results"):
            self.fire("processing_done", algorithm=algorithm)

    # ---------------------------------------------------------- messages
    def _on_message_bar_item(self, item):
        try:
            level = item.level()
        except (AttributeError, RuntimeError):
            return
        if level == Qgis.MessageLevel.Critical:
            try:
                text = "{}: {}".format(item.title(), item.text())
            except (AttributeError, RuntimeError):
                text = ""
            QTimer.singleShot(300, lambda: self.report_error(text, fallback="error_bar")
                              or self.assistant.react("surprised"))
        elif level == Qgis.MessageLevel.Warning:
            if not self.fire("warning_bar") and self.settings.level >= 1:
                self.assistant.react("nervous")
        elif level == Qgis.MessageLevel.Success:
            if not self.fire("success_bar") and self.settings.level >= 1:
                self.assistant.react("sparkle")

    def _on_log_message(self, message, tag, level):
        if tag == "Qlippy":
            return
        if level == Qgis.MessageLevel.Critical:
            if tag == "Processing":
                QTimer.singleShot(0, lambda text=str(message): self.report_error(text, fallback="processing_error"))
            elif tag == "Python error":
                QTimer.singleShot(0, lambda text=str(message): self.report_error(text, fallback="python_error"))
        elif level == Qgis.MessageLevel.Warning and tag == "Processing":
            if "invalid geometr" in str(message).lower():
                self.fire_later(0, "processing_invalid_geometries_log", algorithm="Processing")

    def report_error(self, text, fallback):
        """Comment on an error: a streak of errors, a recognised kind, or the generic message."""
        now = time.monotonic()
        self._recent_errors.append(now)
        streak = sum(1 for error_time in self._recent_errors if now - error_time < ERROR_STREAK_WINDOW_SECONDS)
        if streak >= ERROR_STREAK_COUNT and self.fire("error_streak", count=streak):
            return True
        kind, error_type, detail = classify_error(text)
        if kind and self.fire(kind, error_type=error_type, detail=detail):
            return True
        return self.fire(fallback, error_type=error_type, detail=detail)

    # ------------------------------------------------------------ canvas
    def _on_render_started(self):
        self._render_started_at = time.monotonic()

    def _on_render_finished(self):
        if self._render_started_at is None:
            return
        seconds = time.monotonic() - self._render_started_at
        self._render_started_at = None
        if seconds >= SLOW_RENDER_SECONDS and not self._project_is_loading():
            self.fire("slow_render", seconds="{:.0f}".format(seconds))

    def _on_scale_changed(self, scale):
        """Zooming in and out repeatedly within a few seconds."""
        now = time.monotonic()
        self._recent_scales.append((now, scale))
        scales = [s for changed_at, s in self._recent_scales if now - changed_at < 10.0]
        if len(scales) < 6:
            return
        direction_changes = 0
        previous_direction = 0
        for before, after in zip(scales, scales[1:]):
            direction = (after > before) - (after < before)
            if direction and previous_direction and direction != previous_direction:
                direction_changes += 1
            if direction:
                previous_direction = direction
        if direction_changes >= 5:
            self._recent_scales.clear()
            self.fire("zoom_thrash")

    # ---------------------------------------------------------- periodic
    def _check_every_minute(self):
        now = time.monotonic()
        project = QgsProject.instance()

        unsaved_threshold = self.settings.unsaved_seconds(self.settings.level)
        if project.isDirty() and self._project_dirty_since is None:
            self._project_dirty_since = now
        if self._project_dirty_since is not None and now - self._project_dirty_since >= unsaved_threshold:
            if self.fire("unsaved_project", minutes=int((now - self._project_dirty_since) // 60)):
                return

        for layer in project.mapLayers().values():
            if not isinstance(layer, QgsVectorLayer):
                continue
            if layer.isEditable() and layer.isModified():
                since = self._layer_edited_since.setdefault(layer.id(), now)
                if now - since >= 10 * 60:
                    if self.fire("uncommitted_edits", name=layer.name(), minutes=int((now - since) // 60)):
                        return
            else:
                self._layer_edited_since.pop(layer.id(), None)

        clock = datetime.datetime.now()
        if (clock.hour >= 23 or clock.hour < 5) and "late_night" not in self._fired_this_session:
            if self.fire("late_night", time=clock.strftime("%H:%M")):
                self._fired_this_session.add("late_night")
                return

        hours = (now - self._session_started_at) / 3600.0
        if hours >= 3 and "long_session" not in self._fired_this_session:
            if self.fire("long_session", hours=int(hours)):
                self._fired_this_session.add("long_session")


# ---------------------------------------------------------------- helpers
def crs_label(crs):
    return crs.authid() or crs.description() or "an unknown CRS"


def is_shapefile(layer):
    if layer.providerType() != "ogr":
        return False
    path = layer.source().split("|")[0].lower()
    return path.endswith(".shp")


def is_temporary(layer):
    return layer.providerType() == "memory"


def spatial_index_not_present():
    presence = getattr(Qgis, "SpatialIndexPresence", None)
    if presence is not None:
        return presence.NotPresent
    return QgsFeatureSource.SpatialIndexPresence.SpatialIndexNotPresent


def label_font_family(item):
    for getter_name in ("textFormat", "font"):
        getter = getattr(item, getter_name, None)
        if getter is None:
            continue
        try:
            value = getter()
            font = value.font() if getter_name == "textFormat" else value
            return font.family()
        except (AttributeError, RuntimeError, TypeError):
            continue
    return None


def algorithm_name(algorithm_id):
    try:
        algorithm = QgsApplication.processingRegistry().algorithmById(algorithm_id)
        if algorithm is not None:
            return algorithm.displayName()
    except (AttributeError, RuntimeError):
        pass
    return algorithm_id


def _layer_from_string(value, project):
    """Resolve a recorded layer value the way Processing itself does."""
    try:
        from qgis.core import QgsProcessingContext, QgsProcessingUtils

        context = QgsProcessingContext()
        context.setProject(project)
        layer = QgsProcessingUtils.mapLayerFromString(value, context, False)
        if layer is not None and project.mapLayer(layer.id()) is not None:
            return layer
    except Exception:  # noqa: BLE001 - any failure here just means "not found"
        return None
    return None


def layers_from_parameters(parameters):
    """Project layers referenced by Processing parameters (ids, sources or names)."""
    project = QgsProject.instance()
    by_source = {}
    by_name = {}
    for layer in project.mapLayers().values():
        by_source.setdefault(normalize_source(layer.source()), layer)
        by_name.setdefault(layer.name(), layer)
    found = []

    def add(value):
        if isinstance(value, (list, tuple)):
            for item in value:
                add(item)
            return
        if isinstance(value, dict):
            add(value.get("source"))
            return
        if hasattr(value, "source") and not isinstance(value, str):
            try:
                add(value.source.staticValue())
            except AttributeError:
                pass
            return
        if not isinstance(value, str) or not value or value == TEMPORARY_OUTPUT:
            return
        layer = project.mapLayer(value) or by_name.get(value)
        if layer is None:
            layer = next((by_source[key] for key in source_variants(value) if key in by_source), None)
        if layer is None:
            layer = _layer_from_string(value, project)
        if layer is not None and layer not in found:
            found.append(layer)

    for value in parameters.values():
        add(value)
    return found


def _has_result(run):
    return bool(run.get("results") or run.get("log"))


def _is_temporary_output(value):
    if isinstance(value, str):
        return value == TEMPORARY_OUTPUT or value.startswith("memory:")
    if isinstance(value, dict):
        return _is_temporary_output(value.get("sink"))
    return False


def _is_positive_number(value):
    try:
        return float(value) > 0
    except (TypeError, ValueError):
        return False
