"""Animation library.

Each animation is a function ``fn(progress, elapsed[, ctx]) -> dict`` that
returns pose overrides (see character.DEFAULT_POSE for the keys):

- progress: how far through the animation we are, 0..1
- elapsed:  seconds since the animation started (for looping effects)
- ctx:      optional details, e.g. {"dir": +1/-1} for which side to react to

The helpers below (envelope, bump, keyframes, smooth) shape values over time.
"""

import math
import random

from . import letters


def clamp(value, low=0.0, high=1.0):
    return low if value < low else high if value > high else value


def smooth(value):
    """Ease-in-out (smoothstep) of a 0..1 value."""
    value = clamp(value)
    return value * value * (3.0 - 2.0 * value)


def envelope(progress, start=0.0, end=1.0, ramp=0.12):
    """0 outside [start, end]; ramps up to 1 over `ramp` after start and back down before end."""
    if progress <= start or progress >= end:
        return 0.0
    return smooth((progress - start) / ramp) * smooth((end - progress) / ramp)


def bump(progress, start, end):
    """A single smooth hump (half a sine wave) between start and end."""
    if progress <= start or progress >= end:
        return 0.0
    return math.sin(math.pi * (progress - start) / (end - start))


def keyframes(progress, points):
    """Smoothly interpolate between keyframes given as [(time, value), ...]."""
    if progress <= points[0][0]:
        return points[0][1]
    for (time_a, value_a), (time_b, value_b) in zip(points, points[1:]):
        if progress <= time_b:
            return value_a + (value_b - value_a) * smooth((progress - time_a) / (time_b - time_a) if time_b > time_a else 1.0)
    return points[-1][1]


def out_bounce(value):
    """Ease-out that bounces like a dropped object (0..1 -> 0..1)."""
    value = clamp(value)
    strength, spread = 7.5625, 2.75
    if value < 1 / spread:
        return strength * value * value
    if value < 2 / spread:
        value -= 1.5 / spread
        return strength * value * value + 0.75
    if value < 2.5 / spread:
        value -= 2.25 / spread
        return strength * value * value + 0.9375
    value -= 2.625 / spread
    return strength * value * value + 0.984375


class Animation:
    def __init__(self, name, label, duration, fn, weight=0.0, min_level=0, loop=False, follow=None,
                 uses_ctx=False, menu=True):
        self.uses_ctx = uses_ctx
        self.menu = menu
        self.name = name
        self.label = label
        self.duration = duration
        self.fn = fn
        self.weight = weight  # weight in the random idle pool (0 = never random)
        self.min_level = min_level
        self.loop = loop
        self.follow = follow  # optional (name, probability) to chain

    def pose(self, progress, elapsed, ctx=None):
        if self.uses_ctx:
            return self.fn(progress, elapsed, ctx or {})
        return self.fn(progress, elapsed)


# ---------------------------------------------------------------- animations
def _look_around(progress, elapsed):
    fade = envelope(progress, 0, 1, 0.1)
    return {
        "look_x": keyframes(progress, [(0, 0), (0.12, -1), (0.38, -1), (0.52, 1), (0.78, 1), (0.92, 0), (1, 0)]),
        "look_y": keyframes(progress, [(0, 0), (0.12, 0.15), (0.38, 0.15), (0.52, -0.2), (0.78, -0.2), (1, 0)]),
        "rotation": keyframes(progress, [(0, 0), (0.12, -3), (0.38, -3), (0.52, 3), (0.78, 3), (1, 0)]),
        "brow_r": 0.5 * envelope(progress, 0.45, 0.85),
        "offset_y": -1.5 * fade,
    }


def _bounce(progress, elapsed):
    bounce_phase = (3.0 * progress) % 1.0
    decay = 1.0 - progress
    near = 1.0 - clamp(min(bounce_phase, 1.0 - bounce_phase) / 0.12)
    return {
        "offset_y": -math.sin(math.pi * bounce_phase) * 16.0 * decay,
        "scale_y": 1.0 - 0.12 * near * decay + 0.05 * (1 - near) * decay,
        "scale_x": 1.0 + 0.08 * near * decay,
    }


def _jump(progress, elapsed):
    air = clamp((progress - 0.2) / 0.45)
    return {
        "offset_y": -46.0 * math.sin(math.pi * air) if 0.2 < progress < 0.65 else 0.0,
        "scale_y": keyframes(progress, [(0, 1), (0.18, 0.8), (0.26, 1.12), (0.55, 1.0), (0.66, 0.82), (0.8, 1.05), (1, 1)]),
        "scale_x": keyframes(progress, [(0, 1), (0.18, 1.12), (0.26, 0.92), (0.55, 1.0), (0.66, 1.12), (0.8, 0.97), (1, 1)]),
        "brow_l": 1.0 * envelope(progress, 0.2, 0.7),
        "brow_r": 1.0 * envelope(progress, 0.2, 0.7),
        "eye_scale": 1.0 + 0.15 * envelope(progress, 0.2, 0.7),
    }


def _spin(progress, elapsed):
    return {
        "rotation": 360.0 * smooth(progress),
        "offset_y": -14.0 * math.sin(math.pi * progress),
        "eye_scale": 1.0 + 0.15 * bump(progress, 0, 1),
    }


def _dizzy(progress, elapsed):
    fade = envelope(progress, 0, 1, 0.1)
    return {
        "spiral": 1.0 if 0.03 < progress < 0.95 else 0.0,
        "stars": fade,
        "rotation": 7.0 * math.sin(2 * math.pi * 2 * progress) * (1 - 0.5 * progress),
        "offset_x": 4.0 * math.sin(2 * math.pi * 1.3 * progress) * fade,
        "brow_tilt": -0.5 * fade,
    }


