"""Optional deterministic sampling knobs shared by native and extension runs."""
from __future__ import annotations

import hashlib
import math

from .controls import KINDS, normalize_controls

EXTENSIONS = {"radar", "combination"}
LABEL_KINDS = {kind for kind in KINDS if kind.startswith(("bar", "line"))} | {"pie", "combination", "radar"}
CJK_NAME = "Noto Sans CJK SC"
CJK_FILE = "NotoSansCJKsc-Regular.otf"

RADAR_SERIES_LIMITS = ((8, 8), (15, 6), (23, 4), (36, 3))
RADAR_LABEL_FACTORS = ((24, 1), (48, .5), (72, .2))
RADAR_BAR_VARIANTS = {"polar_bar", "stacked_polar_bar"}
RADAR_LINE_STYLE = {"closed", "point", "dashed", "stroke_width"}
RADAR_PATTERNS = ("random", "correlated", "peaked", "spiky", "smooth", "flat")
RADAR_VARIANTS = ("line", "filled", "polar_bar", "stacked_polar_bar")
EXTENSION_PROFILES = ("publication_clean", "compact_report", "monochrome_minimal",
                      "colorful_analytic", "editorial", "dark_contrast")

# (lower, upper, integer) in workload-safe units. Ranges narrow these limits.
EXTENSION_RANGES = {
    "radar": {"category_count": (4, 36, True), "series_count": (1, 8, True),
              "rotation": (-180, 180, False), "stroke_width": (1, 3.2, False),
              "radial_exponent": (-1, 4, True), "tick_count": (3, 8, True)},
    "combination": {"category_count": (4, 18, True), "bar_series_count": (1, 3, True),
                    "line_series_count": (1, 3, True), "rotation": (-38, 0, False),
                    "stroke_width": (1.35, 3, False), "opacity": (.74, 1, False)},
}
ASPECT_LIMIT = (.6, 3, False)


def ranges_for(kind):
    if kind in EXTENSIONS:
        return EXTENSION_RANGES[kind]
    if kind in {"pie", "boxplot"}:
        return {"category_count": (2, 8, True)}
    ranges = {}
    if kind.startswith("bar"):
        ranges["category_count"] = (4, 24 if kind.endswith("_1") else 16, True)
    elif kind.startswith("line"):
        ranges["point_count"] = (6, 30 if kind.endswith("_1") else 24, True)
    else:
        ranges["point_count"] = (12, 48 if kind.endswith("_n") else 60, True)
    if not kind.endswith("_1"):
        ranges["series_count"] = (2, 6 if kind.endswith("_stack") else 5, True)
    return ranges


def _range_valid(value, limits):
    low, high, integer = limits
    return (type(value) in ({int} if integer else {int, float})
            and math.isfinite(value) and low <= value <= high)


def validate_extension_controls(kind, controls):
    for key, value in controls.items():
        limits = {"aspect_ratio": ASPECT_LIMIT, **ranges_for(kind)}.get(key)
        if limits is not None:
            if _range_valid(value, limits) and not (kind == "radar" and key == "rotation" and value == 180):
                continue
        elif key == "radial_max" and kind == "radar":
            if type(value) in {int, float} and math.isfinite(value) and value > 0:
                continue
        else:
            options = {"profile": EXTENSION_PROFILES}
            if kind == "radar":
                options.update(variant=RADAR_VARIANTS, layout=("overlay",), grid=("polygon", "circle"),
                               data_pattern=RADAR_PATTERNS, per_dimension_scale=(False,),
                               **{key: (True, False) for key in ("closed", "point", "dashed")})
            else:
                options.update(dual_axis=(True, False), error_bars=(True, False), point=(True, False), dashed=(True, False))
            if any(type(value) is type(choice) and value == choice for choice in options.get(key, ())):
                continue
        raise ValueError(f"Invalid extension choice: {kind}.{key}={value!r}")

