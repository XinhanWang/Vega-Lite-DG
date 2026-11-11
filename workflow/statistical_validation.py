"""Independent numeric and scenegraph checks for native statistical charts."""
import collections
import math
from decimal import Decimal

from generation.summaries import canonical_numbers, tukey_summary


def validate_statistics(kind, cfg, rows):
    errors = []
    clean_rows = [{key: value for key, value in row.items() if key != "row_id"} for row in rows]
    if clean_rows != canonical_numbers(cfg["rows"]):
        errors.append("Statistical table differs from sampled statistics")
    if [row["category"] for row in rows] != cfg["categories"] or len(set(cfg["categories"])) != len(rows):
        errors.append("Category identity/order mismatch")
    if kind == "pie":
        values = [row["value"] for row in rows]
        if not all(math.isfinite(value) and value > 0 for value in values):
            errors.append("Pie values must be finite and positive")
        if cfg["value_mode"] == "percent" and sum(values) != 100:
            errors.append("Percentage pie must sum to 100")
    else:
        if len(rows) != len(cfg["observations"]):
            errors.append("Summary/observation audit group count mismatch")
        for row, observations in zip(rows, cfg["observations"]):
            expected = tukey_summary(observations)
            if any(row[field] != expected[field] for field in expected):
                errors.append("Summary differs from independently recomputed Tukey statistics")
            lower, q1, median, q3, upper = [row[field] for field in ("lower", "q1", "median", "q3", "upper")]
            if not lower <= q1 <= median <= q3 <= upper:
                errors.append("Invalid five-number summary ordering")
            q1_decimal, q3_decimal = Decimal(str(q1)), Decimal(str(q3))
            fence_low = q1_decimal - Decimal("1.5") * (q3_decimal - q1_decimal)
            fence_high = q3_decimal + Decimal("1.5") * (q3_decimal - q1_decimal)
            if not fence_low <= Decimal(str(lower)) <= Decimal(str(upper)) <= fence_high or any(fence_low <= Decimal(str(value)) <= fence_high for value in row["outliers"]):
                errors.append("Whisker/outlier fence violation")
    return errors


