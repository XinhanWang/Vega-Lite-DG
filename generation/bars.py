"""Single, grouped and stacked bar families with explicit uncertainty."""
from __future__ import annotations

import numpy as np
from .common import limits, numbers
from .controls import HATCHES
from .labels import categories
from .style_rules import choose_weighted


def single_values(rng, n, family):
    p, r = rng.py, rng.np
    t, scale = np.linspace(0, 1, n), rng.scale()
    noise = lambda size=n: r.normal(0, .05, size)
    if family == "balanced":
        y = np.exp(r.normal(0, .23, n))
    elif family == "heavy_tail":
        y = r.pareto(p.uniform(1.2, 2.3), n) + .5
    elif family == "ordered":
        y = np.linspace(.3, p.uniform(2, 5), n) + noise()
    elif family == "signed_mix":
        y = r.normal(.15, 1, n)
        if n > 1:
            y[0], y[-1] = abs(y[0]) + .2, -abs(y[-1]) - .2
    elif family == "sparse":
        y = r.lognormal(0, .5, n) * (r.random(n) > .55)
        y[p.randrange(n)] = p.uniform(.8, 2)
    elif family == "log_spread":
        y = np.geomspace(.01, p.uniform(20, 1000), n) * np.exp(noise())
    elif family == "clustered":
        y = np.take([.35, 1, 2.4], np.minimum(2, (t * 3).astype(int))) + noise()
    elif family == "alternating":
        y = np.where(np.arange(n) % 2, .45, 1.8) + noise()
    elif family == "bimodal":
        y = np.where(r.random(n) < .5, .45, 2) + r.normal(0, .1, n)
    elif family == "staircase":
        y = .3 + np.floor(t * p.randint(3, 6)) * .4 + noise()
    elif family == "plateau":
        y = .3 + np.minimum(t * 3, 1.7) + noise()
    else:
        raise ValueError(f"Unknown single-bar family {family}")
    return y * scale


def grouped_values(rng, m, n, family):
    p, r = rng.py, rng.np
    t, scale = np.linspace(0, 1, n), rng.scale()
    base = r.uniform(.6, 1.3, n)
    result = []
    for s in range(m):
        noise = r.normal(0, .06, n)
        if family == "parallel":
            y = base + .35 * s + .6 * t
        elif family == "crossing":
            y = .4 + (1 - t if s % 2 else t) * p.uniform(1, 3) + .1 * s
        elif family == "dominant":
            y = base * (p.uniform(4, 7) if s == 0 else p.uniform(.4, 1))
        elif family == "mixed_scale":
            y = base * 10 ** (s - m / 2)
        elif family == "composition":
            y = r.gamma(.8 + s * .3, 1, n)
        elif family == "sparse":
            y = base * (r.random(n) > .5)
        elif family == "signed":
            y = (s - (m - 1) / 2) * .6 + np.sin(2 * np.pi * t + s)
        elif family == "alternating":
            y = np.where((np.arange(n) + s) % 2, .4, 1.7) + s * .15
        elif family == "bimodal":
            y = np.where(r.random(n) < .5, .3, 2) * (1 + .15 * s)
        elif family == "staircase":
            y = .3 + np.floor(t * 4 + s * .6) * .4
        elif family == "plateau":
            y = .3 + np.minimum(t * p.uniform(2, 5), 1 + .2 * s)
        else:
            raise ValueError(f"Unknown grouped-bar family {family}")
        result.append(y + noise if family != "sparse" else y)
    matrix = np.asarray(result)
    if family == "composition":
        matrix /= np.maximum(matrix.sum(axis=0), 1e-12)
    if family != "signed":
        matrix = np.maximum(matrix, 0)
    return matrix * scale


def stacked_values(rng, m, n, family, mode):
    p, r = rng.py, rng.np
    t = np.linspace(0, 1, n)
    weights = r.gamma(2 if family == "balanced" else .65, 1, (m, n))
    if family == "dominant":
        weights[p.randrange(m)] += p.uniform(4, 8)
    elif family in {"sparse", "fragmented"}:
        weights *= r.random((m, n)) > (.55 if family == "sparse" else .35)
    elif family == "layered":
        weights = np.asarray([.5 + s / m + .25 * np.sin(t * 2 * np.pi + s) for s in range(m)])
    elif family in {"front_loaded", "back_loaded"}:
        order = np.arange(m) if family == "front_loaded" else np.arange(m)[::-1]
        weights *= np.exp(-order[:, None] * .65)
    elif family == "switchback":
        weights = np.asarray([.2 + (np.sin(t * 4 * np.pi + s * np.pi / max(m - 1, 1)) + 1) for s in range(m)])
    missing = weights.sum(axis=0) == 0
    weights[0, missing] = 1
    weights /= weights.sum(axis=0)
    totals = np.full(n, 100.) if mode == "percent" else rng.scale() * r.lognormal(0, .45, n)
    matrix = np.asarray(numbers(weights * totals), dtype=float)
    if mode == "percent":
        # Rounding must not turn a normalized stack into a 99.99/100.01 stack.
        for i in range(n):
            largest = int(np.argmax(matrix[:, i]))
            matrix[largest, i] += 100 - float(matrix[:, i].sum())
    return matrix


