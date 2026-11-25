"""Independent numeric and scenegraph checks for native statistical charts."""
import collections
import math
from decimal import Decimal

from generation.summaries import canonical_numbers, tukey_summary


def validate_statistics(kind, cfg, rows, outliers=None, *, precision_v1=False):
    errors = []
    clean_rows = [{key: value for key, value in row.items() if key != "row_id"} for row in rows]
    if kind == "boxplot" and outliers is not None:
        for row in clean_rows:
            row["outliers"] = [point["value"] for point in outliers if point["category"] == row["category"]]
    from statistical import final_rows
    expected_rows = final_rows(kind, cfg, precision_v1)
    if kind == "pie" and cfg["value_mode"] == "percent":
        expected_rows = [dict(row, value=float(Decimal(str(row["value"])) / 100)) for row in expected_rows]
    if clean_rows != expected_rows:
        errors.append("Statistical table differs from sampled statistics")
    if [row["category"] for row in rows] != cfg["categories"] or len(set(cfg["categories"])) != len(rows):
        errors.append("Category identity/order mismatch")
    if kind == "pie":
        from statistical import pie_value_error
        error = pie_value_error([row["value"] for row in rows], 1 if cfg["value_mode"] == "percent" else None)
        if error is not None:
            errors.append(error)
    else:
        if len(rows) != len(cfg["observations"]):
            errors.append("Summary/observation audit group count mismatch")
        for row, observations in zip(clean_rows, cfg["observations"]):
            expected = tukey_summary(observations)
            if precision_v1:
                from precision import box_projection
                expected = box_projection(canonical_numbers(expected))
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
    flattened_marks = {element["mark_id"] for element in elements("outliers_")} if kind == "boxplot" else set()
    for element in geometry["elements"]:
        datum = element.get("datum") or {}
        original = rows_by_category.get(datum.get("category"))
        flattened = element["mark_id"] in flattened_marks
        if original is not None and not flattened and any(datum.get(key) != value for key, value in original.items()
                                        if not (flattened and key == "outliers")):
            errors.append("Rendered statistical datum differs from the input table")
            break
    if not compact and spec["encoding"]["color"]["scale"]["domain"] != categories:
        errors.append("Legend domain differs from table order")
    text = [str(item["text"]) for item in geometry["texts"]]
    from statistical import pie_label
    percent_format = spec.get("usermeta", {}).get("semantic", {}).get("options", {}).get("percent_format")
    def pie_number(row):
        return pie_label(row["value"], cfg["value_mode"] == "percent", percent_format)

    if (compact and kind == "pie") or (not compact and cfg["show_legend"]):
        legend = [str(item["text"]) for item in geometry["texts"] if item.get("role") == "legend-label"]
        expected_legend = categories
        if kind == "pie" and not compact:
            expected_legend = [
                row["category"] + ": " + pie_number(row)
                if cfg["label_mode"] == "legend_value" or row["value"] == 0 else row["category"]
                for row in rows]
        legend_matches = collections.Counter(legend) == collections.Counter(expected_legend) if compact else legend == expected_legend
        if not legend_matches:
            errors.append("Rendered legend labels/order differ from data.values")
    if kind == "pie":
        sectors = elements("sectors_")
        positive_rows = [row for row in rows if row["value"] > 0]
        positive_categories = [row["category"] for row in positive_rows]
        arc_categories = [element["datum"]["category"] for element in sectors]
        if not compact and arc_categories != positive_categories:
            errors.append("Arc scenegraph order differs from data.values")
        if compact:
            counts = collections.Counter(arc_categories)
            if (set(counts) - rows_by_category.keys() or any(count != 1 for count in counts.values())
                    or any(category not in counts for category in positive_categories)):
                errors.append("Arc categories differ from data.values")
        total = sum(row["value"] for row in rows)
        if total <= 0:
            return errors + ["Pie values must have a positive total"]
        angle = 0 if compact else cfg["rotation"]
        for element in sectors:
            row = rows_by_category.get(element["datum"]["category"])
            if row is None:
                continue
            arc = element["arc"]
            extent = row["value"] / total * math.tau
            start, end = sorted((arc["startAngle"], arc["endAngle"]))
            extent_matches = abs(end - start - extent) <= 1e-7
            if not extent_matches or (not compact and abs(start - angle) > 1e-7):
                errors.append("Rendered sector angles differ from ordered values")
            expected_inner = cfg["size"] * .34 * cfg["hole_ratio"] if not compact and cfg["donut"] else 0
            if abs(arc["innerRadius"] - expected_inner) > 1e-7:
                errors.append("Pie/donut hole mismatch")
            angle += extent
            number = pie_number(row)
            expected_text = number if cfg["label_mode"] == "value" else row["category"] + ": " + number
            if not compact and expected_text not in text:
                errors.append("Visible pie value/category label missing: " + expected_text)
        if not compact and cfg["label_mode"] != "legend_value":
            labels = elements("sector_labels_")
            if [label["datum"]["category"] for label in labels] != positive_categories:
                errors.append("Expected one visible numeric label per positive sector")
            for sector, label in zip(sectors, labels):
                angle = label["polar"]["theta"]
                midpoint = (sector["arc"]["startAngle"] + sector["arc"]["endAngle"]) / 2
                if abs((angle - midpoint + math.pi) % (2 * math.pi) - math.pi) > 1e-6:
                    errors.append("Numeric label not positioned at its sector midpoint")
        if not compact:
            zero_text = [row["category"] + ": " + pie_number(row) for row in rows if row["value"] == 0]
            if zero_text:
                visible = [item for item in geometry["texts"] if item.get("drawable")]
                if cfg["show_legend"]:
                    labels = [item["text"] for item in visible if item.get("role") == "legend-label"]
                    if any(label not in labels for label in zero_text):
                        errors.append("Visible zero-value pie legend label missing")
                else:
                    labels = [item for item in visible if (item.get("mark_name") or "").startswith("zero_labels_")]
                    if [item["text"] for item in labels] != zero_text:
                        errors.append("Visible zero-value pie data labels differ from data.values")
                    if any(a["bbox"][3] > b["bbox"][1] for a, b in zip(labels, labels[1:])):
                        errors.append("Zero-value pie data labels overlap")
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
        from statistical import outlier_rows
        expected = collections.Counter((point["category"], point["value"]) for point in outlier_rows(spec))
        outlier_field = "value"
        actual = collections.Counter((element["datum"]["category"], element["datum"][outlier_field]) for element in elements("outliers_"))
        if expected != actual:
            errors.append("Outlier point coverage/multiplicity mismatch")
        for element in elements("outliers_"):
            if abs(element["anchor"][axis_index] - coordinate(element["datum"][outlier_field], element)) > 1e-5:
                errors.append("Outlier position differs from statistic")
        boxes = elements("boxes_")
        locations = [element["center"][1 - axis_index] for element in boxes]
        expected_sort = None if compact else categories
        if locations != sorted(locations) or spec["encoding"][category_axis]["sort"] != expected_sort:
            errors.append("Box category order differs from visible order")
    return errors
