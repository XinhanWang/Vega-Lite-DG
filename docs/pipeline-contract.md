# 科学图表数据生产管线：精简训练 GT v2

部署位置：`h.pjlab.org.cn:/mnt/shared-storage-user/mineru2-shared/users/wangxinhan/proj/data_generation/vsr_v1`。

管线借鉴 VSR 的参数化采样和样式多样化设计，首版覆盖其对应的九种图表结构。训练任务是“图表图像 → 保留数据与科学含义的精简 Vega-Lite JSON”：识别数值、类别、系列、变量单位、分组/堆叠和误差关系。字体、颜色、布局及内部像素几何不属于训练目标。

`chart.png` 从同目录 `full.vl.json` 实际渲染；训练标签是 `compact.py` 确定性生成的 `compact.vl.json`。完整规格负责绘图多样性，精简规格负责统一语义表达。原生 VSR 的 `native.png`、配置和标注继续保存，供溯源与审计使用。

## 使用

以下命令在服务器本目录执行，使用 Python 3.10、父目录固定 Node 24.11 及 node_modules。生成不需要 GPU 或 LLM API。

```sh
python3 bootstrap.py
python3 pipeline.py generate --config configs/smoke.json --output runs/my_smoke
python3 pipeline.py generate --config configs/production.json --output runs/my_production
python3 pipeline.py validate --output runs/my_production
```

输出目录必须为空。`counts` 是候选数；生产配置默认每类 50 个。未通过质量门的样本进入 `rejected.jsonl`，生成命令返回非零。训练仅使用 `manifest.jsonl` / `train.jsonl`。同配置恢复可给 `generate` 加 `--resume`；新配置使用新目录，不在同一运行目录并发启动作业。

既有数据可用新规范重新生成两份规格和图像，保留旧运行目录：

```sh
python3 pipeline.py reproject --source runs/examples_final --output runs/examples_compact_v2_final
python3 pipeline.py reproject --source runs/production_20261109 --output runs/production_compact_v2
python3 pipeline.py validate --output runs/examples_compact_v2_final
python3 build_gallery.py --run runs/examples_compact_v2_final --output publication_compact_v2 --destination https://aicarrier.feishu.cn/wiki/KGpowD0rZidn2xkqOwHcTGVAnWd
```

`reproject` 读取保存的配置并复制原生审计文件，不重新采样。加 `--prepare-only` 可只准备规格和 `render-jobs.json`，随后单独渲染与验证。上述 v2 目录是新版交付使用的路径；运行是否完成及接受数量以各目录实际报告为准。

适配器 2.1 默认在 `generate` 和 `reproject` 两个入口启用生成阶段的防裁切布局。可在独立目录验证旧数据：

```sh
python3 pipeline.py reproject --source runs/production_compact_v2 --output runs/production_no_clip_v3
```

```sh
../.runtime/node render.mjs --input runs/production_compact_v2/render-jobs.json --out runs/production_compact_v2/render-report.json --target-side 1036
python3 pipeline.py validate --output runs/production_compact_v2
python3 -m unittest discover -s tests -v
```

## 图表与配置

| 类型键 | 图表结构 |
|---|---|
| `barh_1` / `barh_n` | 单/多系列横向柱状图 |
| `barv_1` / `barv_n` | 单/多系列纵向柱状图 |
| `barv_stack` | 绝对值/百分比堆叠纵柱 |
| `line_1` / `line_n` | 单/多折线；分类、等间隔时间标签或数值 x |
| `scatter_1` / `scatter_n` | 单/多散点 |

JSON/YAML 配置字段：`seed`、`counts`、`controls`、`workers`、`native`、`postprocess_native`、`target_side`。`controls.all` 为公共控制，`controls.<类型键>` 覆盖它。支持 `category_count`、`point_count`、`series_count`、`family`、`x_mode`、`stack_mode`、`profile`、`style`、`show_error`、`hatch`、`max_attempts`。

`scatter_n.point_count` 是全部系列的总点数，范围 12–48，且至少 `4 * series_count + 4`；折线 point_count 为每系列点数。可用数据族和样式 profile 见 `native.py`。样本种子由总种子、图族、索引决定，记录实际采样种子与控制项；Python 并行使用进程。

## 精简 JSON 约定

常规顶层只有 `data`、可选 `title`、`mark`、`encoding`；误差图使用共享 encoding 的两层 bar + rule。柱图每行是 `category/value`，折线和散点是 `x/y`；多个系列或可见有效单系列名称增加 `series`。只有确实存在误差时再增加 `lower/upper`。

- 变量名与单位在轴通道 `title` 保留一次。整体标题保留原文本，不复制字号或排版换行。
- 多系列以真实名称编码；分组柱用 `xOffset/yOffset`，堆叠用 `stack:"zero"`。已为百分数的数据不再次归一化。
- 分类和等间隔时间标签保持有序离散轴。数值 x 保留真实值；非单调或同 x 折线用 `mark.order:false` 保留原输入连接顺序。
- 重复类别/系列名称确实代表不同身份时，才以该字段中的整数键及最少 `labelExpr` 保留身份和原显示文本。正常样本不带 ID，重复散点不去重。
- 非线性尺度及必要 base/exponent/constant、误差上下限保留。普通线性尺度、布局 domain、ticks、reverse、颜色范围、字体、尺寸、marker 样式、hatch、参考零线和元数据不进入 GT。