# Domain vocabularies are original synthetic text. No benchmark labels are sampled.
THEMES = (
    ("降水", "降水量 (mm)", "观测站", ("沿海", "山区", "城区", "郊区", "河谷", "高原", "平原", "湖区")),
    ("客运", "客流量 (万人次)", "线路", ("城北", "城南", "城西", "城东", "中心城", "机场", "高铁站", "大学城")),
    ("能源", "用电量 (MWh)", "区域", ("工业区", "商业区", "居民区", "开发区", "港区", "物流园", "科技园", "新城区")),
    ("实验测量", "浓度 (mg/L)", "样品", ("对照组", "低剂量", "中剂量", "高剂量", "预实验", "重复组", "空白样", "标准样")),
    ("市场销售", "销售额 (万元)", "渠道", ("直营网店", "零售门店", "经销渠道", "移动端", "团购", "海外业务", "合作渠道", "企业采购")),
    ("课程评估", "得分", "班级", ("一班", "二班", "三班", "四班", "五班", "六班", "七班", "八班")),
    ("材料测试", "强度 (MPa)", "批次", ("原始样", "热处理", "对照样", "合金样", "冷加工", "退火样", "复合材料", "试制样")),
    ("系统性能", "响应时间 (ms)", "方案", ("基准方案", "并行方案", "轻量模型", "参考实现", "快速模式", "默认配置", "高精度", "实验版本")),
)
TITLE_PATTERNS = ("{}对比", "{}统计", "{}变化趋势", "{}测量结果", "{}分布", "{}分析")
RADAR_THEMES = (
    ("模型评估", ("准确率", "稳定性", "覆盖率", "效率", "鲁棒性", "可解释性", "延迟", "召回率")),
    ("服务满意度", ("办理速度", "响应质量", "服务态度", "信息透明度", "便利性", "可靠性", "易用性", "满意度")),
    ("场地评价", ("公共交通", "安全", "通行能力", "环境质量", "成本", "设施维护", "噪声", "区位")),
    ("产品测试", ("外观", "操控", "功耗", "耐久", "舒适度", "精度", "装配", "性能")),
)


def _probability(value, name):
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not 0 <= value <= 1:
        raise ValueError(f"{name} must be a number in [0, 1]")


def validate(policy, kinds):
    if not isinstance(policy, dict) or set(policy) - {"zh_probability", "label_probability", "weighted", "ranges", "text_profile"}:
        raise ValueError("Unknown sampling option or invalid sampling object")
    if "zh_probability" in policy:
        _probability(policy["zh_probability"], "zh_probability")
    if "text_profile" in policy and policy["text_profile"] != "expanded-v1":
        raise ValueError("sampling.text_profile must be expanded-v1")
    for name in ("label_probability", "weighted", "ranges"):
        rules = policy.get(name, {})
        keys = LABEL_KINDS & set(kinds) if name == "label_probability" else {"all", *kinds}
        if not isinstance(rules, dict) or set(rules) - keys:
            raise ValueError(f"Invalid sampling.{name} chart keys")
        for kind, values in rules.items():
            if name == "label_probability":
                _probability(values, f"label_probability.{kind}")
                continue
            if not isinstance(values, dict):
                raise ValueError(f"sampling.{name}.{kind} must be an object")
            for field, options in values.items():
                targets = kinds if kind == "all" else (kind,)
                if name == "ranges":
                    for target in targets:
                        limits = {"aspect_ratio": ASPECT_LIMIT, **ranges_for(target)}.get(field)
                        if (not limits or not isinstance(options, list) or len(options) != 2
                                or not all(_range_valid(v, limits) for v in options) or options[0] > options[1]
                                or target == "radar" and field == "rotation" and options[0] == 180):
                            raise ValueError(f"Invalid sampling.ranges.{kind}.{field}")
                    continue
                if not isinstance(options, list) or not options:
                    raise ValueError(f"Expected weight entries for {kind}.{field}")
                for option in options:
                    if not isinstance(option, dict) or set(option) != {"value", "weight"}:
                        raise ValueError("Weight entries require value and weight")
                    weight = option["weight"]
                    if type(weight) not in {int, float} or not math.isfinite(weight) or weight <= 0:
                        raise ValueError("Weights must be finite and positive")
                    value = option["value"]
                    for target in targets:
                        if field == "aspect_ratio":
                            if not _range_valid(value, ASPECT_LIMIT):
                                raise ValueError("aspect_ratio must be in [.6, 3]")
                        elif target in EXTENSIONS:
                            validate_extension_controls(target, {field: value})
                        else:
                            normalize_controls(target, {field: value})


