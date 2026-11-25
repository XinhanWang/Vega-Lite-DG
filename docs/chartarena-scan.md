# ChartArena 数值图合成配置

`configs/chartarena-scan.json` 用于柱图、折线图、散点图、饼图和箱线图。
`configs/chartarena-scan-extensions.json` 用于雷达图和柱线组合图。

雷达图原图使用 Full Vega 规格，GT 对照图通过项目内的雷达渲染模块从 Compact GT 独立生成。

扩展生成器还输出 `compact.preview.vega.json`，供审查站使用对应的 Vega 渲染规格。原生图表使用 `compact.preview.vl.json`。

```sh
python3 bootstrap.py --with-cjk
python3 pipeline.py generate --config configs/chartarena-scan.json --output runs/scan-native
node generate_chartarena_extensions.mjs configs/chartarena-scan-extensions.json runs/scan-extensions
```

这两个文件是曾用于 ChartArena 审查的任务预设，继续沿用原有文件名、种子和任务数量。生成使用与其他配置相同的通用多样性规划器。任务权重、范围覆盖和显式控制见 [采样配置](sampling-policy.md)。

## 雷达结构与输出分辨率

雷达 Compact GT 使用 `mark: {"type": "line"}`、`usermeta.chartType: "radar"` 和 `encoding.y.title: null`。保留图标题、类别顺序、原始数值、系列和共享径向量程，多系列用 `encoding.color` 区分。`usermeta.table_export.tables` 中的 `data` 指向 `/data/values`，经统一流程生成 `data.md` 和 `data.csv`。

先采样维度数，再按原权重在允许的系列数候选中采样。4–8、9–15、16–23 和 24–36 维分别最多允许 8、6、4 和 3 个系列。填充雷达最多 4 个系列且轮廓闭合。堆叠极坐标柱至少有 2 个系列，各维度的堆叠总值受 `radial_max` 约束。极坐标柱跳过闭合、点标记、虚线和线宽的采样。折线雷达仍可采样闭合和非闭合形式。若配置的权重没有可用的系列数，采样会报出维度及子类约束。

数值标签的基础概率由 `sampling.label_probability.radar` 配置。按维度数与系列数的乘积 `N` 调整。

| 数据点数 | 基础概率系数 |
| --- | ---: |
| `N ≤ 24` | 1 |
| `24 < N ≤ 48` | 0.5 |
| `48 < N ≤ 72` | 0.2 |
| `N > 72` | 0 |

获准显示的数值标签按数据位置排版，和径向刻度或已放置的数值标签相撞时省略该处数值。径向刻度、类别名和多系列图例始终保留。极坐标柱的数值标注沿各柱自身的角度定位。

权重来自对服务器中 100 张 ChartArena 扫描印刷雷达原图的观察，属于起始近似。原图保留折线、填充雷达、分组极坐标柱和堆叠风玫瑰，所有系列绘制在单一极坐标系中。径向量程在样本间采样，同一张图的各维使用共享量程。

PNG 通过 `pHYs` 保存 200 DPI，像素尺寸继续由 `target_side` 决定。PNG 元数据写入保持压缩像素内容完整。

## 柱线组合图

柱图和误差棒继承顶层 `data.values`，折线图使用自己的 `data.values`。顶层 `encoding` 提供公共的 `x`、`y` 和 `color`。误差棒的 `y` 和 `y2` 分别绑定 `lower` 和 `upper`。由 `mark.type` 区分角色，行记录保留 `series`。

单轴图按柱图、可选误差棒、折线图的顺序平铺，双轴图通过 `resolve.scale.y: "independent"` 让折线使用独立的 Y 编码。仅在双轴且有误差棒时，将柱图和误差棒放入同一个图层组，共用左轴。多柱系列保留 `xOffset`，嵌套时由组内图层继承，系列顺序通过 `sort: null` 和记录首次出现顺序表达。Compact 省略默认线性比例尺，保留对数等非默认比例尺的类型和参数。

表 ID `bars` 指向 `/data/values`，`lines` 指向折线实际所在的 `/layer/<index>/data/values`。折线索引在单轴且有误差棒时为 2，其余结构为 1。导出的 Markdown 和 CSV 使用这些表的原始行顺序、值和轴标题。

含百分号单位的轴使用 `.4~p`，表中以小数保存百分比，例如 12.34% 存为 0.1234。普通指标按语义保留整数或 1～2 位小数。配色、柱宽、间距、折线线型、点标记、图例摆放、轴和网格外观、数值标注、字体与画幅在 Full 中采样。分组较密时每个类别只标注一根柱，以给数字留出间距。

柱和线分别采样 1～3 个系列，较少系列更常出现。共享及独立 Y 轴默认等权，可在 `sampling.weighted.combination.dual_axis` 配置任务比例。类别数从 4～18 中采样，误差棒的默认采样概率为 0.2。清单记录每张图的系列数、Y 轴模式、误差棒、趋势族和样式配置。

本地 ChartArena 的扫描印刷组合图用于参考数字制图风格和指标搭配。合成主题覆盖配送量与准时率、用电与峰值负荷、客流与同比、温室产量与含水率、水文流量与水位、生产良率与返工、库存变化与周转。趋势包括上升、下降、周期波动、局部峰值、突变、平稳和正负交叉。