def _wobble(progress, elapsed):
    decay = 1.0 - progress
    return {
        "rotation": 12.0 * math.sin(2 * math.pi * 3 * progress) * decay,
        "scale_x": 1.0 + 0.04 * math.sin(2 * math.pi * 6 * progress) * decay,
    }


def _nod(progress, elapsed):
    look_down = keyframes(progress, [(0, 0), (0.15, 0.7), (0.35, -0.2), (0.55, 0.7), (0.75, -0.1), (1, 0)])
    return {"look_y": look_down, "offset_y": 3.0 * max(0.0, look_down), "scale_y": 1.0 - 0.04 * max(0.0, look_down),
            "brow_l": 0.3 * envelope(progress), "brow_r": 0.3 * envelope(progress)}


def _shake_head(progress, elapsed):
    fade = envelope(progress, 0, 1, 0.15)
    swing = math.sin(2 * math.pi * 3 * progress)
    return {"look_x": 0.9 * swing * fade, "rotation": 4.0 * swing * fade, "brow_tilt": 0.4 * fade, "squint": 0.2 * fade}


def _surprised(progress, elapsed):
    fade = envelope(progress, 0, 1, 0.08)
    return {
        "eye_scale": 1.0 + 0.3 * fade, "pupil_scale": 1.0 - 0.3 * fade,
        "brow_l": 1.3 * fade, "brow_r": 1.3 * fade,
        "exclaim": envelope(progress, 0, 0.9, 0.08),
        "offset_y": -10.0 * bump(progress, 0.0, 0.25),
        "scale_y": 1.0 + 0.06 * bump(progress, 0.0, 0.25),
    }


def _thinking(progress, elapsed):
    fade = envelope(progress, 0, 1, 0.12)
    return {
        "look_x": -0.7 * fade, "look_y": -0.8 * fade,
        "brow_l": 0.9 * fade, "brow_r": -0.2 * fade,
        "question": envelope(progress, 0.1, 0.95),
        "rotation": -4.0 * fade,
    }


def _idea(progress, elapsed):
    return {
        "bulb": envelope(progress, 0.15, 0.97, 0.1),
        "brow_l": 1.0 * envelope(progress), "brow_r": 1.0 * envelope(progress),
        "eye_scale": 1.0 + 0.15 * envelope(progress, 0.15, 1),
        "offset_y": -8.0 * bump(progress, 0.15, 0.35),
        "look_y": -0.7 * envelope(progress, 0.08, 0.5),
        "look_x": 0.0 if progress < 0.5 else None,
    }


def _suspicious(progress, elapsed):
    fade = envelope(progress, 0, 1, 0.12)
    return {
        "squint": 0.55 * fade, "brow_l": 0.9 * fade, "brow_r": -0.5 * fade,
        "look_x": keyframes(progress, [(0, 0), (0.15, -0.9), (0.45, -0.9), (0.6, 0.9), (0.88, 0.9), (1, 0)]),
        "offset_x": -5.0 * fade, "rotation": -5.0 * fade,
    }


def _annoyed(progress, elapsed):
    fade = envelope(progress, 0, 1, 0.1)
    return {
        "brow_tilt": 1.0 * fade, "squint": 0.3 * fade, "steam": envelope(progress, 0.1, 0.92),
        "offset_x": 1.5 * math.sin(2 * math.pi * 12 * progress) * envelope(progress, 0.1, 0.6),
        "scale_y": 1.0 - 0.04 * fade, "look_x": 0.0, "look_y": 0.1 * fade,
    }


def _laugh(progress, elapsed):
    fade = envelope(progress, 0, 1, 0.06)
    return {
        "happy": fade,
        "offset_y": -abs(math.sin(2 * math.pi * 5 * progress)) * 5.0 * fade,
        "rotation": 3.0 * math.sin(2 * math.pi * 2.5 * progress) * fade,
        "brow_l": 0.6 * fade, "brow_r": 0.6 * fade,
    }


def _eye_roll(progress, elapsed):
    fade = envelope(progress, 0, 1, 0.1)
    roll_angle = math.pi * smooth((progress - 0.1) / 0.55)
    return {
        "look_x": -math.cos(roll_angle) * 0.95 * fade,
        "look_y": -math.sin(roll_angle) * 0.95 * fade,
        "brow_l": keyframes(progress, [(0, 0), (0.3, 0.8), (0.6, 0.8), (0.8, -0.3), (1, 0)]),
        "brow_r": keyframes(progress, [(0, 0), (0.3, 0.8), (0.6, 0.8), (0.8, -0.3), (1, 0)]),
        "lid": 0.4 * envelope(progress, 0.6, 1.0),
        "scale_y": 1.0 - 0.04 * bump(progress, 0.65, 1.0),
    }


def _pin_drop(progress, elapsed):
    fall = out_bounce(progress / 0.45)
    look = keyframes(progress, [(0, -0.9), (0.4, 0.9), (0.75, 0.9), (1, 0)])
    return {
        "pin": envelope(progress, 0, 1, 0.04),
        "pin_drop": 130.0 * (1.0 - fall),
        "look_x": 0.35 * envelope(progress), "look_y": look,
        "brow_l": 0.7 * envelope(progress, 0, 0.5), "brow_r": 0.7 * envelope(progress, 0, 0.5),
        "happy": 1.0 if 0.55 < progress < 0.85 else 0.0,
        "offset_y": -6.0 * bump(progress, 0.55, 0.7),
    }


def _search(progress, elapsed):
    fade = envelope(progress, 0, 1, 0.1)
    magnifier_x = 55.0 + 95.0 * (0.5 - 0.5 * math.cos(2 * math.pi * 1.5 * progress))
    return {
        "mag": fade, "mag_x": magnifier_x, "mag_y": 200.0 + 5.0 * math.sin(2 * math.pi * 2 * progress),
        "look_x": clamp((magnifier_x - 100.0) / 50.0, -1, 1) * fade, "look_y": 0.9 * fade,
        "brow_l": 0.6 * fade, "squint": 0.2 * fade,
    }


