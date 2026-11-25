"""Decimal quantization for newly generated scientific observations."""
from decimal import Decimal, ROUND_FLOOR, ROUND_HALF_UP, localcontext
import math
import re

PRECISION_VERSION = 2
PRECISION_ATTEMPTS = 4
PERCENT_FORMAT = ".4~p"
PERCENT_SPECIFIER = re.compile(r"(?:(?:.)?[<>=^])?[+\-( ]?[$#]?0?\d*,?(?:\.\d+)?~?[%p]")


class PrecisionError(ValueError):
    """The sampled data cannot represent its structure at the target precision."""


def _decimal(value):
    result = Decimal(str(value))
    if not result.is_finite():
        raise PrecisionError("Precision requires a finite value")
    return result


def _number(value):
    if value == value.to_integral_value():
        return int(value)
    result = float(value)
    if not math.isfinite(result) or result == 0:
        raise PrecisionError("Rounded value is outside the numeric range")
    return result


def quantize(value, *, percent=False, fraction=False, places=None):
    """Round decimal ties away from zero and return a JSON number."""
    if type(value) is int and not percent and places is None:
        return value
    number = _decimal(value)
    if not number:
        return 0
    scientific = "e" in str(value).lower()
    exponent = (-4 if fraction else -2) if percent else (
        number.adjusted() - 3 if scientific or abs(number) < 1 else -2)
    if places is not None:
        exponent = max(exponent, -places)
    if number == number.to_integral_value() and not percent and not scientific:
        return int(number)
    with localcontext() as context:
        context.prec = max(28, number.adjusted() - exponent + 2)
        return _number(number.quantize(Decimal(1).scaleb(exponent), rounding=ROUND_HALF_UP))


def ordered_projection(values, *, distinct=False, percent=False, fraction=False):
    """Project once, requiring distinct positions only where the geometry needs them."""
    result = [quantize(value, percent=percent, fraction=fraction) for value in values]
    if distinct and len(set(result)) != len(set(values)):
        raise PrecisionError("Distinct continuous positions coincide after rounding")
    return result


def percentage_parts(values):
    """Apportion 10,000 hundredths of a percentage point by largest remainder."""
    decimals = [_decimal(value) for value in values]
    total = sum(decimals)
    if total <= 0 or any(value < 0 for value in decimals):
        raise PrecisionError("Percentage components require nonnegative values and a positive total")
    quotas = [value * 10_000 / total for value in decimals]
    units = [int(quota.to_integral_value(rounding=ROUND_FLOOR)) for quota in quotas]
    remaining = 10_000 - sum(units)
    order = sorted(range(len(units)), key=lambda i: quotas[i] - units[i], reverse=True)
    for i in order[:remaining]:
        units[i] += 1
    if any(value > 0 and unit == 0 for value, unit in zip(decimals, units)):
        raise PrecisionError("Percentage rounding would erase a positive component")
    return [_number(Decimal(unit).scaleb(-2)) for unit in units]


def percentage_fraction(value):
    return _number(_decimal(value).scaleb(-2))


def interval(center, lower, upper, numbers):
    value, low, high = numbers
    if (not lower <= center <= upper or not low <= value <= high
            or (lower < upper and low == high)):
        raise PrecisionError("Uncertainty interval is invalid after rounding")
    return low, high


def _project_stack(group, percent, fraction, explicit, rounded):
    raw_values = [row["value"] for row in group]
    values = percentage_parts(raw_values) if percent else [rounded(value) for value in raw_values]
    if percent and fraction:
        values = [percentage_fraction(value) for value in values]
    # Reuse shared starts. Keep explicitly offset or diverging source stacks.
    endpoints = {0: Decimal(0)}
    previous_end = Decimal(0)
    for row, value in zip(group, values):
        old_start, old_end = row["value_lower"], row["value_upper"]
        original_start = _decimal(old_start)
        original_end = original_start + _decimal(row["value"])
        start = previous_end if percent else endpoints.get(old_start, _decimal(rounded(old_start)))
        end = start + _decimal(value)
        if explicit and end != _decimal(rounded(end)):
            raise PrecisionError("Stack endpoints require incompatible decimal scales")
        lower, upper = _number(start), _number(end)
        if value and lower == upper:
            raise PrecisionError("Stack segment collapses after rounding")
        row.update(value=value, value_lower=lower, value_upper=upper)
        endpoints[old_end] = endpoints[_number(original_end)] = end
        previous_end = end


