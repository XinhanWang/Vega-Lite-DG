"""VSR text rules with per-chart bilingual vocabularies and independent RNG state."""
from __future__ import annotations

from functools import lru_cache
import gzip
from pathlib import Path
import random
import re

from . import vsr_text
from .sampling_policy import unit
from .vsr_runtime import _bind

ZH_WORDS = Path(__file__).with_name("words_zh.txt.gz")

# Chart-domain words supplement the general dictionaries. This mix is shared
# by every template, including those that did not use VSR before.
DOMAIN_WORDS = {
    "zh": (
        "晶粒 相变 合金 界面 载荷 位移 应变 弹性 韧性 导热 腐蚀 钝化 温升 热流 "
        "液滴 颗粒 孔隙 粗糙度 浓度 沉积 转速 传质 压降 电位 电流 容量 阻抗 "
        "振幅 噪声 相位 频谱 波形 纹理 像素 路径 梯度 极值 分辨率 观测 采样 基线 "
        "吞吐 延迟 带宽 内存 缓冲 缓存 并行 召回 准确率 误差 负载 队列 节点 "
        "能耗 水位 光照 雨量 风速 流量 温度 盐度 湿度 土壤 植被 营养 叶片 产量 "
        "运输 订单 库存 收益 损耗 成本 资产 信号 终端 渠道 园区 仓储 餐饮 客流 "
        "站点 航段 档期 选区 队伍 课程 班级 校区 书目 测试 评级 得分 教学"
    ).split(),
    "en": (
        "Grain Phase Alloy Interface Load Strain Ductility Conductivity Corrosion Passivation "
        "Heat Flux Droplet Porosity Roughness Concentration Deposition Torque Pressure Potential "
        "Current Capacity Impedance Amplitude Noise Spectrum Waveform Texture Pixel Gradient "
        "Resolution Observation Sampling Baseline Throughput Latency Bandwidth Memory Buffer Cache "
        "Parallel Recall Precision Error Queue Node Energy Reservoir Irradiance Rainfall Wind "
        "Discharge Temperature Salinity Humidity Soil Canopy Yield Transit Order Inventory Revenue "
        "Loss Cost Asset Signal Terminal Channel Depot Freight Attendance Route Session Cohort "
        "Course Campus Reference Trial Rating Score Instruction"
    ).split(),
}
CATEGORY_AXES = {
    "zh": "类别 样本 组别 区域 条件 批次 渠道 工况 阶段 标签 区间 平台 站点 队列 层级 档位 观测点 试验组 分组 序列".split(),
    "en": "Category Sample Group Region Condition Batch Channel Scenario Phase Label Interval Platform Site Cohort Level Tier Observation Trial Segment Sequence".split(),
}
MEASURE_AXES = {
    "zh": "数值 得分 指数 强度 均值 中位数 频率 峰值 幅度 密度 偏差 差值 波动 负载 速率 总量 规模 参考值 测量值 响应 性能 效率 利用率 计数".split(),
    "en": "Value Score Index Strength Average Median Frequency Peak Magnitude Density Deviation Difference Variation Load Rate Volume Scale Reference Measurement Response Performance Efficiency Utilization Count".split(),
}
TIME_AXES = {
    "zh": ("时间", "时期", "日期", "历时", "观测时间", "统计周期", "时间窗口", "记录周期", "观测期", "统计时段"),
    "en": ("Time", "Period", "Date", "Duration", "Observation time", "Reporting period", "Time window", "Recording period", "Observation period", "Reporting window"),
}
INDEX_AXES = {
    "zh": ("观测序号", "时间步", "样本编号", "测点索引", "迭代次数", "序列位置", "采样顺序", "记录编号"),
    "en": ("Observation index", "Time step", "Sample ID", "Point index", "Iteration", "Sequence position", "Sampling order", "Record ID"),
}
COMBO_METRICS = {
    "zh": ("达成率", "利用率", "完成率", "覆盖率", "通过率", "占用率", "匹配率", "保有率", "准时率", "兑现率"),
    "en": ("Attainment", "Utilization", "Completion", "Coverage", "Pass rate", "Occupancy", "Match rate", "Retention", "On-time rate", "Delivery rate"),
}
SERIES_ROLE_ZH = {"Series": "系列", "Group": "分组", "Batch": "批次", "Run": "轮次", "Trial": "试验", "Layer": "分层"}
GROUP_NAME = re.compile(r"(Series|Group|Batch|Run|Trial|Layer) (\d+)\Z")


@lru_cache(maxsize=1)
def chinese_words():
    with gzip.open(ZH_WORDS, "rt", encoding="utf-8") as source:
        return tuple(line.rstrip("\n") for line in source)


def _primitives(kind, seed, language):
    rng = random.Random(int(unit(kind, seed, "expanded-v1-words") * 2**64))
    namespace = {**vars(vsr_text), "random": rng}
    _bind(vsr_text, namespace)
    if language == "zh":
        namespace.update(load_words=chinese_words,
                         MONTHS=[f"{month}月" for month in range(1, 13)],
                         QUARTERS=[f"第{quarter}季" for quarter in range(1, 5)])
    base_word = namespace["sample_word"]

    def word():
        if rng.random() < .16:
            return rng.choice(DOMAIN_WORDS[language])
        return base_word()

    namespace["sample_word"] = word
    return rng, namespace


def _distinct(draw, count):
    labels = {}
    while len(labels) < count:
        labels[draw(len(labels))] = None
    return list(labels)


def sample_chart_text(kind, seed, language, category_count=0, series_count=0):
    """Sample all text roles without drawing from the number or style RNG."""
    rng, text = _primitives(kind, seed, language)
    word = text["sample_word"]
    zh = language == "zh"
    family = "bar" if kind.startswith("bar") else kind.split("_", 1)[0]
    title = text["sample_title"]("line" if family == "combination" else family)
    has_word = re.search(r"[\u4e00-\u9fff]" if zh else r"[A-Za-z]{4,}", title)
    if not has_word or rng.random() < .28:
        title = f"{word()} - {title}"

    def axis(pool):
        role = rng.choice(pool[language])
        separator = "" if zh else " "
        return f"{word()}{separator}{role}" if rng.random() < .65 else role

    def category(_):
        # Most labels use the original VSR mixture. Give dense radar spokes
        # and combination x axes shorter names to preserve visible text.
        if family in {"radar", "combination"}:
            mode = rng.choice(("word", "word", "word", "hybrid", "code", "abbr", "compound"))
            return text["sample_label"](mode)
        return text["sample_label"]()

    def series(index):
        name = text["sample_series_name"](index)
        match = GROUP_NAME.fullmatch(name)
        if zh and match:
            return SERIES_ROLE_ZH[match[1]] + match[2]
        return name

    result = {
        "title": title,
        "category_axis": axis(CATEGORY_AXES), "value_axis": axis(MEASURE_AXES),
        "second_measure_axis": axis(MEASURE_AXES),
        "time_axis": rng.choice(TIME_AXES[language]), "index_axis": rng.choice(INDEX_AXES[language]),
        "categories": _distinct(category, category_count),
        "series": _distinct(series, series_count),
    }
    if family == "combination":
        result["right_axis"] = rng.choice(COMBO_METRICS[language]) + " (%)"
        # Keep the two Studio series identities distinct after switching the
        # second series to the independent-scale label.
        suffix = result["right_axis"].removesuffix(" (%)")
        if result["series"] and result["series"][0] == suffix:
            result["series"][0] += " A"
    return result