def _love(progress, elapsed):
    fade = envelope(progress, 0, 1, 0.1)
    return {"hearts": fade, "blush": fade, "happy": envelope(progress, 0.05, 0.95, 0.05),
            "rotation": 5.0 * math.sin(2 * math.pi * 1.2 * progress) * fade}


def _nervous(progress, elapsed):
    fade = envelope(progress, 0, 1, 0.1)
    return {
        "sweat": fade, "brow_tilt": -0.9 * fade, "eye_scale": 1.0 + 0.08 * fade,
        "look_x": keyframes(progress, [(0, 0), (0.12, -0.8), (0.3, 0.8), (0.48, -0.8), (0.66, 0.8), (0.85, 0), (1, 0)]),
        "offset_x": 0.8 * math.sin(2 * math.pi * 18 * progress) * fade,
    }


def _sad(progress, elapsed):
    fade = envelope(progress, 0, 1, 0.12)
    return {"brow_tilt": -1.0 * fade, "look_y": 0.7 * fade, "scale_y": 1.0 - 0.05 * fade, "offset_y": 3.0 * fade,
            "tears": envelope(progress, 0.2, 1.0), "lid": 0.25 * fade, "rotation": -3.0 * fade}


def _reading(progress, elapsed):
    fade = envelope(progress, 0, 1, 0.1)
    return {"glasses": fade, "look_y": 0.75 * fade,
            "look_x": 0.7 * math.sin(2 * math.pi * 1.5 * progress) * envelope(progress, 0.15, 0.85),
            "brow_l": 0.5 * fade, "brow_r": 0.5 * fade, "offset_y": 2.0 * fade}


def _sparkle(progress, elapsed):
    fade = envelope(progress, 0, 1, 0.1)
    return {"sparkle": fade, "happy": envelope(progress, 0.1, 0.9), "offset_y": -4.0 * bump(progress, 0.1, 0.4),
            "eye_scale": 1.0 + 0.1 * fade}


def _squash(progress, elapsed):
    wobble = math.sin(2 * math.pi * 2.5 * progress) * math.exp(-3.0 * progress)
    return {"scale_y": 1.0 - 0.22 * wobble, "scale_x": 1.0 + 0.15 * wobble}


def _dance(progress, elapsed):
    fade = envelope(progress, 0, 1, 0.08)
    return {
        "offset_y": -abs(math.sin(2 * math.pi * 2 * elapsed)) * 8.0 * fade,
        "rotation": 9.0 * math.sin(2 * math.pi * elapsed) * fade,
        "notes": fade, "happy": envelope(progress, 0.1, 0.9, 0.05),
        "look_x": 0.5 * math.sin(2 * math.pi * elapsed) * fade,
    }


def _tap_glass(progress, elapsed):
    fade = envelope(progress, 0, 1, 0.18)
    taps = sum(bump(progress, start, start + 0.06) for start in (0.3, 0.42, 0.6, 0.72))
    return {
        "scale_x": 1.0 + 0.22 * fade, "scale_y": 1.0 + 0.22 * fade,
        "look_x": 0.0, "look_y": -0.05 * fade,
        "brow_l": 0.6 * fade, "brow_r": 0.6 * fade,
        "eye_scale": 1.0 + 0.1 * fade, "pupil_scale": 1.0 + 0.1 * fade,
        "tap": envelope(progress, 0.25, 0.85), "offset_y": -2.0 * taps, "tail_rot": -35.0 * taps,
    }


def _celebrate(progress, elapsed):
    fade = envelope(progress, 0, 1, 0.08)
    return {"hat": fade, "confetti": envelope(progress, 0.1, 1.0), "happy": envelope(progress, 0.1, 0.9),
            "offset_y": -18.0 * abs(math.sin(2 * math.pi * 1.5 * progress)) * fade,
            "rotation": 5.0 * math.sin(2 * math.pi * 1.5 * progress) * fade,
            "tail_rot": -50.0 * fade + 15.0 * math.sin(2 * math.pi * 3 * progress) * fade}


def sleep_pose(elapsed):
    """Looping pose while asleep (s = seconds asleep)."""
    return {"lid": 1.0, "zzz": 1.0, "scale_y": 1.0 + 0.025 * math.sin(2 * math.pi * elapsed / 3.2),
            "rotation": 6.0, "offset_y": 2.0, "brow_l": -0.3, "brow_r": -0.3, "look_x": 0.0, "look_y": 0.3,
            "blanket": 1.0, "phase": elapsed}


def _doze(progress, elapsed):
    settle = smooth(progress)
    return {
        "lid": keyframes(progress, [(0, 0), (0.3, 0.6), (0.45, 0.3), (0.75, 0.85), (0.85, 0.6), (1, 1)]),
        "rotation": 6.0 * settle, "offset_y": 2.0 * settle, "zzz": smooth((progress - 0.7) / 0.3),
        "brow_l": -0.3 * settle, "brow_r": -0.3 * settle, "look_y": 0.3 * settle,
        "scale_y": 1.0 + 0.06 * bump(progress, 0.1, 0.4),
        "blanket": smooth((progress - 0.55) / 0.35),
    }


def _wake(progress, elapsed):
    return {
        "lid": keyframes(progress, [(0, 1), (0.12, 0)]),
        "eye_scale": 1.0 + 0.3 * envelope(progress, 0.05, 0.8),
        "brow_l": 1.2 * envelope(progress, 0.05, 0.8), "brow_r": 1.2 * envelope(progress, 0.05, 0.8),
        "exclaim": envelope(progress, 0.08, 0.85),
        "offset_y": -12.0 * bump(progress, 0.05, 0.35),
        "rotation": 6.0 * (1.0 - smooth(progress * 3)),
        "blanket": keyframes(progress, [(0, 1), (0.25, 0)]),
    }


