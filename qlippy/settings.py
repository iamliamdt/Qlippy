"""Persistent settings (QgsSettings, prefix ``qlippy/``)."""

import json

from qgis.core import QgsSettings

PREFIX = "qlippy/"

LEVEL_NAMES = ["Helpful", "Cheeky", "Sassy", "Unhinged"]
LEVEL_DESCRIPTIONS = [
    "Plain, useful tips. No attitude.",
    "Tips with a bit of attitude.",
    "Tips, teasing and unprompted opinions.",
    "Frequent nagging, chaos and easter eggs.",
]
SIZES = [("Small", 0.7), ("Medium", 0.9), ("Large", 1.15)]
IDLE_SLEEP_SECONDS = 300

# "How often Qlippy speaks and acts": multiplies every gap, cooldown and interval.
CHATTINESS = [("Very rarely", 3.0), ("Rarely", 1.8), ("Normal", 1.0), ("Often", 0.6), ("Very often", 0.35)]
DEFAULT_CHATTINESS = 2

# Per Help/Harass level (Helpful, Cheeky, Sassy, Unhinged); editable in Detailed settings.
FREQUENCY_DEFAULTS = {
    "event_gap": [240, 120, 60, 30],          # seconds: minimum gap between comments on events
    "cooldown_factor": [2.5, 1.5, 1.0, 0.5],  # multiplies each comment type's own cooldown
    "remark_min": [30, 15, 7, 2],             # minutes: random remarks/tips at the earliest...
    "remark_max": [60, 30, 15, 6],            # ...and at the latest
    "unsaved_minutes": [20, 15, 10, 5],       # minutes of unsaved changes before a reminder
    "animation_min": [30, 20, 15, 8],         # seconds between random animations, at the earliest...
    "animation_max": [90, 60, 45, 25],        # ...and at the latest
    "wander_min": [12, 8, 6, 3],              # minutes between exploring trips, at the earliest...
    "wander_max": [25, 15, 12, 8],            # ...and at the latest
}
# Chance of walking over to a panel when it opens (at "Normal"; scaled by the slider).
WANDER_EVENT_CHANCE = 0.25
FREQUENCY_LABELS = {
    "event_gap": ("Gap between comments", "s"),
    "cooldown_factor": ("Repeat cooldown multiplier", "\u00d7"),
    "remark_min": ("Random remarks, earliest", "min"),
    "remark_max": ("Random remarks, latest", "min"),
    "unsaved_minutes": ("Unsaved-project reminder after", "min"),
    "animation_min": ("Random animations, earliest", "s"),
    "animation_max": ("Random animations, latest", "s"),
    "wander_min": ("Exploring trips, earliest", "min"),
    "wander_max": ("Exploring trips, latest", "min"),
}

PERSONALITY_DEFAULT = "classic"


