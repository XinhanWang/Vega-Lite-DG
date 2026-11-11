"""Short readable labels, unique within an axis and suitable for complete ticks."""
from __future__ import annotations

MONTHS = ("Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec")
WORDS = ("Atlas", "Birch", "Cedar", "Delta", "Elm", "Falcon", "Grove", "Harbor", "Iris", "Juniper", "Kite", "Lake", "Maple", "North", "Oak", "Pine", "Quartz", "River", "South", "Terra", "Urban", "Valley", "West", "Willow", "Amber", "Silver", "Copper", "Indigo", "Summit", "Coastal", "Central", "Forest", "Spring", "Summer", "Autumn", "Winter")
MEASURES = ("Revenue", "Efficiency", "Production", "Accuracy", "Output", "Capacity", "Demand", "Growth", "Response", "Quality", "Energy", "Performance")


def categories(rng, count):
    p = rng.py
    mode = p.choice(("word", "phrase", "year", "month", "quarter", "code", "hybrid", "ordinal"))
    start = p.randint(2010, 2024)
    pool = list(WORDS)
    p.shuffle(pool)
    labels = []
    for i in range(count):
        word = pool[i % len(pool)]
        if mode == "word":
            label = word
        elif mode == "phrase":
            label = f"{p.choice(('North', 'South', 'Upper', 'Lower', 'New', 'Old'))} {word}"
        elif mode == "year":
            label = str(start + i)
        elif mode == "month":
            label = f"{MONTHS[i % 12]} {start + i // 12}"
        elif mode == "quarter":
            label = f"Q{i % 4 + 1} {start + i // 4}"
        elif mode == "code":
            label = f"{p.choice(('A', 'B', 'R', 'T'))}{i + 1:02d}"
        elif mode == "ordinal":
            label = f"Stage {i + 1}"
        else:
            label = f"{word}-{i + 1:02d}"
        if label in labels:
            label = f"{label} {i + 1}"
        labels.append(label)
    return labels


def temporal_labels(rng, count):
    p = rng.py
    mode = p.choice(("month", "month", "quarter", "year"))
    year, start = p.randint(2010, 2024), p.randrange(12 if mode == "month" else 4)
    if mode == "year":
        return [str(year + i) for i in range(count)]
    if mode == "quarter":
        return [f"Q{(start + i) % 4 + 1} {year + (start + i) // 4}" for i in range(count)]
    return [f"{MONTHS[(start + i) % 12]} {year + (start + i) // 12}" for i in range(count)]


def series_names(rng, count, show_legend):
    if not show_legend:
        return [f"Series {i + 1}" for i in range(count)]
    mode = rng.py.choice(("series", "group", "measure", "scenario"))
    pool = list(MEASURES)
    rng.py.shuffle(pool)
    return [f"Series {i + 1}" if mode == "series" else f"Group {chr(65 + i)}" if mode == "group" else pool[i] if mode == "measure" else f"Scenario {chr(65 + i)}" for i in range(count)]


def titles(rng, kind):
    p = rng.py
    measure = p.choice(MEASURES)
    noun = "Comparison" if kind.startswith("bar") else "Trend" if kind.startswith("line") else "Relationship"
    title = f"{measure} {noun}" if p.random() > 0.12 else ""
    xtitle = p.choice(("Category", "Region", "Group", "Condition")) if kind.startswith("bar") else p.choice(("Time", "Period", "Observation")) if kind.startswith("line") else p.choice(("Input", "Feature A", "Concentration", "Measurement X"))
    ytitle = p.choice((measure, f"{measure} (%)", f"{measure} (units)"))
    if kind.startswith("barh"):
        xtitle, ytitle = ytitle, xtitle
    return {"title": title, "x_title": xtitle, "y_title": ytitle,
            "title_loc": p.choice(("left", "center", "right")),
            "title_weight": p.choice(("normal", "normal", "bold")),
            "title_style": "italic" if p.random() < 0.12 else "normal"}