def sample(rng, kind, count, series_count, family, style, controls):
    p = rng.py
    horizontal, stacked, single = kind.startswith("barh"), kind == "barv_stack", kind.endswith("_1")
    labels = categories(rng, count)
    mode = controls.get("stack_mode", p.choice(("absolute", "absolute", "percent")))
    matrix = stacked_values(rng, series_count, count, family, mode) if stacked else single_values(rng, count, family)[None, :] if single else grouped_values(rng, series_count, count, family)
    # Store the actual category order, rather than a sort expression in GT.
    order = np.arange(count)
    if p.random() < .3:
        order = np.argsort(matrix.sum(axis=0))
        if p.random() < .5:
            order = order[::-1]
    labels, matrix = [labels[int(i)] for i in order], matrix[:, order]
    matrix = np.asarray(numbers(matrix), dtype=float)
    if stacked and mode == "percent":
        for i in range(count):
            matrix[int(np.argmax(matrix[:, i])), i] += 100 - float(matrix[:, i].sum())
    if stacked:
        width = p.uniform(.52, .72) if count > 10 else p.uniform(.58, .80)
    elif single:
        width = p.uniform(.48, .68) if count > 18 else p.uniform(.58 if horizontal else .56, .82)
    else:
        width = p.uniform(.68, .84) / (series_count + .25)
    offsets = [(s - (series_count - 1) / 2) * width for s in range(series_count)]
    colors = style["series_colors"][:series_count]
    hatches = [controls.get("hatch", None if p.random() < (.68 if single else .72) else p.choice(HATCHES[1:])) for _ in colors]
    error = None
    if not stacked and controls.get("show_error", p.random() < (.14 if single else .16)):
        error = np.abs(matrix) * rng.np.uniform(.05, .16 if single else .14, matrix.shape) + rng.np.uniform(0, .2 if single else .25, matrix.shape)
    extent = matrix.sum(axis=0) if stacked else np.concatenate((matrix.ravel(), (matrix - error).ravel(), (matrix + error).ravel())) if error is not None else matrix
    domain = limits(extent, zero=True)
    out = {"labels": labels, "linewidth": p.uniform(.65, 1.45), "grid_axis": p.choices(("x", "both", "y") if kind in {"barh_1", "barv_1"} else ("y", "both", "x"), (.68, .22, .10))[0],
           "bar_height" if horizontal else "bar_width": width,
           "xlim" if horizontal else "ylim": domain,
           "ylim" if horizontal else "xlim": [-.65, count - .35],
           "x_rotation": 0,
           "x_ha": "right", "show_error": error is not None,
           "xerr" if horizontal else "yerr": numbers(error[0] if single else error) if error is not None else None,
           "ecolor": style["text_color"] if not single or error is None or p.random() < .5 else colors[0], "capsize": p.randint(2, 5),
           "error_kw": {"elinewidth": p.uniform(.8, 1.6 if single else 1.5), "capthick": p.uniform(.8, 1.6 if single else 1.5)} if error is not None else None}
    if single:
        out.update(values=matrix[0].tolist(), bar_color=colors[0], edgecolor=style["text_color"] if p.random() < .35 else colors[0], alpha=p.uniform(.78, .98), hatch=hatches[0])
    else:
        out.update(matrix=matrix.tolist(), colors=colors,
                   edgecolors=[style["text_color"] if p.random() < .28 else c for c in colors],
                   alphas=[p.uniform(.78, .98) for _ in colors], hatches=hatches,
                   offsets=offsets, group_width=width * (series_count + .25),
                   linewidths=[p.uniform(.6, 1.4) for _ in colors])
    if stacked:
        out.update(stack_mode=mode, bottoms=np.vstack((np.zeros(count), np.cumsum(matrix, axis=0)[:-1])).tolist())
        if mode == "percent":
            out["y_title"] = "Share (%)"
    max_label_len = max(map(len, labels), default=0)
    if kind == 'barv_1':
        out["x_rotation"] = choose_weighted(p, [0, 20, 30, 45, 60], [0.34, 0.2, 0.18, 0.16, 0.12]) if len(labels) > 8 or max((len(label) for label in labels), default=0) > 10 else choose_weighted(p, [0, 15, 25, 35], [0.44, 0.24, 0.18, 0.14])
    elif kind == 'barv_n':
        if count > 8 or max_label_len > 8:
            x_rotation = choose_weighted(p, [20, 30, 40, 50, 60], [0.14, 0.22, 0.24, 0.22, 0.18])
        else:
            x_rotation = choose_weighted(p, [0, 10, 15, 25], [0.34, 0.22, 0.22, 0.22])
        out["x_rotation"] = x_rotation
    elif kind == 'barv_stack':
        if count > 10 or max_label_len > 10:
            x_rotation = choose_weighted(p, [20, 30, 40, 50, 60], [0.1, 0.22, 0.24, 0.22, 0.22])
        else:
            x_rotation = choose_weighted(p, [0, 10, 15, 25], [0.38, 0.22, 0.2, 0.2])
        out["x_rotation"] = x_rotation
    out["x_ha"] = ("center" if count <= 8 and max_label_len <= 10 else "right") if kind == "barv_1" else "center" if out["x_rotation"] == 0 else "right"
    return out
