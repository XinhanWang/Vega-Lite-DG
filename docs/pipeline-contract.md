# 生成、GT 与渲染约定

当前生成器为 `vega-lite-native/1.0`，GT 合约为 `compact-v3`。样本经过“数据/样式采样 → 完整 Vega-Lite → 精简 GT → 两份独立渲染 → 质量门 → 训练导出”。Matplotlib 与 VSR 原生图像不再参与新样本生成。

## 采样接口

```python
from generation import generate_chart
from adapter import build_pair

sample = generate_chart("line_n", 20261110, "runs/example/sample", {
    "point_count": 12,
    "series_count": 3,
    "x_mode": "categorical",
    "show_legend": False,
})
full, compact, source = build_pair("line_n", sample["config"])
```

`generate_chart` 只采样并保存 `config.json` 与 `sampling.json`，返回 `config`、`sample_seed` 和 `diagnostics`。它不创建图片。已有上述采样文件时拒绝覆盖。`build_pair` 不修改输入配置；完整 JSON 的 `data.values` 与 `source.rows` 是同一套观察。

`generation/controls.py` 声明九种图表、各图族的数据分布和样式 profile。`common.py` 持有每样本独立的 Python/NumPy 随机源；`labels.py`、`styles.py`、`bars.py`、`lines.py`、`scatter.py` 分别处理文本、样式和图族数据；`core.py` 组合采样并记录坐标选择。新版本无需通过绘图后的随机状态捕获决定图表内容。

