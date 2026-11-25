"""Decimal precision for newly generated scientific observations."""
from decimal import Decimal, ROUND_HALF_UP, localcontext
import math
import re

PRECISION_VERSION = 1
PERCENT_FORMAT = ".4~p"
PERCENT_SPECIFIER = re.compile(r"(?:(?:.)?[<>=^])?[+\-( ]?[$#]?0?\d*,?(?:\.\d+)?~?[%p]")


def significant(value, digits=4, *, keep_integer=True):
    """Round the decimal spelling, with midpoint ties away from zero."""
    if not math.isfinite(value):
        raise ValueError("Precision requires a finite value")
    if not value or keep_integer and value == int(value):
        return value if value else 0
    decimal = Decimal(str(value))
    with localcontext() as context:
        context.prec = max(24, digits + 1)
        rounded = decimal.quantize(Decimal(1).scaleb(decimal.adjusted() - digits + 1), rounding=ROUND_HALF_UP)
    result = float(rounded)
    return result if result and math.isfinite(result) else value


def ordered_projection(values, accept=lambda _: True, *, fixed=()):
    """Increase precision when rounding would merge or reorder distinct observations."""
    distinct = sorted(set(values))
    fixed = set(fixed)
    for digits in (4, 5, 6, 8, 10, 13, 16):
        projected = [value if value in fixed else significant(value, digits) for value in distinct]
        if all(a < b for a, b in zip(projected, projected[1:])):
            mapping = dict(zip(distinct, projected))
            result = [mapping[value] for value in values]
            if accept(result):
                return result
    return list(values)


def _absolute_stack_endpoints(group):
    """Accumulate adjacent segments in decimal before testing endpoint order."""
    endpoints = []
    previous_upper = None
    adjacent_starts = ()
    for row in group:
        lower = row["value_lower"]
        # A saved next start can be the result of either float or decimal
        # accumulation. Preserve other explicit starts, including small gaps.
        bottom = previous_upper if lower in adjacent_starts else Decimal(str(lower))
        previous_upper = bottom + Decimal(str(row["value"]))
        top = float(previous_upper)
        endpoints.extend((float(bottom), top))
        adjacent_starts = (row["value_upper"], top)
    return endpoints


def project_rows(kind, rows, *, percent_stack=False):
    """Quantize observations before deriving the final plot coordinates."""
    if not kind.startswith("bar"):
        for channel in ("x", "y"):
            if all(isinstance(row[channel], (int, float)) for row in rows):
                values = ordered_projection([row[channel] for row in rows])
                for row, value in zip(rows, values):
                    row[channel] = row["plot_" + channel] = value
                    if channel == "y" and "value" in row:
                        row["value"] = value
        return

    axis = "x" if kind.startswith("barh") else "y"
    stacked = kind.endswith("_stack")
    if stacked and not percent_stack:
        groups = {}
        for row in rows:
            groups.setdefault(row["category_id"], []).append(row)
        for group in groups.values():
            boundaries = ordered_projection(_absolute_stack_endpoints(group))
            for i, row in enumerate(group):
                lower, upper = boundaries[2*i:2*i + 2]
                row.update(value_lower=lower, value_upper=upper,
                           value=float(Decimal(str(upper)) - Decimal(str(lower))))
    elif not stacked:
        values = ordered_projection([row["value"] for row in rows])
        for row, value in zip(rows, values):
            if "error_lower" in row:
                lower, _, upper = ordered_projection(
                    [row["error_lower"], row["value"], row["error_upper"]], fixed=(row["value"],))
                # Round independently sampled limits, then keep the center inside their interval.
                if not lower <= value <= upper:
                    lower, upper = min(lower, value), max(upper, value)
                row.update(error_lower=lower, error_upper=upper,
                           error_minus=value - lower, error_plus=upper - value)
            row["value"] = row["value_upper"] = value
    for row in rows:
        lower, upper = row["value_lower"], row["value_upper"]
        row[axis] = row["value"]
        row["plot_" + axis] = (lower + upper) / 2 if stacked else row["value"]
        row["plot_" + axis + "0"], row["plot_" + axis + "1"] = lower, upper


def box_projection(row):
    fields = ("lower", "q1", "median", "q3", "upper")
    def valid(values):
        lower, q1, median, q3, upper, *outliers = map(lambda value: Decimal(str(value)), values)
        fence = Decimal("1.5") * (q3 - q1)
        return (q1 - fence <= lower <= q1 <= median <= q3 <= upper <= q3 + fence
                and all(value < q1 - fence or value > q3 + fence for value in outliers))

    projected = ordered_projection([*(row[field] for field in fields), *row["outliers"]], valid)
    return {**row, **dict(zip(fields, projected)), "outliers": projected[len(fields):]}