精简数据没有 `row_id`、`plot_x0`、堆叠 bottom/top、像素坐标或生产信息。完整规格中的 source rows、ID 和几何文件继续作为管线内部证据。`normalize(full)` 与 `normalize(compact)` 的验证分别检查确定性和幂等；`project_rows(full) == semantic_rows(compact)` 检查真实观察、重复身份与顺序。视觉样式变化而科学语义不变时，应共享同一 GT。

## 渲染与文字完整性

完整绘图规格生成前，`plot_layout.py` 会用所有观察点、柱子/堆叠端点和误差上下限计算安全坐标范围，并为散点符号、线宽和误差棒端帽预留像素边距。已有坐标范围只按需扩大；反向轴和尺度类型保留。非线性轴在其尺度变换空间计算边距，无法合法映射的数值会明确报错。等比例图通过增大绘图区尺寸保持比例，不再为了等比例缩小数据范围。主图元和纹理在最终范围上生成，之后再处理长文字布局。

这一策略默认生效，不改变数据、误差数值或精简 GT。每例 `plot-layout.json` 记录原范围、最终范围、边距及尺寸，`source.json` 和完整规格的 `usermeta` 中也保留该记录。原生 `native.png` 仍是未修改的 VSR 审计对照；训练图像使用经过上述布局的 `chart.png`。`build_geometry_pair` 默认保留原几何，仅用于历史审计；生产调用的是 `build_pair`。

生成前预防与渲染后检查同时保留：不关闭 `clip`，不放宽质检阈值，也不删除越界观察来通过检查。无法安全布局或渲染后仍裁切的样本继续进入拒收清单。

渲染使用官方 **Vega-Lite 6.5.0 `compile` → Vega 6.4.0 `View.toSVG()`** 产生 SVG，再由第三方 **Resvg 2.6.2** 栅格化为 PNG。项目字体从 `fonts.manifest.json` 读取并记录 SHA-256。完整与精简 JSON 分别独立编译、渲染。

`text_layout.py` 在完整绘图规格中关闭轴/图例/标题默认省略号截断，按词换行，增加留白或画布空间；原始科学标题和变量名另存供精简投影读取。`text-audit.json` 检查实际 SVG 文本/tspan 是否保留声明显示的标题、刻度和图例文字，并报告非源文本的省略号。该检查结合几何边界审计使用，不能单凭 SVG 文本证明所有文字之间都无重叠。

renderer 默认 2 个独立 Node 子进程、每批最多 10 样本、单批 180 秒超时；原生库崩溃或超时后保留成功结果、拆分重试，最终失败记录为拒收。恢复默认开启，核对输入、运行环境、字体和全部输出 SHA-256；缺失或变更文件会重绘。

常用参数为 `--workers`、`--chunk-size`、`--child-timeout-ms`、`--target-side`、`--resize-mode contain|stretch`、`--no-resume`。renderer 进程数独立于 Python 配置的 `workers`。详细参数、退出码及隔离恢复验证见 [render.mjs](../render.mjs)。

## 输出与质量门

每例 `samples/<类型>-<索引>/` 的主要文件：

- `full.vl.json`、`chart.svg/png`：绘图规格及其实际渲染图像。
- `compact.vl.json`、`compact.svg/png`：最小训练 GT 及独立重绘。
- `config.json`、`source.json`、`generation.json`：采样配置、原始观察和生产证据。
- `geometry.json`、`compact.geometry.json` 及对应 1036 版本：场景图几何和同步缩放结果。
- `text-audit.json`、`render-record.json`：实际 SVG 文字检查与输出校验记录。
- `plot-layout.json`：渲染前范围与像素边距调整的审计记录。
- `native.png`、`native.annotation.json`、`native.raw.config.json` 等：可选原生对照和标注。

运行目录保存 `run.json`、`generation-manifest.json`、`render-report.json`、`validation.json`、接受/拒绝清单及训练 JSONL。质量门检查两份官方 Schema、语义投影/幂等、真实场景图观察数量（包括重复行）、图像尺寸、有限坐标、缩放坐标一致、SVG 文字、渲染警告及严重裁切。完整和精简规格允许不同视觉布局。

VSR 上游固定为 `1fd040346add205ffbada9748273cad3bc9159e5`，源代码和 Apache-2.0 LICENSE 保留在 `vendor/VSR`。原生生成模式可继续运行其 `resize_and_remap.py`、`render_anchors.py`，输出 `native_outputs/`、`native_packaged/`；重新投影使用已保存的原生证据，无需重新打包。`verify_native.py` 是原生包装器的保真审计工具，不是精简 GT 的训练目标。

本版不宣称生成了论文历史 800K 数据或复现了未公开质量过滤器。新增图族、真实数据采样和其他扩展留待后续。

## 参考

- [科学图表识别训练方案](https://aicarrier.feishu.cn/wiki/QmiTwJqa3iz4f6kHfIQc0fkBnnh)
- [VSR 图表生成设计](https://github.com/InternLM/VSR/tree/1fd040346add205ffbada9748273cad3bc9159e5/chart_generation)
- [ChartCoder data_generator](https://github.com/thunlp/ChartCoder/tree/47d965c971be15eebc5bd495c87efcfa34b2016a/data_generator)
- [Vega-Lite 官方示例](https://vega.github.io/vega-lite/examples/)