| 控制 | 适用范围与含义 |
|---|---|
| `category_count` | 柱图类别数 |
| `point_count` | 折线每条线的点数；散点总点数 |
| `series_count` | `_1` 固定为 1；普通 `_n` 为 2–5；堆叠为 2–6 |
| `family` | 必须属于该类型在 `FAMILIES` 中声明的数据族 |
| `profile` | 声明的视觉 profile；`dense_scatter_family` 仅用于散点 |
| `x_mode` | 折线的 `numeric` / `categorical` / `temporal` |
| `stack_mode` | 堆叠柱图的 `absolute` / `percent` |
| `show_error` | 非堆叠柱图误差棒，布尔值 |
| `hatch` | 柱形纹理：null、`/`、`\`、`|`、`-`、`+`、`x`、`o`、`O`、`.`、`*` |
| `show_legend` | 是否显示图例，布尔值 |
| `x_inverted` / `y_inverted` | 坐标反向，布尔值 |
| `x_scale` / `y_scale` | `linear` / `log` / `symlog` / `sqrt`；数据与尺度必须兼容 |
| `reference_lines` | `[{"axis": "x"或"y", "value": 有限数值}]` |
| `style` | 样式字典覆盖 |

`scatter_n.point_count` 在 `4 × series_count + 4` 到 48 之间，表示所有系列合计。类别坐标必须使用线性位置尺度；对数轴要求有效正值，平方根轴要求非负值。无效组合明确报错，不隐式丢弃观察。

旧别名 `n_points`、`n_categories`、`n_series`、`style_profile` 仍可使用；与规范名冲突时拒绝。`max_attempts` 为旧配置兼容项，强制控制直接应用，新采样没有旧版拒绝重采样循环。参数含义和验证以 `generation/controls.py` 为准。

## GT 表与可见顺序

训练 GT 的 `data.values` 是实际读取顺序，不依赖隐藏的排序列表：

- 横向柱图：类别从上到下，组内柱子从上到下。
- 纵向柱图：类别从左到右，分组柱子从左到右。
- 堆叠柱图：类别从左到右，每组片段从上到下。
- 折线：x 从左到右，同一 x 的记录保持稳定系列顺序。
- 散点：x 从左到右，同 x 时 y 从上到下，完全相同的观察保留重复次数。

反向坐标按照实际屏幕方向计算上述顺序。原始 `row_id`、`series_index`、`point_index` 保留在完整规格与证据文件，不因排序重写身份。类别/系列/偏移的 nominal 或 ordinal 通道统一设置 `sort: null`，按 `data.values` 第一次出现顺序建立域。数值轴反向属性属于可见语义，会保留在 GT。

通常，柱图每行是 `category/value/series`，折线和散点每行是 `x/y/series`。GT 不包含生产 ID、像素坐标、字体配色或原绘图区范围。必要的可重绘信息例外如下：

- 误差区间用 `lower/upper` 表示，GT 以柱图加显式 rule 图层重绘。
- 堆叠增加 `stack_order` 维护片段连接关系；异常基线或非普通正负累计堆叠改用显式 `start/end`，避免被重新堆叠成不同形状。
- 非单调折线路径在按可见 x 排序后，以 `path_order` 保留原连接。反向遍历但边相同的路径不必新增该列。
- 重复类别/系列名称采用同一字段内的整数身份与 `labelExpr` 显示原文字，避免相同名称被错误合并。审计投影可添加 `*_instance` 区分这些身份；这些审计字段不写入 GT。

`normalize(full)` 构造 GT，`normalize(compact)` 幂等。`project_rows(full) == semantic_rows(compact)` 比较的是同一可见顺序下的观察、重复身份和必要连接信息。只有视觉样式变化而可见语义不变时，GT 才保持一致；改变坐标方向、图例可见性等会相应改变 GT。

## 类别标签与隐藏图例

类别型及等间隔时间标签折线，完整规格会显式设置所有类别刻度。历史配置中的 `tick_positions` 或 `_render_axes.xticks` 稀疏子集不会覆盖完整类别集合。GT 同样列出全部类别并关闭自动标签省略。时间标签按相等日历周期占位，日期元数据不会擅自变成按实际时间差排布的连续轴。

无图例时，原始不可见名称不进入训练答案。系列按表中首次出现顺序命名为 `Series 1`、`Series 2`……；单系列也保留 `series: "Series 1"`。完整规格与 GT 都隐藏图例，`Series N` 作为答案中的约定身份，而不是伪造图片中存在的文字。显示图例时保留其真实名称和重复名称身份。

单点折线必须保留可见点标记，避免只有一条无长度线而看不到观察。标记子采样仅作用于图形标记，不删掉数据行或类别标签。

## 布局与渲染

`plot_layout.py` 根据点、柱端点、堆叠端点和误差上下限扩展安全坐标范围，为标记、线宽和端帽保留像素空间；已有足够的范围保持不变。非线性轴在变换空间计算边距。等比例散点通过扩大绘图区保持比例，无法合法映射的数据明确失败。每例的 `plot-layout.json` 保存调整证据。

`presentation.py` 将采样的字体、网格、线型、刻度和图例样式映射到 Vega-Lite。字体文件经 fontTools 读取真实元数据。`text_layout.py` 关闭默认截断，按词换行并增加留白；原始标题/变量名保留用于 GT 投影。全部类别标签显式保留，长标签仍需结合图像检查其可读性。

渲染使用固定版本的官方 Vega-Lite `compile`、Vega `View.toSVG()`，再由 Resvg 栅格化。完整与精简规格独立编译、渲染。字体来源为 `assets/fonts/` 与 `fonts.manifest.json`，输出记录保存文件哈希。

renderer 默认使用两个隔离 Node 子进程，每批最多十个样本，单批超时为 180 秒。失败批次拆分重试，成功结果保留。恢复时核对输入、运行环境、字体和输出 SHA-256；变化或缺失的输出重绘。常用参数为 `--workers`、`--chunk-size`、`--child-timeout-ms`、`--target-side`、`--resize-mode contain|stretch`、`--no-resume`。renderer 进程数独立于 Python 采样进程数。

## 质量门与训练导出

运行目录保存 `run.json`、候选 `generation-manifest.json`、`render-jobs.json`、`render-report.json`、`validation.json`、接受/拒绝清单与训练 JSONL。新生成的成功样本保存：

| 产物 | 用途 |
|---|---|
| `full.vl.json`、`chart.svg/png` | 完整规格与训练输入 |
| `compact.vl.json`、`compact.svg/png` | GT 与独立重绘 |
| `config.json`、`sampling.json`、`generation.json` | 可复查的采样参数、种子和控制 |
| `source.json` | 原始观察身份、可见顺序和能力记录 |
| `geometry.json`、`compact.geometry.json` 及缩放版本 | 实际场景图图元和坐标 |
| `plot-layout.json`、`text-audit.json`、`render-record.json` | 布局、文字与输出完整性检查 |

历史重投影仅继承源目录已有的 `sampling.json` 等历史证据，不会补造缺失的采样来源文件。

质量门检查两份官方 Schema、投影一致与幂等、场景图真实观察数量和重复次数、图像尺寸、有限坐标、缩放一致性、实际 SVG 文字、渲染警告及严重裁切。数据图元不能靠删除越界观察通过检查。完整与 GT 的视觉样式可不同，但类别、观察及连接信息必须一致。

`counts` 表示候选数。只有接受样本写入 `manifest.jsonl` / `train.jsonl`；拒收原因写入 `rejected.jsonl`。生成、渲染或验证失败会使命令返回非零。自动检查不能认证所有视觉可读性，也不代表复现了论文历史 800K 数据或未公开质量过滤器。

## 迁移与兼容

旧 VSR Matplotlib 生成器、PNG/像素标注、resize/anchor 打包、原生展示重放已移除。新运行不创建 `native.png`、`native.annotation.json`、`native_outputs/` 或 `native_packaged/`。`native.py.generate_native` 作为薄兼容入口委托 `generation.generate_chart`，其旧 `render` 参数不产生绘图行为。

旧运行配置中的 `native` / `postprocess_native` 可读取，启用时提示已移除并忽略。`--resume` 要求生成器版本、GT 合约和规范化配置均相同；旧版本运行使用 `reproject` 到新目录。重投影直接读取保存的 `config.json` 和可选 `presentation.native.json`，保留旧数据与可用展示快照，重新构建当前 JSON/图像。`--recover-native-presentation` 已不支持，不能重做 Matplotlib 捕获。

图族与风格多样性来自显式可选的数据族及参数组合。相同新生成器版本、种子、控制与资源可重现；不保证与旧 VSR 生成器的同种子数据或像素一致。VSR 的设计归属与许可证保留在 `THIRD_PARTY.md` 和 `vendor/VSR/LICENSE`。