def _wave(progress, elapsed):
    fade = envelope(progress, 0, 1, 0.18)
    return {"tail_rot": -75.0 * fade + 22.0 * math.sin(2 * math.pi * 3 * progress) * envelope(progress, 0.15, 0.85),
            "brow_l": 0.5 * fade, "brow_r": 0.5 * fade, "rotation": -4.0 * fade}


def _tap_map(progress, elapsed):
    fade = envelope(progress, 0, 1, 0.12)
    taps = sum(bump(progress, start, start + 0.1) for start in (0.25, 0.45, 0.65))
    return {"tail_rot": 18.0 * taps - 6.0 * fade, "look_x": 0.6 * fade, "look_y": 0.9 * fade,
            "brow_l": 0.4 * fade, "brow_r": 0.4 * fade, "rotation": 3.0 * fade}


def _paper_flutter(progress, elapsed):
    fade = envelope(progress, 0, 1, 0.12)
    return {"paper_curl": fade * (0.7 + 0.5 * math.sin(2 * math.pi * 4 * progress)),
            "paper_dy": -1.2 * math.sin(2 * math.pi * 5 * progress) * fade,
            "look_x": 0.9 * fade, "look_y": 0.7 * fade, "eye_scale": 1.0 + 0.1 * fade,
            "brow_l": 0.8 * fade, "brow_r": 0.8 * fade}


def _enter(progress, elapsed):
    return {"alpha": smooth(progress * 4.0), "offset_y": -170.0 * (1.0 - out_bounce(progress)),
            "scale_y": 1.0 + 0.1 * bump(progress, 0.3, 0.5) - 0.1 * bump(progress, 0.36, 0.5),
            "brow_l": 1.0 * (1 - progress), "brow_r": 1.0 * (1 - progress)}


def _exit(progress, elapsed):
    remaining = 1.0 - smooth(progress)
    return {"scale_x": max(0.001, remaining), "scale_y": max(0.001, remaining), "rotation": -200.0 * smooth(progress),
            "alpha": 1.0 - smooth((progress - 0.4) / 0.6)}


def _land(progress, elapsed):
    wobble = math.exp(-5.0 * progress) * math.cos(2 * math.pi * 2 * progress)
    return {"scale_y": 1.0 - 0.2 * wobble, "scale_x": 1.0 + 0.14 * wobble, "eye_scale": 1.0 + 0.1 * bump(progress, 0, 0.5)}


def _yawn(progress, elapsed):
    fade = envelope(progress, 0.1, 0.75)
    return {"scale_y": 1.0 + 0.1 * fade, "scale_x": 1.0 - 0.04 * fade,
            "lid": keyframes(progress, [(0, 0), (0.2, 0.5), (0.6, 0.8), (0.8, 0.2), (1, 0)]),
            "brow_l": 1.0 * fade, "brow_r": 1.0 * fade, "rotation": -4.0 * fade, "look_y": -0.5 * fade}


def _brow_wiggle(progress, elapsed):
    wiggle = abs(math.sin(2 * math.pi * 2 * progress))
    return {"brow_l": 1.2 * wiggle, "brow_r": 1.2 * wiggle, "eye_scale": 1.0 + 0.05 * wiggle}


def _stare(progress, elapsed):
    fade = envelope(progress, 0, 1, 0.1)
    return {"look_x": 0.0, "look_y": 0.0, "squint": 0.35 * fade, "brow_tilt": 0.4 * fade,
            "scale_x": 1.0 + 0.06 * fade, "scale_y": 1.0 + 0.06 * fade}


def _shuffle(progress, elapsed):
    fade = envelope(progress, 0, 1, 0.1)
    return {"offset_x": 12.0 * math.sin(2 * math.pi * 1.5 * progress) * fade,
            "offset_y": -abs(math.sin(2 * math.pi * 3 * progress)) * 5.0 * fade,
            "rotation": -5.0 * math.cos(2 * math.pi * 1.5 * progress) * fade,
            "look_x": math.cos(2 * math.pi * 1.5 * progress) * fade}


def _sneeze(progress, elapsed):
    build = smooth(progress / 0.55) if progress < 0.55 else 0.0
    burst = bump(progress, 0.55, 0.75)
    return {"scale_y": 1.0 + 0.1 * build - 0.15 * burst, "scale_x": 1.0 + 0.1 * burst,
            "lid": 0.6 * build + (1.0 if 0.55 < progress < 0.7 else 0.0),
            "brow_l": 1.0 * build, "brow_r": 1.0 * build,
            "offset_x": 8.0 * burst, "rotation": -8.0 * build + 10.0 * burst,
            "paper_curl": 0.8 * bump(progress, 0.58, 0.95), "exclaim": envelope(progress, 0.56, 0.9)}


def _peek(progress, elapsed):
    fade = envelope(progress, 0, 1, 0.2)
    return {"scale_y": 1.0 - 0.55 * fade, "offset_y": 0.0, "look_x": keyframes(progress, [(0, 0), (0.3, -0.8), (0.6, 0.8), (0.8, 0)]),
            "eye_scale": 1.0 - 0.1 * fade, "brow_l": 0.6 * fade, "brow_r": 0.6 * fade}


def _shiver(progress, elapsed):
    fade = envelope(progress, 0, 1, 0.1)
    return {"offset_x": 1.4 * math.sin(2 * math.pi * 22 * progress) * fade, "scale_y": 1.0 - 0.05 * fade,
            "brow_tilt": -0.6 * fade, "squint": 0.2 * fade}



