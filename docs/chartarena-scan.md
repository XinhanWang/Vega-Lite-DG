# ChartArena scan 合成配置

`configs/chartarena-scan.json` 用于柱图、折线图、散点图、饼图和箱线图。
`configs/chartarena-scan-extensions.json` 用于雷达图和柱线组合图。

雷达图训练 GT 使用 `mark: {"type": "line"}` 和 `usermeta.chartType: "radar"`。多系列时用 `encoding.color` 区分系列。原图使用 Full Vega 规格，GT 对照图由 Compact GT 经雷达适配器单独渲染。

扩展生成器还输出 `compact.preview.vega.json`，供审查站使用对应的 Vega 渲染规格。原生图表使用 `compact.preview.vl.json`。

```sh
python3 bootstrap.py --with-cjk
python3 pipeline.py generate --config configs/chartarena-scan.json --output runs/scan-native
../.runtime/node generate_chartarena_extensions.mjs configs/chartarena-scan-extensions.json \
  runs/scan-extensions ../Chart-Annotation-Studio /path/to/chart_gt_adapter_checkout
```

- `counts` 决定各模板的候选数。默认把 ChartArena 的六类数值图各配为 100 个候选，另保留 50 个散点候选。人工审查可把每个模板的计数改为 100 并为质量拒绝留余量。
- `sampling.text_profile: expanded-v1` 来自 VSR 原有的短词、短语、配对、日期、缩写和代码组合。中文使用 221,690 个词条，英文复用 VSR 英文词库，两种语言再混入图表领域词汇。文字有独立随机源，全部 14 个模板均可使用。省略该项使用之前的文字采样。
- `sampling.zh_probability` 是每张图独立采样中文的概率，默认 0.5。
- `sampling.label_probability` 按模板设置数据点、柱或扇区的数值标注概率。柱图、折线图、饼图和柱线组合图默认 0.25。轴刻度、类别名和图例名照常显示。
- `sampling.weighted` 以 `{"value": ..., "weight": ...}` 条目定义分布。模板级同名权重优先于 `all`，原生配置里的显式 `controls` 优先于权重采样。每个变量使用由种子、模板和字段派生的独立随机数。
- `sampling.weighted.radar.radial_max` 采样零基径向量程上限。抽查扫描原图可见 0–0.5、0–1、0–3.5、0–5、0–10、0–20、0–100 和 0–120 等量程。配置还包含 0–6，权重是起始近似。省略此项时上限为 100。
- `render_workers` 可以单独控制原生渲染进程数。未配置时沿用渲染器默认值。
- 中文使用固定版本的 Noto Sans CJK SC。中文词组连写，比较和配对使用中文连接符，数值单位和日历语义保留。显示文本在构建 Full 规格与 Compact GT 之前应用。显式数值标注只进入 Full，Compact GT 保持原数据和结构。
- `configs/production_vsr.json`、`configs/examples_vsr.json` 和旧式扩展配置仍可直接运行。要用 VSR 自然样式同时开启双语，可在一份独立的 VSR 配置中加入 `sampling.zh_probability: 0.5` 与 `sampling.text_profile: expanded-v1`。

## 参考分布

服务器上以 `chartbench/chartarena/annotation-atlas/chartarena-official-data.jsonl` 为标注快照，
以 `chartbench/chartarena/chartarena-zero-shot/gemini-3.8-flash-high-native-vl-20261105/images` 为数值图原图目录。
标注快照 SHA-256 为 `46a1efb47a35912fc727b193f7629cf102f5ae8f14a51d2bfdbcb193a7da4e64`。

筛选 `img_type == "扫描印刷"` 后，六类数值图各 100 张。以图像宽高比的 P10、中位数、P90
设置画幅的窄、中、宽档，原生布局可能因完整文字边界调整最终宽高。
中位数分别为柱图 1.67、折线 1.37、饼图 1.31、箱线 1.37、雷达 1.19、组合图 1.77。
饼图中 95 张的标注含百分号，因此配置以百分比数据为主，保留原始值样本。
子类型、样式和画幅权重是初始近似。实际样本的语言、标签开关和渲染样式可从清单核对。

生成使用项目自己的数值规则和主题词表。标注快照和参考图用于提取分布统计。

## 雷达结构与输出分辨率

雷达训练 GT 统一采用 `mark: {"type": "line"}` 和 `usermeta: {"chartType": "radar"}`。GT 保留标题、类别顺序、原始数值、系列和共享径向量程，由已有的 `chart_gt_adapter.extensions.radar_to_vega` 直接渲染。表格从同一份 GT 的 `data.values` 导出。

配置中的 `category_count` 支持 4–36 维，`series_count` 支持 1–8 系列。原图使用 `radar_render.mjs` 绘制，可对 `variant`、`grid`、`tick_count`、`rotation`、`point`、`dashed`、`stroke_width`、`closed` 和 `data_pattern` 独立加权采样。数值标签以 0.25 概率采样。

权重来自对服务器中 100 张 ChartArena 扫描印刷雷达原图的观察，属于起始近似。原图保留折线、填充雷达、分组极坐标柱和堆叠风玫瑰，所有系列绘制在单一极坐标系中。径向量程在样本间采样，同一张图的各维使用共享量程。

PNG 通过 `pHYs` 保存 200 DPI，像素尺寸继续由 `target_side` 决定。PNG 元数据写入保持压缩像素内容完整。