def audit_geometry(kind, cfg, spec, geometry):
    errors = []
    compact = "semantic" not in spec.get("usermeta", {})
    names = {mark["mark_id"]: mark["name"] for mark in geometry["marks"]}
    def elements(prefix):
        if compact:
            if kind == "pie":
                return [element for element in geometry["elements"] if element["mark_type"] == "arc"]
            prefix = {"whiskers_": "layer_0_", "boxes_": "layer_1_", "medians_": "layer_2_", "outliers_": "layer_3_"}[prefix]
        return [element for element in geometry["elements"] if (names[element["mark_id"]] or "").startswith(prefix)]
    rows = spec["data"]["values"]
    categories = [row["category"] for row in rows]
    rows_by_category = {row["category"]: row for row in rows}
    for element in geometry["elements"]:
        datum = element.get("datum") or {}
        original = rows_by_category.get(datum.get("category"))
        if original is not None and any(datum.get(key) != value for key, value in original.items()):
            errors.append("Rendered statistical datum differs from the input table")
            break
    if not compact and spec["encoding"]["color"]["scale"]["domain"] != categories:
        errors.append("Legend domain differs from table order")
    text = [str(item["text"]) for item in geometry["texts"]]
    if (compact and kind == "pie") or (not compact and cfg["show_legend"]):
        legend = [str(item["text"]) for item in geometry["texts"] if item.get("role") == "legend-label"]
        expected_legend = categories
        if kind == "pie" and not compact and cfg["label_mode"] == "legend_value":
            expected_legend = [row["category"] + ": " + f'{row["value"]:g}' + ("%" if cfg["value_mode"] == "percent" else "") for row in rows]
        if legend != expected_legend:
            errors.append("Rendered legend labels/order differ from data.values")
    if kind == "pie":
        sectors = elements("sectors_")
        if [element["datum"]["category"] for element in sectors] != categories:
            errors.append("Arc scenegraph order differs from data.values")
        total = sum(row["value"] for row in rows)
        angle = 0 if compact else cfg["rotation"]
        for row, element in zip(rows, sectors):
            arc = element["arc"]
            extent = row["value"] / total * 2 * math.pi
            start, end = sorted((arc["startAngle"], arc["endAngle"]))
            if abs(start - angle) > 1e-7 or abs(end - angle - extent) > 1e-7:
                errors.append("Rendered sector angles differ from ordered values")
            expected_inner = cfg["size"] * .34 * cfg["hole_ratio"] if not compact and cfg["donut"] else 0
            if abs(arc["innerRadius"] - expected_inner) > 1e-7:
                errors.append("Pie/donut hole mismatch")
            angle += extent
            number = f'{row["value"]:g}' + ("%" if cfg["value_mode"] == "percent" else "")
            expected_text = number if cfg["label_mode"] == "value" else row["category"] + ": " + number
            if not compact and expected_text not in text:
                errors.append("Visible pie value/category label missing: " + expected_text)
        if len(sectors) != len(rows):
            errors.append("Expected one arc per category")
        if not compact and cfg["label_mode"] != "legend_value":
            labels = elements("sector_labels_")
            if [label["datum"]["category"] for label in labels] != categories:
                errors.append("Expected one visible numeric label per sector")
            for sector, label in zip(sectors, labels):
                angle = label["polar"]["theta"]
                midpoint = (sector["arc"]["startAngle"] + sector["arc"]["endAngle"]) / 2
                if abs((angle - midpoint + math.pi) % (2 * math.pi) - math.pi) > 1e-6:
                    errors.append("Numeric label not positioned at its sector midpoint")
    else:
        value_axis = "x" if cfg["orientation"] == "horizontal" else "y"
        category_axis = "y" if value_axis == "x" else "x"
        axis_index = 0 if value_axis == "x" else 1
        scale = geometry["scales"][value_axis]
        domain, positions = scale["domain"], scale["range"]
        def coordinate(value, element):
            fraction = (value - domain[0]) / (domain[-1] - domain[0])
            return (positions[0] + fraction * (positions[-1] - positions[0])) * geometry["source_to_image"]["scale_" + value_axis] + element["group_offset"][axis_index]
        components = (("boxes_", "q1", "q3"), ("whiskers_", "lower", "upper"),
                      ("medians_", "median", None))
        if not compact:
            components += (("cap_lower_", "lower", None), ("cap_upper_", "upper", None))
        for prefix, field, endpoint in components:
            marks = elements(prefix)
            if collections.Counter(element["datum"]["category"] for element in marks) != collections.Counter(categories):
                errors.append("Missing/duplicate component: " + prefix)
            for element in marks:
                datum = element["datum"]
                expected = coordinate(datum[field], element)
                if prefix == "whiskers_":
                    actual = element["anchor"][axis_index]
                    if abs(element["end"][axis_index] - coordinate(datum[endpoint], element)) > 1e-5:
                        errors.append("Whisker endpoint differs from statistics")
                elif endpoint:
                    bounds = sorted((expected, coordinate(datum[endpoint], element)))
                    if max(abs(element["bbox"][axis_index + index * 2] - bounds[index]) for index in (0, 1)) > 1e-5:
                        errors.append("Rendered box bounds differ from quartiles")
                    actual = expected
                else:
                    actual = element["center"][axis_index]
                if abs(actual - expected) > 1e-5:
                    errors.append("Rendered statistic position mismatch: " + field)
        expected = collections.Counter((row["category"], value) for row in rows for value in row["outliers"])
        actual = collections.Counter((element["datum"]["category"], element["datum"]["outlier"]) for element in elements("outliers_"))
        if expected != actual:
            errors.append("Outlier point coverage/multiplicity mismatch")
        for element in elements("outliers_"):
            if abs(element["anchor"][axis_index] - coordinate(element["datum"]["outlier"], element)) > 1e-5:
                errors.append("Outlier position differs from statistic")
        boxes = elements("boxes_")
        locations = [element["center"][1 - axis_index] for element in boxes]
        expected_sort = None if compact else categories
        if locations != sorted(locations) or spec["encoding"][category_axis]["sort"] != expected_sort:
            errors.append("Box category order differs from visible order")
    return errors
