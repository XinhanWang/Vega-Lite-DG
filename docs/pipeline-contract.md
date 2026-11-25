# 生成、GT 与渲染约定

当前生成器为 `vega-lite-native/1.2`，GT 合约为 `compact-v3`。样本经过“数据/样式采样 → 完整 Vega-Lite → 精简 GT → 两份独立渲染 → 质量门 → 训练导出”。Matplotlib 与 VSR 原生图像不再参与新样本生成。

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

`generation/controls.py` 声明九种图表、数据族和style profile。`vsr_samplers/` 静态保留原VSR纯采样函数，`vsr_text.py` 和 `words.txt` 保留文本与词表；`vsr_runtime.py` 绑定每样本独立Python Random/NumPy RandomState及已有纯RGB样式规则；`core.py` 整合显式控制、GT与坐标合约。不导入旧绘图、history、Matplotlib，不通过绘图反推观察数据。

| 控制 | 适用范围与含义 |
|---|---|
| `category_count` | 柱图类别数 |
| `point_count` | 折线每条线的点数；散点总点数 |
| `series_count` | `_1` 固定为 1；普通 `_n` 为 2–5；堆叠为 2–6 |
| `family` | 必须属于该类型在 `FAMILIES` 中声明的数据族 |
| `profile` | 声明的视觉 profile；`dense_scatter_family` 仅用于散点 |
| `x_mode` | 折线的 `numeric` / `categorical` / `temporal` |
| `stack_mode` | 纵向堆叠支持 `absolute` 和 `percent`，横向堆叠仅支持 `absolute` |
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

反向坐标按照实际屏幕方向计算上述顺序。原始 `row_id`、`series_index`、`point_index` 保留在完整规格与证据文件，不因排序重写身份。类别/系列/偏移的 nominal 或 ordinal 通道统一设置 `sort: null`，按 `data.values` 第一次出现顺序建立域。散点等图型沿用各自的离散通道规范。折线的离散位置通道使用 nominal，路径回退时允许显式 X 排序。数值轴反向属性属于可见语义，会保留在 GT。

通常，柱图每行是 `category/value/series`，折线和散点每行是 `x/y/series`。GT 不包含生产 ID、像素坐标、字体配色或原绘图区范围。必要的可重绘信息例外如下：

- 误差区间用 `lower/upper` 表示，GT 以柱图加原生 errorbar 图层重绘。
- 堆叠增加 `stack_order` 维护片段连接关系；异常基线或非普通正负累计堆叠改用显式 `start/end`，避免被重新堆叠成不同形状。
- 非单调折线路径在按可见 x 排序后，以 `path_order` 保留原连接。反向遍历但边相同的路径不必新增该列。
- 重复类别/系列保留原文，以 `category_id=C1…`、离散位置的 `x_id=X1…` 或 `y_id=Y1…`、`series_id=S1…` 区分实际对象；仅对应维度实际重名时整列加入。Renderer 在副本中生成 `labelExpr`，表达式不进入 GT。完整字段顺序、稳定工程 key 与旧字段迁移见 [GT 身份契约](gt-identity-contract.md)。

`normalize(full)` 构造 GT，`normalize(compact)` 幂等。`project_rows(full) == semantic_rows(compact)` 比较的是同一可见顺序下的观察、重复身份和必要连接信息。只有视觉样式变化而可见语义不变时，GT 才保持一致；改变坐标方向、图例可见性等会相应改变 GT。

## Precision V1

新生成样本使用 Precision V2。整数保留原值，普通浮点数最多两位小数，绝对值小于 1 的非零普通数和科学计数法数值最多四位有效数字。十进制中点向远离零的方向舍入。输出是 JSON 数值，去掉无意义的尾数和负零。离散标签、身份和记录顺序保持原值。

饼图和百分比堆叠按百分数的百分之一百分点量化，通过最大余数法分配尾差，每组恰好合计 100%。已使用比例值的图表仍用比例值存储，新生成的百分比饼图仍声明 `theta.format: ".4~p"`。原有百分比轴格式与堆叠柱的百分数存储约定保持一致。

普通观测允许舍入为同值。连续折线已有的互异横坐标、非零误差区间、箱线图的五数次序和 Tukey 围栏、堆叠的边界与径向量程均在舍入后校验。约束失败最多尝试四次确定性抽样。正常零基堆叠用已量化的段值计算共享边界。表中存在显式堆叠边界时，边界同时遵守精度限制。热力图、面积图和直方图由 Studio 支持，DG 原生管线不采样这些图表。

Full 渲染、Compact GT 与 Markdown、CSV 导出使用同一份量化后的科学数据。原始配置与抽样种子保留用于复核。生产流程默认启用该规则。`build_pair(..., precision_v1=True)` 保留其调用方式并启用当前规则。历史 Precision V1 全量重投影复用保存的 Full 观测数据。Compact-only 投影保留历史数值和格式。

普通百分数轴的数据、刻度值和坐标范围使用比例，例如 `0.176`。新图的显式百分数轴在 `_render_axes.x_format` 或 `_render_axes.y_format` 使用 `.4~p`，需要更高显示精度时使用 `.N~p`。Full 和 Compact 都通过 `axis.format` 显示百分号。只有标题含 `(%)` 时，数据保留原量纲，省略百分比格式。旧 Full 的简单百分比刻度后缀表达式仍沿用历史兼容投影。

箱线图横向读取 `_render_axes.x_format`，纵向读取 `_render_axes.y_format`。格式应用于数值轴，五数统计、须线和离群点继续使用同一套比例值。

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

图族、文字与风格多样性来自原VSR实际采样规则及显式控制。参数层按实际原版采样oracle核对；相同生成器版本、种子、控制和资源可重现。完整类别标签、隐藏系列名、显式controls和原生布局是记录的合约扩展，不承诺Matplotlib/Vega像素一致。VSR 的设计归属与许可证保留在 `THIRD_PARTY.md` 和 `vendor/VSR/LICENSE`。