# ------------------------------------------------------------- spelling
def _spell_timeline(word):
    shapes = letters.sequence(word)
    n_letters = len(shapes) - 2
    start, trans, hold, bow = 0.3, 0.5, 0.8, 0.8
    duration = start + (len(shapes) - 1) * trans + n_letters * hold + bow
    keyframe_points = [(0.0, 0.0), (start, 0.0)]
    clock = start
    for shape_index in range(1, len(shapes)):
        clock += trans
        keyframe_points.append((clock, float(shape_index)))
        if shape_index < len(shapes) - 1:
            clock += hold
            keyframe_points.append((clock, float(shape_index)))
    keyframe_points.append((duration, float(len(shapes) - 1)))
    return duration, keyframe_points, clock


def _make_spell(word, mood):
    duration, keyframe_points, end_letters = _spell_timeline(word)

    def fn(progress, elapsed):
        morph = keyframes(elapsed, keyframe_points)
        fade = envelope(elapsed / duration, 0.0, 1.0, 0.05)
        out = {"word": float(word), "morph": morph}
        bow = bump(elapsed, end_letters, duration)
        out["rotation"] = 12.0 * bow
        out["offset_y"] = 4.0 * bow
        if mood == "proud":
            out.update(brow_l=0.6 * fade, brow_r=0.6 * fade, happy=1.0 if elapsed > end_letters else 0.0,
                       sparkle=envelope(elapsed / duration, end_letters / duration, 1.0, 0.04))
        elif mood == "smug":
            out.update(brow_l=0.9 * fade, brow_r=-0.2 * fade, squint=0.25 * fade)
        else:  # disgust
            out.update(brow_tilt=-0.5 * fade, squint=0.4 * fade, look_x=-0.8 * fade, look_y=0.3 * fade)
        return out
    return duration, fn


_SPELL_QGIS = _make_spell(0, "proud")
_SPELL_GPKG = _make_spell(1, "smug")
_SPELL_SHP = _make_spell(2, "disgust")


# ------------------------------------------------------------ map tricks
def _fold_map(progress, elapsed):
    fade = envelope(progress, 0, 1, 0.06)
    return {
        "paper_fold1": keyframes(progress, [(0, 0), (0.08, 0), (0.25, 1), (0.55, 1), (0.62, 0.55), (0.68, 0.85),
                              (0.74, 0.4), (0.8, 0.7), (0.92, 0), (1, 0)]),
        "paper_fold2": keyframes(progress, [(0, 0), (0.28, 0), (0.42, 1), (0.5, 1), (0.56, 0.3), (0.6, 0.7), (0.66, 0)]),
        "look_x": 0.5 * fade, "look_y": 0.85 * fade,
        "brow_l": keyframes(progress, [(0, 0), (0.4, 0.8), (0.5, 0.8), (0.55, 0), (1, 0)]),
        "brow_r": keyframes(progress, [(0, 0), (0.4, 0.8), (0.5, 0.8), (0.55, 0), (1, 0)]),
        "brow_tilt": -0.8 * envelope(progress, 0.52, 0.92), "sweat": envelope(progress, 0.55, 0.95),
        "tail_rot": 18.0 * math.sin(2 * math.pi * 6 * progress) * envelope(progress, 0.5, 0.9),
        "happy": 1.0 if 0.43 < progress < 0.52 else 0.0,
    }


def _wave_map(progress, elapsed):
    fade = envelope(progress, 0, 1, 0.15)
    return {"paper_lift": 26.0 * fade, "paper_wave": fade, "paper_rot": 8.0 * math.sin(2 * math.pi * 1.5 * progress) * fade,
            "tail_rot": -40.0 * fade + 10.0 * math.sin(2 * math.pi * 3 * progress) * fade,
            "happy": envelope(progress, 0.2, 0.85), "brow_l": 0.6 * fade, "brow_r": 0.6 * fade, "offset_y": -3.0 * fade}


def _upside_down(progress, elapsed):
    fade = envelope(progress, 0, 1, 0.08)
    flip = keyframes(progress, [(0, 0), (0.08, 0), (0.3, 180), (0.72, 180), (0.94, 360), (1, 360)])
    return {"paper_rot": flip % 360.0, "paper_lift": 14.0 * (bump(progress, 0.06, 0.32) + bump(progress, 0.7, 0.96)),
            "look_y": 0.85 * fade, "look_x": 0.2 * fade, "question": envelope(progress, 0.32, 0.72),
            "rotation": -18.0 * envelope(progress, 0.35, 0.7, 0.08), "brow_l": 0.9 * envelope(progress, 0.3, 0.75), "brow_r": -0.3 * envelope(progress, 0.3, 0.75)}


def _telescope(progress, elapsed):
    fade = envelope(progress, 0.3, 0.8, 0.06)
    return {"paper_roll": keyframes(progress, [(0, 0), (0.25, 0.97), (0.8, 0.97), (1, 0)]),
            "paper_alpha": 1.0 - envelope(progress, 0.24, 0.84, 0.04),
            "telescope": fade, "telescope_ang": -12.0 + 12.0 * math.sin(2 * math.pi * 1.2 * progress),
            "look_x": 0.9 * fade, "look_y": -0.2 * fade + 0.3 * math.sin(2 * math.pi * 1.2 * progress) * fade,
            "squint": 0.45 * fade, "brow_r": 1.0 * fade, "brow_l": -0.4 * fade, "rotation": -6.0 * fade}


def _plane_path(flight):
    x = 100.0 + 78.0 * math.sin(2 * math.pi * flight)
    y = 150.0 - 110.0 * math.sin(math.pi * flight) + 20.0 * math.sin(4 * math.pi * flight)
    return x, y