class Settings:
    def __init__(self):
        self._s = QgsSettings()

    def _get(self, key, default, typ):
        try:
            return self._s.value(PREFIX + key, default, type=typ)
        except (TypeError, ValueError):
            return default

    def _set(self, key, value):
        self._s.setValue(PREFIX + key, value)

    @property
    def level(self):
        return max(0, min(3, self._get("level", 1, int)))

    @level.setter
    def level(self, value):
        self._set("level", int(value))

    @property
    def visible(self):
        return self._get("visible", True, bool)

    @visible.setter
    def visible(self, value):
        self._set("visible", bool(value))

    @property
    def random_animations(self):
        # stored as the old 0-3 "anim_frequency" value: anything above 0 means on
        return self._get("anim_frequency", 2, int) > 0

    @random_animations.setter
    def random_animations(self, value):
        self._set("anim_frequency", 2 if value else 0)

    @property
    def random_remarks(self):
        return self._get("random_remarks", True, bool)

    @random_remarks.setter
    def random_remarks(self, value):
        self._set("random_remarks", bool(value))

    @property
    def size_index(self):
        return max(0, min(len(SIZES) - 1, self._get("size", 1, int)))

    @size_index.setter
    def size_index(self, value):
        self._set("size", int(value))

    @property
    def scale(self):
        return SIZES[self.size_index][1]

    @property
    def follow_cursor(self):
        return self._get("follow_cursor", True, bool)

    @follow_cursor.setter
    def follow_cursor(self, value):
        self._set("follow_cursor", bool(value))

    @property
    def doze(self):
        return self._get("doze", True, bool)

    @doze.setter
    def doze(self, value):
        self._set("doze", bool(value))

    @property
    def tint(self):
        return self._get("tint", True, bool)

    @tint.setter
    def tint(self, value):
        self._set("tint", bool(value))

    @property
    def wander(self):
        """Wandering on or off (stored as the old 0-3 value: anything above 0 means on)."""
        return self._get("wander", 1, int) > 0

    @wander.setter
    def wander(self, value):
        self._set("wander", 1 if value else 0)

    @property
    def wander_return_home(self):
        return self._get("wander_return_home", True, bool)

    @wander_return_home.setter
    def wander_return_home(self, value):
        self._set("wander_return_home", bool(value))

    @property
    def wander_idle_only(self):
        return self._get("wander_idle_only", False, bool)

    @wander_idle_only.setter
    def wander_idle_only(self, value):
        self._set("wander_idle_only", bool(value))

    @property
    def personality(self):
        return self._get("personality", PERSONALITY_DEFAULT, str) or PERSONALITY_DEFAULT

    @personality.setter
    def personality(self, value):
        self._set("personality", str(value))

    @property
    def chattiness(self):
        return max(0, min(len(CHATTINESS) - 1, self._get("chattiness", DEFAULT_CHATTINESS, int)))

    @chattiness.setter
    def chattiness(self, value):
        self._set("chattiness", int(value))

    @property
    def spacing_factor(self):
        """>1 means Qlippy waits longer between things (less chatty)."""
        return CHATTINESS[self.chattiness][1]

    @property
    def frequency_table(self):
        """The per-level frequency values, defaults filled in for anything not customised."""
        table = {key: list(values) for key, values in FREQUENCY_DEFAULTS.items()}
        try:
            stored = json.loads(self._get("frequency_table", "", str) or "{}")
        except ValueError:
            stored = {}
        for key, values in stored.items():
            if key in table and isinstance(values, list) and len(values) == 4:
                try:
                    table[key] = [max(0.0, float(value)) for value in values]
                except (TypeError, ValueError):
                    pass
        return table

    @frequency_table.setter
    def frequency_table(self, table):
        self._set("frequency_table", json.dumps(table) if table else "")

    def frequency(self, key, level):
        return self.frequency_table[key][max(0, min(3, level))]

    # Effective values (per-level table x chattiness) used by the assistant and rules.
    def event_gap(self, level):
        return self.frequency("event_gap", level) * self.spacing_factor

    def cooldown_factor(self, level):
        return self.frequency("cooldown_factor", level) * self.spacing_factor

    def remark_interval(self, level):
        low = self.frequency("remark_min", level)
        high = max(low, self.frequency("remark_max", level))
        return low * 60 * self.spacing_factor, high * 60 * self.spacing_factor

    def unsaved_seconds(self, level):
        return self.frequency("unsaved_minutes", level) * 60 * self.spacing_factor

    def _interval(self, low_key, high_key, level, unit_seconds):
        low = self.frequency(low_key, level)
        high = max(low, self.frequency(high_key, level))
        return low * unit_seconds * self.spacing_factor, high * unit_seconds * self.spacing_factor

    def animation_interval(self, level):
        """Seconds between random animations, or None when they're switched off."""
        if not self.random_animations:
            return None
        return self._interval("animation_min", "animation_max", level, 1)

    def wander_interval(self, level):
        """Seconds between exploring trips, or None when wandering is off."""
        if not self.wander:
            return None
        return self._interval("wander_min", "wander_max", level, 60)

    def wander_event_chance(self):
        return min(0.9, WANDER_EVENT_CHANCE / self.spacing_factor)

    @property
    def position(self):
        """Relative position (fx, fy) in 0..1 of the free space, or None."""
        x = self._get("pos_x", -1.0, float)
        y = self._get("pos_y", -1.0, float)
        if x < 0 or y < 0:
            return None
        return min(1.0, x), min(1.0, y)

    @position.setter
    def position(self, value):
        if value is None:
            self._s.remove(PREFIX + "pos_x")
            self._s.remove(PREFIX + "pos_y")
        else:
            self._set("pos_x", float(value[0]))
            self._set("pos_y", float(value[1]))

    @property
    def disabled_rules(self):
        value = self._s.value(PREFIX + "disabled_rules", "")
        if isinstance(value, (list, tuple)):
            return {str(x) for x in value if x}
        return {x for x in str(value or "").split(",") if x}

    def disable_rule(self, rule_id):
        rules = self.disabled_rules
        rules.add(rule_id)
        self._set("disabled_rules", ",".join(sorted(rules)))

    def set_disabled_rules(self, rule_ids):
        self._set("disabled_rules", ",".join(sorted(rule_ids)))

    def comment_enabled(self, comment_id):
        return comment_id not in self.disabled_rules

    def reset_disabled_rules(self):
        self._set("disabled_rules", "")
