"""Sixteen scatter geometries without a plotting-library dependency."""
from __future__ import annotations

import numpy as np
from .common import limits, numbers
from .template_styles import marker_scatter_1, marker_scatter_n


def points(rng, n, family):
    p, r = rng.py, rng.np
    t = np.linspace(-1, 1, n)
    x = r.uniform(-1, 1, n)
    noise = lambda amount=.1: r.normal(0, amount, n)
    if family == "clustered":
        x, y = r.normal(0, .45, (2, n))
    elif family == "multi_cluster":
        centers = np.asarray([[-.7, -.4], [.6, .55], [-.2, .7]])
        xy = centers[r.integers(0, 3, n)] + r.normal(0, .16, (n, 2))
        x, y = xy.T
    elif family == "correlated":
        y = p.choice((-1, 1)) * x * p.uniform(.5, 1.5) + noise(.17)
    elif family == "curved":
        y = p.choice((-1, 1)) * x ** 2 + noise(.08)
    elif family == "ring":
        theta = r.uniform(0, 2 * np.pi, n)
        radius = r.normal(.8, .06, n)
        x, y = np.cos(theta) * radius, np.sin(theta) * radius
    elif family == "heteroskedastic":
        y = x + noise(.4) * (x + 1.2)
    elif family == "fan":
        x = r.uniform(.05, 1, n)
        y = x * r.uniform(-1, 1, n)
    elif family == "stripe":
        y = r.choice([-.7, 0, .7], n) + noise(.045)
        if p.random() < .5:
            x, y = y, x
    elif family == "stepwise":
        y = np.floor((x + 1) * 2) * .4 + noise(.06)
    elif family == "bimodal":
        mode = r.choice([-1, 1], n)
        x, y = mode * .65 + noise(.18), mode * .4 + noise(.2)
    elif family == "outliers":
        y = x * .6 + noise(.12)
        selection = r.choice(n, max(1, n // 8), replace=False)
        x[selection], y[selection] = r.uniform(-2, 2, (2, len(selection)))
    elif family == "spiral":
        theta = np.linspace(0, p.uniform(3, 6) * np.pi, n)
        radius = np.linspace(.1, 1, n)
        x, y = radius * np.cos(theta) + noise(.03), radius * np.sin(theta) + noise(.03)
    elif family == "crescent":
        theta = r.uniform(.1 * np.pi, 1.5 * np.pi, n)
        x, y = np.cos(theta) + noise(.05), .65 * np.sin(theta) + noise(.05)
    elif family == "grid":
        side = max(2, int(np.ceil(np.sqrt(n))))
        grid = np.asarray(np.meshgrid(np.linspace(-1, 1, side), np.linspace(-1, 1, side))).reshape(2, -1).T
        xy = grid[r.choice(len(grid), n, replace=False)] + r.normal(0, .025, (n, 2))
        x, y = xy.T
    elif family == "bridge":
        x = t + noise(.05)
        y = noise(.06) * np.where(abs(t) > .45, 4, 1)
    elif family == "hourglass":
        y = noise(.55) * np.maximum(abs(x), .04)
    else:
        raise ValueError(f"Unknown scatter family {family}")
    scale = rng.scale()
    # Rotation and unequal axis scales broaden geometry while preserving family.
    angle = p.uniform(-.35, .35)
    x, y = x * np.cos(angle) - y * np.sin(angle), x * np.sin(angle) + y * np.cos(angle)
    return x * scale, y * scale * p.uniform(.65, 1.4)


def sample(rng, kind, count, series_count, family, style, controls):
    p, r = rng.py, rng.np
    counts = ([count] if series_count == 1 else (np.full(series_count, 4) + r.multinomial(count - 4 * series_count, np.full(series_count, 1 / series_count))).tolist())
    xs, ys, local_families = [], [], []
    for s, n in enumerate(counts):
        local_family = family
        x, y = points(rng, n, local_family)
        if series_count > 1:
            x = x + (s - (series_count - 1) / 2) * max(float(np.ptp(x)), .1) * p.uniform(.2, .8)
            y = y + s * max(float(np.ptp(y)), .1) * p.uniform(-.35, .35)
        xs.extend(x.tolist())
        ys.extend(y.tolist())
        local_families.append(local_family)
    xs, ys = numbers(xs), numbers(ys)
    marker_sampler = marker_scatter_1 if series_count == 1 else marker_scatter_n
    sampled = [marker_sampler(p, n) for n in counts]
    markers, sizes, alphas = map(list, zip(*sampled))
    colors = style['series_colors'][:series_count]
    edges = ['none' if marker == '.' or n > 42 else style['text_color'] if p.random() < .45 else color for marker, n, color in zip(markers, counts, colors)]
    widths = [p.uniform(.3, .9) for _ in counts]
    out = {"x": xs, "y": ys, "counts": counts, "starts": np.cumsum([0] + counts[:-1]).tolist(),
           "series_families": local_families, "xlim": limits(xs), "ylim": limits(ys),
           "grid_axis": p.choices(("both", "y", "x"), (.52, .28, .20))[0]}
    if series_count == 1:
        out.update(color=colors[0], marker=markers[0], size=sizes[0], alpha=alphas[0], edgecolor=edges[0], linewidth=widths[0])
    else:
        out.update(colors=colors, markers=markers, sizes=sizes, alphas=alphas, edgecolors=edges, linewidths=widths)
    return out