def _paper_plane(progress, elapsed):
    flight = clamp((progress - 0.2) / 0.6)
    x, y = _plane_path(flight)
    next_x, next_y = _plane_path(min(1.0, flight + 0.01))
    ang = math.degrees(math.atan2(next_y - y, next_x - x)) if flight < 1.0 else 0.0
    plane = envelope(progress, 0.17, 0.84, 0.03)
    return {"paper_fold1": keyframes(progress, [(0, 0), (0.15, 1), (0.84, 1), (1, 0)]),
            "paper_alpha": 1.0 - envelope(progress, 0.15, 0.86, 0.04),
            "plane": plane, "plane_x": x, "plane_y": y, "plane_rot": ang,
            "tail_rot": -60.0 * bump(progress, 0.14, 0.26),
            "look_x": clamp((x - 100.0) / 70.0, -1, 1) * plane if plane > 0 else None,
            "look_y": clamp((y - 88.0) / 70.0, -1, 1) * plane if plane > 0 else None,
            "happy": 1.0 if 0.84 < progress < 0.95 else 0.0, "brow_l": 0.7 * plane, "brow_r": 0.7 * plane}


def _blown_away(progress, elapsed):
    away = keyframes(progress, [(0, 0), (0.05, 0), (0.3, 150), (0.65, 150), (0.95, 0), (1, 0)])
    chase = keyframes(progress, [(0, 0), (0.3, 0), (0.6, 55), (0.68, 55), (0.95, 0)])
    return {"paper_dx": away, "paper_lift": 30.0 * bump(progress, 0.05, 0.3) + 12.0 * envelope(progress, 0.65, 0.95),
            "paper_rot": 200.0 * bump(progress, 0.05, 0.3) - 20.0 * envelope(progress, 0.65, 0.95),
            "paper_wave": 0.8 * (bump(progress, 0.05, 0.3) + envelope(progress, 0.65, 0.95)),
            "offset_x": chase, "offset_y": -abs(math.sin(2 * math.pi * 4 * progress)) * 8.0 * envelope(progress, 0.3, 0.95),
            "exclaim": envelope(progress, 0.05, 0.3), "eye_scale": 1.0 + 0.25 * envelope(progress, 0.05, 0.6),
            "brow_l": 1.2 * envelope(progress, 0.05, 0.65), "brow_r": 1.2 * envelope(progress, 0.05, 0.65),
            "look_x": 1.0 * envelope(progress, 0.05, 0.65), "sweat": envelope(progress, 0.3, 0.65)}


def _route(progress, elapsed):
    fade = envelope(progress, 0, 1, 0.08)
    return {"route": keyframes(progress, [(0, 0), (0.1, 0), (0.8, 1), (1, 1)]) * (1.0 if progress < 0.97 else 0.0),
            "pin": envelope(progress, 0.02, 0.97, 0.04), "pin_drop": 0.0,
            "tail_rot": 14.0 * math.sin(2 * math.pi * 5 * progress) * envelope(progress, 0.1, 0.8),
            "look_x": keyframes(progress, [(0, 0), (0.1, -0.3), (0.5, -0.9), (0.8, -0.6), (1, 0)]) * fade, "look_y": 0.9 * fade,
            "happy": 1.0 if 0.82 < progress < 0.95 else 0.0, "glasses": fade}


def _many_pins(progress, elapsed):
    fade = envelope(progress, 0, 1, 0.08)
    return {"pins_n": keyframes(progress, [(0, 0), (0.05, 0), (0.7, 7.0), (0.85, 7.0), (1.0, 8.5)]),
            "look_x": math.sin(2 * math.pi * 1.5 * progress) * 0.9 * fade, "look_y": 0.8 * fade,
            "tail_rot": 16.0 * abs(math.sin(2 * math.pi * 5 * progress)) * envelope(progress, 0.05, 0.7),
            "happy": 1.0 if 0.72 < progress < 0.88 else 0.0}


# -------------------------------------------------------- click reactions
def _flinch(progress, elapsed, ctx):
    side = ctx.get("dir", 1.0)
    recoil = bump(progress, 0.0, 0.55)
    return {"lid": keyframes(progress, [(0, 0), (0.08, 1), (0.4, 1), (0.6, 0)]), "brow_tilt": 0.6 * recoil,
            "offset_x": -side * 7.0 * recoil, "rotation": -side * 7.0 * recoil, "scale_y": 1.0 - 0.06 * recoil}


def _blink_hard(progress, elapsed):
    return {"lid": keyframes(progress, [(0, 0), (0.12, 1), (0.25, 0), (0.4, 1), (0.55, 0), (1, 0)]),
            "brow_l": keyframes(progress, [(0, 0), (0.12, -0.5), (0.6, 0.8), (1, 0)]),
            "brow_r": keyframes(progress, [(0, 0), (0.12, -0.5), (0.6, 0.8), (1, 0)])}


def _shake_off(progress, elapsed):
    decay = math.exp(-3.0 * progress)
    return {"rotation": 10.0 * math.sin(2 * math.pi * 5 * progress) * decay, "offset_x": 3.0 * math.sin(2 * math.pi * 5 * progress) * decay,
            "squint": 0.4 * bump(progress, 0, 0.5), "brow_tilt": 0.3 * bump(progress, 0, 0.6)}


def _tail_yank(progress, elapsed):
    return {"tail_rot": keyframes(progress, [(0, 0), (0.08, -95), (0.3, -95), (0.45, -60), (0.55, -90), (0.65, -60),
                               (0.75, -90), (1, 0)]),
            "exclaim": envelope(progress, 0.02, 0.4), "look_x": 0.8 * envelope(progress), "look_y": 0.7 * envelope(progress),
            "eye_scale": 1.0 + 0.2 * envelope(progress, 0, 0.5), "brow_l": 1.0 * envelope(progress, 0, 0.5), "brow_r": 1.0 * envelope(progress, 0, 0.5)}


