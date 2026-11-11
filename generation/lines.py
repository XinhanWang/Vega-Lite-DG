"""Line curves and x axes; categorical/calendar ticks always include all points."""
from __future__ import annotations

import numpy as np
from .common import limits, numbers
from .template_styles import line_marks
from .labels import categories, temporal_labels


def curve(rng, count, family, series, total):
    p, r = rng.py, rng.np
    t = np.linspace(0, 1, count)
    phase = p.uniform(0, 2 * np.pi)
    offset = series / max(total - 1, 1)
    if family == "parallel_trend":
        y = .3 + .5 * series + p.choice((-1, 1)) * 1.4 * t
    elif family == "crossing":
        y = .2 + 2 * ((1 - t) if series % 2 else t) + .2 * offset
    elif family == "oscillating":
        y = 1 + np.sin(t * p.uniform(2, 5) * 2 * np.pi + phase) * (.5 + offset)
    elif family == "piecewise":
        y = np.interp(t, [0, .25, .55, .8, 1], r.uniform(-.4, 2, 5))
    elif family == "random_walk":
        y = np.cumsum(r.normal(.03, .25, count)) + offset
    elif family == "spike_event":
        y = .5 + t * .2 + p.uniform(1.5, 3) * np.exp(-((t - p.uniform(.25, .75)) / p.uniform(.03, .09)) ** 2)
    elif family == "decay":
        y = .2 + (1.5 + offset) * np.exp(-t * p.uniform(2, 6))
    elif family == "seasonal":
        y = .6 + 1.2 * t + .4 * np.sin(2 * np.pi * (3 * t + offset))
    elif family == "mean_reverting":
        y = np.zeros(count)
        y[0] = r.normal(.7, .4)
        for i in range(1, count):
            y[i] = .65 * y[i - 1] + .35 * (.8 + offset) + r.normal(0, .15)
    elif family == "logistic":
        y = .1 + (1.6 + offset) / (1 + np.exp(-(t - p.uniform(.35, .65)) * p.uniform(7, 15)))
    elif family == "sawtooth":
        y = .2 + np.mod(t * p.uniform(2, 5) + offset, 1) * 1.8
    else:
        raise ValueError(f"Unknown line family {family}")
    return y + r.normal(0, .025, count)


def sample(rng, kind, count, series_count, family, style, controls):
    p, r = rng.py, rng.np
    mode = controls.get("x_mode", p.choices(("categorical", "temporal", "numeric"), (.48, .28, .24))[0])
    if mode == "numeric":
        scale = rng.scale()
        xs = np.cumsum(r.lognormal(0, .25, count)) * scale
        if p.random() < .25:
            xs -= xs.mean()
        xs = numbers(xs)
        labels = [str(value) for value in xs]
        ticks = numbers(np.linspace(min(xs), max(xs), min(count, p.randint(4, 7))))
        tick_labels = [str(value) for value in ticks]
        xlim = limits(xs)
    else:
        xs = list(range(count))
        labels = temporal_labels(rng, count) if mode == "temporal" else categories(rng, count)
        ticks, tick_labels, xlim = xs[:], labels[:], [-.5, count - .5]
    scale = rng.scale()
    matrix = numbers([curve(rng, count, family, s, series_count) * scale for s in range(series_count)])
    marks = line_marks(p, count, series_count, mode, tick_labels)
    if count == 1:
        marks['markers'] = [marker or 'o' for marker in marks['markers']]
    rotation = marks['x_rotation']
    markers = marks['markers']
    return {"x_mode": mode, "x_values": xs, "x_labels": labels, "tick_positions": ticks,
            "tick_labels": tick_labels, "matrix": matrix, "colors": style["series_colors"][:series_count],
            "markers": markers, "linestyles": marks["linestyles"],
            "marker_sizes": marks["marker_sizes"],
            "markevery": marks["markevery"],
            "alphas": marks["alphas"], "widths": marks["widths"],
            "xlim": xlim, "ylim": limits(matrix), "x_rotation": rotation,
            "x_ha": "center" if rotation == 0 else "right", "grid_axis": p.choices(("y", "both", "x"), (.50, .35, .15) if mode == "numeric" else (.62, .25, .13))[0]}