def unit(kind, seed, field):
    return int.from_bytes(hashlib.sha256(f"sampling/v1:{kind}:{seed}:{field}".encode()).digest()[:8], "big") / 2**64


def _weighted_choice(kind, seed, field, options):
    remaining = unit(kind, seed, field) * sum(option["weight"] for option in options)
    for option in options:
        remaining -= option["weight"]
        if remaining < 0:
            return option["value"]
    return options[-1]["value"]


def radar_label_factor(points):
    return next((factor for limit, factor in RADAR_LABEL_FACTORS if points <= limit), 0)


def _draw_range(kind, seed, field, bounds, integer, *, prefer_small=False):
    low, high = bounds
    u = min(unit(kind, seed, field), math.nextafter(1.0, 0.0))
    if prefer_small:
        u = min(u, unit(kind, seed, field + ":density"))
    if integer:
        return low + int(u * (high - low + 1))
    return low + u * (high - low)


def _default_aspect(kind):
    if kind in {"radar", "pie"}:
        return (.9, 1.65)
    if kind == "combination":
        return (1.25, 2.3)
    return (1.1, 2.1) if kind.startswith(("barv", "line")) else (.95, 1.9)


def _radar_ticks(radial_max, target_side, categories):
    # Favor integral multiples of the mantissa so tick labels stay simple.
    mantissa = float(f"{radial_max:e}".split("e")[0])
    budget = min(8, max(3, round(target_side / (122 + 4 * categories))))

    def score(count):
        step = mantissa * 20 / count
        return round(abs(step - round(step)) + .18 * (budget - count), 8), -count

    return min(range(3, budget + 1), key=score)


class _IncompatibleDraw(ValueError):
    """A random choice conflicts with another admissible parameter."""


def plan(kind, seed, policy, *, controls=None, target_side=1036):
    """Resolve explicit controls before drawing, retrying incompatible random choices."""
    explicit = dict(controls or {})
    if kind in EXTENSIONS:
        validate_extension_controls(kind, explicit)
    else:
        # Normalize aliases before checking the coupled sampled controls.
        explicit = normalize_controls(kind, explicit)
    for attempt in range(4):
        try:
            return _plan(kind, seed if not attempt else f"{seed}:retry:{attempt}", policy, explicit, target_side)
        except _IncompatibleDraw as error:
            if attempt == 3:
                raise ValueError(f"{kind} has no compatible draw after four attempts: {error}") from error