def _boing(progress, elapsed):
    wobble = math.exp(-3.0 * progress) * math.sin(2 * math.pi * 4 * progress)
    return {"scale_y": 1.0 + 0.28 * wobble, "scale_x": 1.0 - 0.16 * wobble, "offset_y": -6.0 * bump(progress, 0, 0.3),
            "eye_scale": 1.0 + 0.15 * abs(wobble), "brow_l": 0.8 * abs(wobble), "brow_r": 0.8 * abs(wobble)}


def _giggle(progress, elapsed):
    fade = envelope(progress, 0, 1, 0.08)
    return {"happy": fade, "blush": fade, "offset_x": 1.5 * math.sin(2 * math.pi * 14 * progress) * fade,
            "rotation": 4.0 * math.sin(2 * math.pi * 3 * progress) * fade, "scale_y": 1.0 + 0.03 * math.sin(2 * math.pi * 14 * progress) * fade}


def _paper_flip(progress, elapsed):
    fade = envelope(progress, 0, 1, 0.1)
    return {"paper_curl": keyframes(progress, [(0, 0), (0.2, 1.4), (0.45, 0.9), (0.6, 1.2), (1, 0)]),
            "look_x": 0.8 * fade, "look_y": 0.8 * fade, "brow_l": 0.9 * fade, "brow_r": 0.9 * fade,
            "eye_scale": 1.0 + 0.15 * fade}


def _pin_here(progress, elapsed, ctx):
    fall = out_bounce(progress / 0.4)
    return {"pin": envelope(progress, 0, 1, 0.05), "pin_drop": 120.0 * (1.0 - fall),
            "pin_lon": ctx.get("lon", 16.37), "pin_lat": ctx.get("lat", 48.21),
            "look_y": keyframes(progress, [(0, -0.6), (0.4, 0.9), (0.85, 0.9), (1, 0)]), "look_x": ctx.get("dir", 0.0) * 0.6,
            "happy": 1.0 if 0.5 < progress < 0.85 else 0.0, "brow_l": 0.6 * envelope(progress, 0, 0.5), "brow_r": 0.6 * envelope(progress, 0, 0.5)}


def _pat_map(progress, elapsed):
    fade = envelope(progress, 0, 1, 0.1)
    taps = sum(bump(progress, start, start + 0.12) for start in (0.15, 0.35, 0.55))
    return {"tail_rot": 22.0 * taps, "look_y": 0.9 * fade, "look_x": 0.5 * fade, "happy": envelope(progress, 0.1, 0.85),
            "rotation": 4.0 * fade, "paper_dy": 1.0 * taps}


def _play_dead(progress, elapsed):
    fall = smooth(elapsed / 0.5)
    return {"rotation": 80.0 * fall, "x_eyes": 1.0 if elapsed > 0.3 else 0.0, "tail_rot": 25.0 * fall,
            "brow_l": -0.4 * fall, "brow_r": -0.4 * fall, "scale_y": 1.0 - 0.15 * bump(min(1.0, elapsed / 0.6), 0.7, 1.0),
            "look_x": 0.0, "look_y": 0.0}


def _get_up(progress, elapsed):
    return {"rotation": 80.0 * (1.0 - smooth(progress / 0.6)) + 6.0 * math.sin(2 * math.pi * 3 * progress) * envelope(progress, 0.5, 1),
            "x_eyes": 1.0 if progress < 0.25 else 0.0, "spiral": 1.0 if 0.25 <= progress < 0.6 else 0.0,
            "tail_rot": 25.0 * (1.0 - smooth(progress / 0.6)), "brow_tilt": 0.5 * envelope(progress, 0.5, 1.0)}

# ------------------------------------------------- peeking around windows
def _peek_around(progress, elapsed, ctx):
    """Lean out from behind a window (ctx['dir'] = +1 if the window is to the right)."""
    side = ctx.get("dir", 1.0)
    lean = keyframes(progress, [(0, 0), (0.15, 1), (0.4, 1), (0.5, 0.2), (0.62, 1), (0.88, 1), (1, 0)])
    return {"rotation": side * 16.0 * lean, "offset_x": side * 10.0 * lean, "scale_y": 1.0 - 0.04 * lean,
            "look_x": side * lean, "look_y": -0.1 * lean,
            "brow_l": 0.9 * lean if side < 0 else 0.3 * lean, "brow_r": 0.9 * lean if side > 0 else 0.3 * lean,
            "eye_scale": 1.0 + 0.1 * lean}


def _knock_window(progress, elapsed, ctx):
    """Knock on the window that's in the way."""
    side = ctx.get("dir", 1.0)
    knocks = sum(bump(progress, start, start + 0.08) for start in (0.3, 0.42, 0.62, 0.74))
    lean = envelope(progress, 0, 1, 0.15)
    return {"rotation": side * 8.0 * lean, "offset_x": side * (6.0 * lean + 3.0 * knocks),
            "tail_rot": -70.0 * lean - 15.0 * knocks if side > 0 else -20.0 * lean,
            "tap": envelope(progress, 0.25, 0.9), "look_x": side * lean, "brow_l": 0.6 * lean, "brow_r": 0.6 * lean}


def _wait_impatiently(progress, elapsed, ctx):
    side = ctx.get("dir", 1.0)
    fade = envelope(progress, 0, 1, 0.1)
    return {"look_x": side * 0.8 * fade, "squint": 0.3 * fade, "brow_tilt": 0.3 * fade,
            "offset_y": -abs(math.sin(2 * math.pi * 3 * progress)) * 3.0 * fade, "tail_rot": 10.0 * abs(math.sin(2 * math.pi * 4 * progress)) * fade}