def project_rows(kind, rows, *, percent_stack=False, discrete_line_y=False, percent_axes=None):
    """Quantize observations before deriving final plot coordinates."""
    percent_axes = percent_axes or {}
    def rounded(value, axis):
        return quantize(value, percent=axis in percent_axes, fraction=percent_axes.get(axis, False))

    if not kind.startswith("bar"):
        for channel in ("x",) if discrete_line_y else ("x", "y"):
            if all(isinstance(row[channel], (int, float)) for row in rows):
                values = [row[channel] for row in rows]
                projected = ordered_projection(values, distinct=kind.startswith("line") and channel == "x",
                                               percent=channel in percent_axes, fraction=percent_axes.get(channel, False))
                for row, value in zip(rows, projected):
                    row[channel] = row["plot_" + channel] = value
                    if channel == "y" and "value" in row:
                        row["value"] = value
        return

    axis = "x" if kind.startswith("barh") else "y"
    stacked = kind.endswith("_stack")
    if stacked:
        from ordering import needs_stack_endpoints
        explicit = not percent_stack and needs_stack_endpoints(rows)
        groups = {}
        for row in rows:
            groups.setdefault(row["category_id"], []).append(row)
        for group in groups.values():
            _project_stack(group, percent_stack, percent_axes.get(axis, False), explicit,
                           lambda value: rounded(value, axis))
    else:
        for row in rows:
            original = row["value"]
            value = rounded(original, axis)
            if "error_lower" in row:
                lower, upper = row["error_lower"], row["error_upper"]
                lower, upper = interval(original, lower, upper, (value, rounded(lower, axis), rounded(upper, axis)))
                row.update(error_lower=lower, error_upper=upper,
                           error_minus=_number(_decimal(value) - _decimal(lower)),
                           error_plus=_number(_decimal(upper) - _decimal(value)))
            row["value"] = row["value_upper"] = value
    for row in rows:
        lower, upper = row["value_lower"], row["value_upper"]
        row[axis] = row["value"]
        row["plot_" + axis] = (lower + upper) / 2 if stacked else row["value"]
        row["plot_" + axis + "0"], row["plot_" + axis + "1"] = lower, upper


def box_projection(row):
    fields = ("lower", "q1", "median", "q3", "upper")
    projected = ordered_projection([*(row[field] for field in fields), *row["outliers"]])
    lower, q1, median, q3, upper, *outliers = map(_decimal, projected)
    fence = Decimal("1.5") * (q3 - q1)
    if (not q1 - fence <= lower <= q1 <= median <= q3 <= upper <= q3 + fence
            or any(q1 - fence <= value <= q3 + fence for value in outliers)
            or (row["q1"] < row["q3"] and q1 == q3)):
        raise PrecisionError("Box statistics or outliers violate their structure after rounding")
    return {**row, **dict(zip(fields, projected)), "outliers": projected[len(fields):]}


def extension_observations(tables, radial_max=None, stacked=False):
    """Project extension tables before any drawing or export is built."""
    totals = {}
    for table in tables:
        percent = table["percent"]
        places = table.get("places")
        def rounded(value):
            if percent and places is not None:
                value = _decimal(value) / 100
                return quantize(value, percent=True, fraction=True, places=places + 2)
            return quantize(value, percent=percent, fraction=percent, places=places)
        for row in table["rows"]:
            original = row["value"]
            value = rounded(original)
            if "lower" in row:
                lower, upper = row["lower"], row["upper"]
                row["lower"], row["upper"] = interval(original, lower, upper, (value, rounded(lower), rounded(upper)))
            row["value"] = value
            if radial_max is not None:
                if not 0 <= value <= radial_max:
                    raise PrecisionError("Radar observation exceeds the radial scale")
                category = row["category"]
                totals[category] = totals.get(category, Decimal(0)) + _decimal(value)
    if stacked and any(total > _decimal(radial_max) for total in totals.values()):
        raise PrecisionError("Radar stack exceeds the radial scale after rounding")
    return tables