def _plan(kind, seed, policy, explicit, target_side):
    result = {}
    if "zh_probability" in policy:
        result["language"] = "zh" if unit(kind, seed, "language") < policy["zh_probability"] else "en"
        result["theme"] = int(unit(kind, seed, "theme") * len(THEMES))
        result["title_pattern"] = int(unit(kind, seed, "title_pattern") * len(TITLE_PATTERNS))
    if "text_profile" in policy:
        result["text_profile"] = policy["text_profile"]
        result.setdefault("language", "en")

    def merged(section):
        fields = policy.get(section, {})
        return {**fields.get("all", {}), **fields.get(kind, {})}

    weights, intervals = merged("weighted"), merged("ranges")
    choices = dict(explicit)
    limits = ranges_for(kind)

    def draw(field, bounds=None, *, small=False):
        low, high = bounds or intervals.get(field, limits[field][:2])
        return _draw_range(kind, seed, field, (low, high), limits[field][2], prefer_small=small)

    def pick(field, options, probabilities=None):
        if field not in choices:
            candidates = weights.get(field) or [
                {"value": value, "weight": weight}
                for value, weight in zip(options, probabilities or [1] * len(options), strict=True)
            ]
            choices[field] = _weighted_choice(kind, seed, field, candidates)

    if kind == "radar":
        def candidates(field):
            if field in explicit:
                return [dict(value=explicit[field], weight=1)]
            if field in weights:
                return weights[field]
            lo, hi = intervals.get(field, limits[field][:2])
            return [dict(value=value, weight=1) for value in range(lo, hi + 1)]

        categories, series = candidates("category_count"), candidates("series_count")

        def fits(n, count, variant):
            cap = next(cap for limit, cap in RADAR_SERIES_LIMITS if n <= limit)
            return ((2 if variant == "stacked_polar_bar" else 1) <= count
                    <= min(cap, 4 if variant == "filled" else cap))

        def feasible(variant, n):
            return any(fits(n, option["value"], variant) for option in series)

        variants = weights.get("variant", [
            dict(value=variant, weight=weight)
            for variant, weight in zip(RADAR_VARIANTS, (5, 3, 1, 1), strict=True)
        ])
        explicit_line_style = RADAR_LINE_STYLE & explicit.keys()
        eligible = [opt for opt in variants if any(feasible(opt["value"], n["value"]) for n in categories)
                    and not (opt["value"] == "filled" and explicit.get("closed") is False)
                    and not (opt["value"] in RADAR_BAR_VARIANTS and explicit_line_style)]
        if "variant" in explicit:
            variant = explicit["variant"]
        elif eligible:
            variant = _weighted_choice(kind, seed, "variant", eligible)
        else:
            raise ValueError("No radar series_count weight or range satisfies any requested variant and category count")
        choices["variant"] = variant
        valid_categories = [opt for opt in categories if feasible(variant, opt["value"])]
        if not valid_categories:
            raise ValueError(f"No radar series_count weight or range satisfies the category counts for {variant}")
        if "category_count" in explicit or "category_count" in weights:
            n = _weighted_choice(kind, seed, "category_count", valid_categories)
        else:
            n = draw("category_count", (valid_categories[0]["value"], valid_categories[-1]["value"]), small=True)
        choices["category_count"] = n
        valid_series = [opt for opt in series if fits(n, opt["value"], variant)]
        if "series_count" in explicit or "series_count" in weights:
            choices["series_count"] = _weighted_choice(kind, seed, "series_count", valid_series)
        else:
            choices["series_count"] = draw("series_count", (valid_series[0]["value"], valid_series[-1]["value"]), small=True)
        if variant in RADAR_BAR_VARIANTS:
            if explicit_line_style:
                raise ValueError(f"Polar bars do not use {', '.join(sorted(explicit_line_style))}")
            for field in RADAR_LINE_STYLE:
                choices.pop(field, None)
                weights.pop(field, None)
        elif variant == "filled":
            if explicit.get("closed") is False:
                raise ValueError("Filled radar requires a closed outline")
            choices["closed"] = True

    for field, options in weights.items():
        if field not in choices:
            choices[field] = _weighted_choice(kind, seed, field, options)

    if kind in EXTENSIONS:
        pick("profile", EXTENSION_PROFILES, (5, 3, 2, 3, 2, 1))
        if kind == "radar":
            pick("grid", ("polygon", "circle"))
            pick("data_pattern", RADAR_PATTERNS)
            if "radial_max" not in choices:
                exponent = choices.pop("radial_exponent", None)
                if exponent is None:
                    exponent = draw("radial_exponent")
                choices["radial_max"] = (1, 2, 2.5, 5)[int(unit(kind, seed, "radial_base") * 4)] * 10 ** exponent
            if "tick_count" not in choices:
                a, b = intervals.get("tick_count", limits["tick_count"][:2])
                choices["tick_count"] = min(b, max(a, _radar_ticks(choices["radial_max"], target_side, n)))
            if variant not in RADAR_BAR_VARIANTS:
                pick("closed", (True, False), (4, 1))
        else:
            pick("dual_axis", (True, False))
            pick("error_bars", (True, False), (1, 4))
        if kind == "combination" or variant not in RADAR_BAR_VARIANTS:
            pick("point", (True, False), (3, 2))
            pick("dashed", (True, False), (1, 3))
    elif kind == "pie":
        pick("value_mode", ("percent", "absolute"), (3, 2))
        pick("donut", (True, False))
    elif kind == "boxplot":
        pick("orientation", ("horizontal", "vertical"))
    elif kind.endswith("_stack"):
        pick("stack_mode", ("absolute", "percent"), (3, 1))
    elif kind.startswith("line"):
        if choices.get("y_mode") == "categorical" and "x_mode" not in explicit:
            choices["x_mode"] = "numeric"
        pick("x_mode", ("categorical", "temporal", "numeric"), (4, 2, 4))
        if "y_mode" not in choices and choices["x_mode"] == "numeric" and unit(kind, seed, "y_mode") < .2:
            choices["y_mode"] = "categorical"

    if kind == "scatter_n" and "series_count" not in choices:
        low, high = intervals.get("series_count", limits["series_count"][:2])
        point_limit = choices.get("point_count", intervals.get("point_count", limits["point_count"][:2])[1])
        high = min(high, (point_limit - 4) // 4)
        if low > high:
            raise _IncompatibleDraw("Scatter series_count range cannot fit point_count")
        choices["series_count"] = draw("series_count", (low, high), small=True)
    for field in limits:
        if field in choices or kind == "radar" and (field == "radial_exponent" or
                                                   variant in RADAR_BAR_VARIANTS and field == "stroke_width"):
            continue
        if kind == "scatter_n" and field == "point_count":
            low, high = intervals.get(field, limits[field][:2])
            low = max(low, 4 * choices["series_count"] + 4)
            if low > high:
                raise _IncompatibleDraw("Scatter point_count range cannot support the selected series_count")
            choices[field] = draw(field, (low, high))
        elif kind == "pie" and field == "category_count":
            low, high = intervals.get(field, limits[field][:2])
            low = max(low, choices.get("zero_count", 0) + 1)
            if low > high:
                raise _IncompatibleDraw("Pie category_count range cannot support zero_count")
            choices[field] = draw(field, (low, high))
        else:
            choices[field] = draw(field, small=field.endswith("series_count"))

    ratio = choices.pop("aspect_ratio", None)
    if ratio is not None:
        result["aspect_ratio"] = ratio
    elif "figsize" not in choices.get("style", {}):
        result["aspect_ratio"] = _draw_range(kind, seed, "aspect_ratio",
                                             intervals.get("aspect_ratio", _default_aspect(kind)), False)
    probabilities = policy.get("label_probability", {})
    if kind == "radar" or kind in probabilities or kind == "combination":
        p = probabilities.get(kind, .25)
        if kind == "radar":
            p *= radar_label_factor(n * choices["series_count"])
        result["value_labels"] = unit(kind, seed, "value_labels") < p
    if kind == "pie" and choices.get("zero_count", 0) >= choices["category_count"]:
        raise _IncompatibleDraw("Pie zero_count must be below category_count")
    if kind == "scatter_n" and choices["point_count"] < 4 * choices["series_count"] + 4:
        raise _IncompatibleDraw("Scatter point_count cannot support series_count")
    if kind.startswith("line") and choices.get("y_mode") == "categorical" and choices["x_mode"] != "numeric":
        raise _IncompatibleDraw("Categorical Y requires numeric X")
    if kind not in EXTENSIONS:
        normalize_controls(kind, choices)
    return result, choices