ANIMATIONS = [
    Animation("look_around", "Look around", 3.2, _look_around, 3),
    Animation("brow_wiggle", "Eyebrow wiggle", 1.4, _brow_wiggle, 3),
    Animation("wave", "Wave", 2.0, _wave, 2),
    Animation("tap_map", "Tap the map", 2.0, _tap_map, 2),
    Animation("bounce", "Bounce", 1.6, _bounce, 2),
    Animation("reading", "Read the map", 3.6, _reading, 2),
    Animation("search", "Magnifying glass", 3.6, _search, 2),
    Animation("thinking", "Think", 3.2, _thinking, 2),
    Animation("pin_drop", "Drop a pin", 2.2, _pin_drop, 2),
    Animation("idea", "Idea", 2.4, _idea, 1),
    Animation("yawn", "Yawn", 2.6, _yawn, 1),
    Animation("paper_flutter", "Paper flutter", 2.2, _paper_flutter, 1),
    Animation("wobble", "Wobble", 1.6, _wobble, 1),
    Animation("spin", "Spin", 1.5, _spin, 1, follow=("dizzy", 0.5)),
    Animation("dizzy", "Dizzy", 2.6, _dizzy, 0.3),
    Animation("dance", "Dance", 3.4, _dance, 1),
    Animation("sparkle", "Sparkle", 1.9, _sparkle, 1),
    Animation("squash", "Squash and stretch", 1.3, _squash, 1),
    Animation("jump", "Jump", 1.3, _jump, 1),
    Animation("nod", "Nod", 1.3, _nod, 1),
    Animation("shake_head", "Shake head", 1.5, _shake_head, 0.5),
    Animation("shuffle", "Shuffle", 2.4, _shuffle, 1),
    Animation("sneeze", "Sneeze", 2.0, _sneeze, 0.7),
    Animation("peek", "Duck and peek", 2.4, _peek, 0.7),
    Animation("shiver", "Shiver", 1.6, _shiver, 0.4),
    Animation("tap_glass", "Tap on the screen", 2.6, _tap_glass, 1, min_level=1),
    Animation("suspicious", "Suspicious", 2.8, _suspicious, 1, min_level=1),
    Animation("eye_roll", "Eye roll", 1.9, _eye_roll, 1, min_level=2),
    Animation("stare", "Stare", 2.6, _stare, 1, min_level=2),
    Animation("laugh", "Laugh", 2.2, _laugh, 0.5),
    Animation("love", "Love", 2.6, _love, 0.4),
    Animation("celebrate", "Celebrate", 3.0, _celebrate, 0.3),
    Animation("surprised", "Surprised", 1.8, _surprised, 0.3),
    Animation("nervous", "Nervous", 2.6, _nervous, 0.3),
    Animation("annoyed", "Annoyed", 2.4, _annoyed, 0.3, min_level=2),
    Animation("sad", "Sad", 2.8, _sad, 0.2),
    Animation("spell_qgis", "Spell QGIS", _SPELL_QGIS[0], _SPELL_QGIS[1], 1.2),
    Animation("spell_gpkg", "Spell GPKG", _SPELL_GPKG[0], _SPELL_GPKG[1], 0.4, min_level=1),
    Animation("spell_shp", "Spell SHP", _SPELL_SHP[0], _SPELL_SHP[1], 0.0),
    Animation("fold_map", "Fold the map", 5.0, _fold_map, 0.8),
    Animation("wave_map", "Wave the map", 3.2, _wave_map, 1),
    Animation("upside_down", "Map upside down", 4.0, _upside_down, 0.8),
    Animation("telescope", "Map telescope", 4.6, _telescope, 1),
    Animation("paper_plane", "Paper plane", 5.0, _paper_plane, 0.8),
    Animation("blown_away", "Map blown away", 4.6, _blown_away, 0.5),
    Animation("route", "Draw a route", 3.6, _route, 1),
    Animation("many_pins", "Pin all the places", 3.4, _many_pins, 0.6),
    Animation("flinch", "Flinch", 0.9, _flinch, uses_ctx=True),
    Animation("blink_hard", "Blink hard", 0.8, _blink_hard),
    Animation("shake_off", "Shake it off", 1.2, _shake_off),
    Animation("tail_yank", "Tail yank", 1.3, _tail_yank),
    Animation("boing", "Boing", 1.4, _boing),
    Animation("giggle", "Giggle", 1.6, _giggle),
    Animation("paper_flip", "Paper flip", 1.4, _paper_flip),
    Animation("pin_here", "Pin here", 1.6, _pin_here, uses_ctx=True, menu=False),
    Animation("pat_map", "Pat the map", 1.8, _pat_map),
    Animation("play_dead", "Play dead", 1.0, _play_dead, loop=True, menu=False),
    Animation("get_up", "Get up", 1.2, _get_up, menu=False),
    Animation("peek_around", "Peek around", 2.8, _peek_around, uses_ctx=True),
    Animation("knock_window", "Knock on the window", 2.2, _knock_window, uses_ctx=True),
    Animation("wait_impatiently", "Wait impatiently", 2.4, _wait_impatiently, uses_ctx=True),
    Animation("doze", "Fall asleep", 2.6, _doze),
    Animation("wake", "Wake up", 1.3, _wake),
    Animation("enter", "Drop in", 1.1, _enter),
    Animation("exit", "Spin out", 0.8, _exit),
    Animation("land", "Land", 0.7, _land),
]

BY_NAME = {animation.name: animation for animation in ANIMATIONS}

# Shown in the "Animate" menu (system animations excluded).
MENU_ANIMATIONS = [animation for animation in ANIMATIONS
                   if animation.menu and animation.name not in ("enter", "exit", "land", "doze", "wake")]


def pick_idle(level, rng=random):
    pool = [animation for animation in ANIMATIONS if animation.weight > 0 and animation.min_level <= level]
    total = sum(animation.weight for animation in pool)
    remaining = rng.uniform(0, total)
    for animation in pool:
        remaining -= animation.weight
        if remaining <= 0:
            return animation
    return pool[-1]
