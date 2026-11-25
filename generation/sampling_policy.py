"""Optional deterministic sampling knobs shared by native and extension runs."""
from __future__ import annotations

import hashlib
import math

from .controls import KINDS, normalize_controls

EXTENSIONS = {"radar", "combination"}
LABEL_KINDS = {kind for kind in KINDS if kind.startswith(("bar", "line"))} | {"pie", "combination", "radar"}
CJK_NAME = "Noto Sans CJK SC"
CJK_FILE = "NotoSansCJKsc-Regular.otf"

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
    if not isinstance(policy, dict) or set(policy) - {"zh_probability", "label_probability", "weighted", "text_profile"}:
        raise ValueError("Unknown sampling option or invalid sampling object")
    if "zh_probability" in policy:
        _probability(policy["zh_probability"], "zh_probability")
    if "text_profile" in policy and policy["text_profile"] != "expanded-v1":
        raise ValueError("sampling.text_profile must be expanded-v1")
    for name in ("label_probability", "weighted"):
        rules = policy.get(name, {})
        keys = LABEL_KINDS & set(kinds) if name == "label_probability" else {"all", *kinds}
        if not isinstance(rules, dict) or set(rules) - keys:
            raise ValueError(f"Invalid sampling.{name} chart keys")
        for kind, values in rules.items():
            if name == "label_probability":
                _probability(values, f"label_probability.{kind}")
                continue
            if not isinstance(values, dict):
                raise ValueError(f"sampling.weighted.{kind} must be an object")
            for field, options in values.items():
                if not isinstance(options, list) or not options:
                    raise ValueError(f"Expected weight entries for {kind}.{field}")
                for option in options:
                    if not isinstance(option, dict) or set(option) != {"value", "weight"}:
                        raise ValueError("Weight entries require value and weight")
                    weight = option["weight"]
                    if isinstance(weight, bool) or not isinstance(weight, (int, float)) or not math.isfinite(weight) or weight <= 0:
                        raise ValueError("Weights must be finite and positive")
                    value = option["value"]
                    if field == "aspect_ratio":
                        if isinstance(value, bool) or not isinstance(value,(int,float)) or not .6 <= value <= 3:
                            raise ValueError("aspect_ratio must be in [.6, 3]")
                    else:
                        for target in (kinds if kind == "all" else (kind,)):
                            if target == "radar" and field == "radial_max":
                                if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or value <= 0:
                                    raise ValueError("radial_max must be a finite positive number")
                                continue
                            if target not in EXTENSIONS:
                                normalize_controls(target, {field: value})
                                continue
                            choices = {
                                "profile": {"publication_clean", "monochrome_minimal", "compact_report",
                                            "editorial", "colorful_analytic", "dark_contrast"},
                                "category_count": set(range(4, 13)),
                            }
                            choices.update({"series_count": set(range(1, 9)),
                                            "category_count": set(range(4, 37)),
                                            "variant": {"line", "filled", "polar_bar", "stacked_polar_bar"},
                                            "layout": {"overlay"}, "closed": {True, False},
                                            "grid": {"polygon", "circle"}, "rotation": {-90, -60, 0, 30},
                                            "tick_count": {3, 4, 5, 6, 8}, "point": {True, False},
                                            "dashed": {True, False}, "stroke_width": {1, 1.5, 2, 2.5, 3},
                                            "per_dimension_scale": {False},
                                            "data_pattern": {"random", "correlated", "peaked", "spiky", "smooth", "flat"}} if target == "radar"
                                           else {"dual_axis": {True, False}})
                            if field not in choices or value not in choices[field]:
                                raise ValueError(f"Invalid extension choice: {target}.{field}")


def unit(kind, seed, field):
    return int.from_bytes(hashlib.sha256(f"sampling/v1:{kind}:{seed}:{field}".encode()).digest()[:8], "big") / 2**64


def plan(kind, seed, policy):
    result = {}
    if "zh_probability" in policy:
        result["language"] = "zh" if unit(kind, seed, "language") < policy["zh_probability"] else "en"
        result["theme"] = int(unit(kind, seed, "theme") * len(THEMES))
        result["title_pattern"] = int(unit(kind, seed, "title_pattern") * len(TITLE_PATTERNS))
    if "text_profile" in policy:
        result["text_profile"] = policy["text_profile"]
        result.setdefault("language", "en")
    if kind in policy.get("label_probability", {}):
        result["value_labels"] = unit(kind, seed, "value_labels") < policy["label_probability"][kind]
    weights = policy.get("weighted", {})
    choices = {}
    for field, options in {**weights.get("all", {}), **weights.get(kind, {})}.items():
        remaining = unit(kind, seed, field) * sum(option["weight"] for option in options)
        for option in options:
            remaining -= option["weight"]
            if remaining < 0:
                break
        choices[field] = option["value"]
    if "aspect_ratio" in choices:
        result["aspect_ratio"] = choices.pop("aspect_ratio")
    return result, choices
