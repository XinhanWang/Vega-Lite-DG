# Vega-Lite-DG

面向“图表图像 → 精简 Vega-Lite JSON”训练任务的数据生产管线。借鉴 VSR 的参数化采样、数据族与样式多样化设计，当前覆盖九种图表类型。生成不需要 GPU 或 LLM API。

每个样本建立三个相互对应的产物：

1. **`full.vl.json`**：带完整视觉样式的绘图规格。
2. **`chart.png`**：从完整规格实际渲染的训练输入图像。
3. **`compact.vl.json`**：保留科学语义和原始观察的精简训练标签。

渲染链为官方 **Vega-Lite 6.5.0 `compile` → Vega 6.4.0 `View.toSVG()`**，随后由 **Resvg 2.6.2** 栅格化为 PNG。可选 `native.png` 是 VSR 作者生成器的审计对照，训练输入为 `chart.png`。

## 支持的图表

| 类型键 | 图表 |
|---|---|
| `barh_1` | 单系列横向柱状图 |
| `barh_n` | 多系列分组横向柱状图 |
| `barv_1` | 单系列纵向柱状图 |
| `barv_n` | 多系列分组纵向柱状图 |
| `barv_stack` | 绝对值或百分比堆叠纵向柱状图 |
| `line_1` | 单折线图 |
| `line_n` | 多折线图 |
| `scatter_1` | 单系列散点图 |
| `scatter_n` | 多系列散点图 |

柱图支持误差棒；折线支持分类、等间隔时间标签或数值 x。数据族和样式控制的具体集合见 `native.py`。

## 快速开始

在 Linux、Python 3.10、Node.js 22+ 环境中执行。已部署服务器使用 Python 3.10 和 Node 24.11；Python 依赖版本记录在 `requirements.txt`，npm 直接依赖固定在 `package.json`。

```sh
git clone git@github.com:XinhanWang/Vega-Lite-DG.git
cd Vega-Lite-DG
python3 -m venv .venv
. .venv/bin/activate
python -m pip install -r requirements.txt
npm install
python bootstrap.py
python pipeline.py generate --config configs/smoke.json --output runs/my_smoke
python pipeline.py validate --output runs/my_smoke
```

`bootstrap.py` 下载并校验项目本地字体，写入含字体家族、字重、字形和文件哈希的 `fonts.manifest.json`，首次执行需要网络。升级已有环境后也应执行一次，以刷新字体元数据；已存在的字体不会重复下载。生成和验证使用仓库内固定版本的 VSR 核心源码，不依赖上游完整仓库。Schema 默认从 npm 安装的 Vega-Lite 包读取。

`requirements.txt` 保留已部署环境的精确版本，其中 Pillow 9.0.1 / PyYAML 5.4.1 较旧。新环境若需从源码构建 PyYAML，可先安装 `wheel`、`setuptools`、`Cython<3`，再以 `--no-build-isolation` 安装该版本；系统需具备相应编译器及 Python 开发头文件。已有服务器环境可直接执行下面的生产命令。

## 生成、恢复与重新投影

```sh
# 九类各 50 个候选，共 450 个
python3 pipeline.py generate --config configs/production.json --output runs/my_production

# 相同配置恢复；不要在同一目录并发运行
python3 pipeline.py generate --config configs/production.json --output runs/my_production --resume

# 单独重做质量检查
python3 pipeline.py validate --output runs/my_production

# 对旧运行重新生成规格和图像，保留原始采样数据
python3 pipeline.py reproject --source runs/my_production --output runs/my_reprojected
```

新运行的输出目录必须为空。`counts` 表示候选数，最终接受数量以 `validation.json` 为准。生成、渲染或质量检查失败会记录原因；拒收非零时命令返回非零。训练数据只读取 `manifest.jsonl` / `train.jsonl` 中的接收样本。

`reproject --prepare-only` 只准备新规格和 `render-jobs.json`，可随后单独渲染：

```sh
node render.mjs --input runs/my_reprojected/render-jobs.json --out runs/my_reprojected/render-report.json --target-side 1036
python3 pipeline.py validate --output runs/my_reprojected
```

`generate` / `reproject` 可用 `--node /path/to/node` 指定 Node；默认优先使用父目录 `.runtime/node`，其次使用 PATH 中的 Node。renderer 的进程数独立于 Python 生成进程数，支持 `--workers`、`--chunk-size`、`--child-timeout-ms`、`--no-resume` 等，细节见 [渲染与语义约定](docs/pipeline-contract.md)。

## 视觉样式多样性

适配器 2.3.0 默认保留原生渲染后的实际展示状态。正常 `generate` 会自动捕获这些信息，无需额外开关；完整绘图规格仍通过固定版本的官方 Vega-Lite → Vega → Resvg 链路生成图片。

- **字体按文字角色保留**：分别记录标题、轴标题、刻度、倍率标记和图例实际使用的字体家族、字重、字形和字号。VSR 的数值刻度与图例经常使用默认 DejaVu Sans，不能统一替换成标题字体。Matplotlib 指定 `fname` 时以字体文件的实际字形为准；采样配置中的 `title_style` / `title_weight` 不一定最终生效。
- **倾斜标签**：保留原生 `x_rotation` / 实际文字角度。倾斜长标签通过自动画布留白完整展示，不再强制改为水平换行；必要时扩大类别间距。水平长标签仍可换行。
- **数值刻度**：保留原生显示精度、负号、科学计数倍率或偏移文本。倍率单独作为标准 Vega-Lite 文字图层绘制，不改数据、不混入语义轴标题或训练目标。
- **绘图区与大小比例**：将原生 axes 的像素尺寸按 DPI 转成点，与字号、描边宽度的单位对齐，避免将整张 figure 尺寸误当绘图区。防裁切仍可扩大范围或绘图区。
- **图例**：捕获原生最终图例边界，保留 `best` 已解析出的实际锚点；保留列数、边框、透明底色、间距和系列符号。散点图例使用实际点大小。过大的图例仍可能外移以容纳完整文字，位置和原因写入审计。
- **网格与刻度**：捕获渲染时实际启用的网格方向、刻度朝向、长度、颜色和宽度。内向刻度额外预留标签距离；保留四侧边框。

原生诊断保存在新样本 `config.json._render_axes`；映射记录位于 `source.json.presentation` / `full.vl.json.usermeta.presentation`。`render-report.json` 记录渲染器与字体文件哈希。选定字体缺失会明确失败；跨机器配置按文件名在项目字体目录中查找。字体初始化见 `bootstrap.py`。

旧配置若缺少上述信息，可按原种子与原控制参数重放原生渲染来补齐：

```sh
python3 pipeline.py reproject --source runs/production_diverse_v4 \
  --output runs/my_fidelity_run --recover-native-presentation
```

重放前后逐项核对配置、坐标范围、刻度和标签；存在差异则失败，不使用不匹配的诊断。旧 `config.json`、原生 PNG 和数据保留，恢复结果另存 `presentation.native.json`，后续重投影会复用此文件。仅有配置、没有种子及原生诊断时，使用明确记录的回退样式；`best` 的占用启发式只用于这种缺少原生落点的情况。

这些改动不改变观察数据和 `compact.vl.json`。字体度量、图例阴影、线图“线段加标记”的复合图例、纹理密度仍存在跨渲染器差异；不承诺像素级复刻。自动文字检查验证完整性和画布边界，不能证明任意文字都互不重叠。

## 配置

`configs/smoke.json` 为九类各一个，`configs/production.json` 为九类各 50 个，`configs/examples.json` 为受控示例。配置支持 JSON / YAML。

```json
{
  "seed": 20261109,
  "counts": {"barv_n": 10, "scatter_1": 10},
  "controls": {
    "all": {"profile": "publication_clean"},
    "barv_n": {"series_count": 3, "show_error": true}
  },
  "native": true,
  "postprocess_native": true,
  "workers": 2,
  "target_side": 1036
}
```

profile 的可选值见 `native.py` 中的 `PROFILES`；不指定时由管线采样。`controls.all` 是公共控制，`controls.<类型键>` 覆盖公共项。常用控制包括 `category_count`、`point_count`、`series_count`、`family`、`x_mode`、`stack_mode`、`profile`、`style`、`show_error`、`hatch`、`max_attempts`。`scatter_n.point_count` 是所有系列的总点数；折线的 `point_count` 是每系列点数。样本种子由总种子、类型和索引确定。

## 精简标签与防裁切

精简 JSON 通常只保留 `data`、可选 `title`、`mark` 和 `encoding`。数值、类别、真实系列名、变量单位、分组/堆叠关系、误差上下限及必要的非线性尺度保留；颜色、字体、尺寸、像素坐标、内部 ID、生产元数据和纯布局范围不进入训练标签。误差图使用 bar + rule 两层表达。

生成阶段默认执行防裁切布局：完整观察、堆叠端点和误差上下限参与坐标范围计算，并给符号、描边和端帽预留像素边距；等比例图通过扩大绘图区保持比例。随后进行长文字换行及画布扩展。每例 `plot-layout.json` 记录范围和尺寸的调整。该过程不修改原始数据或精简标签。

渲染后仍检查 Schema、语义一致性、观察数量、图像与几何尺寸、非有限坐标、SVG 文本完整性和图元裁切。自动检查通过不代表所有文字之间必然无重叠；具体检查边界见 [约定文档](docs/pipeline-contract.md)。

## 输出结构

```text
runs/my_production/
├── run.json / generation-manifest.json / render-jobs.json
├── render-report.json / validation.json
├── manifest.jsonl          # 接收样本及其产物路径
├── rejected.jsonl          # 拒收样本及原因
├── train.jsonl             # 图像路径与精简 JSON 训练对
└── samples/<kind>-<index>/
    ├── full.vl.json / chart.svg / chart.png
    ├── compact.vl.json / compact.svg / compact.png
    ├── config.json / source.json / generation.json
    ├── geometry.json / compact.geometry.json
    ├── plot-layout.json / text-audit.json / render-record.json
    └── native.*            # 启用 native 时的原生证据
```

清单中的相对图像路径以运行目录为根。`train.jsonl` 的 assistant 内容是精简 JSON 字符串；训练加载器需自行按模型格式读取图像和对话。

## 代码结构与验证

| 文件 | 职责 |
|---|---|
| `pipeline.py` | 生成、恢复、重新投影、质量门和训练清单 |
| `native.py` | 固定上游生成器调用、采样控制与原生审计 |
| `adapter.py` / `compact.py` | 完整绘图规格与确定性精简标签 |
| `presentation.py` | 字体、坐标轴、图例等样式映射和来源记录 |
| `plot_layout.py` / `text_layout.py` | 图元防裁切与长文字布局 |
| `render.mjs` | 官方编译渲染、场景图审计、子进程隔离及恢复 |
| `bootstrap.py` | 项目本地字体准备与哈希清单 |
| `build_gallery.py` / `verify_native.py` | 示例页面导出与原生保真审计 |
| `vendor/VSR` | 必需的上游源码、词表与许可证 |

```sh
VSR_TEXT_TEST_MODULES="$PWD/node_modules" python3 -m unittest discover -s tests -v
```

执行 SVG 集成测试需要 PATH 中的 Node 版本为 22+，并将 `VSR_TEXT_TEST_MODULES` 指向实际安装的 node_modules；未设置时 SVG 集成项跳过。服务器依赖安装在父目录，应使用 `PATH="$PWD/../.runtime:$PATH" VSR_TEXT_TEST_MODULES="$PWD/../node_modules" python3 -m unittest discover -s tests -v`。

2026-11-10（适配器 2.3.0）的服务器验证：73 项测试通过，包含实际 SVG 的绘图区底色检查，以及原生字体角色、旋转标签、科学计数倍率、图例锚点与重放一致性检查。

- `runs/production_fidelity_v5`：九类各 50 个，共 450 个旧样本全部接收；与 `production_diverse_v4` 的配置文件、原生 PNG 字节相同，观察数据表和精简 JSON 内容逐份相同。
- `runs/fresh_fidelity_v5`：新种子 20261111，九类各 3 个，共 27 个新样本全部接收。正常 `generate` 会自动捕获并映射新诊断。
- 477 份完整图的 SVG 文本检查通过；原尺寸图元、文字的画布边界和绘图区裁切检查均通过。额外的 1036 缩放审计有 24 条零值参考线的保守描边包围框触边提示（旧样本 22、新样本 2），逐条确认是 `reference_*`，没有观察点、柱、折线或误差区间裁切提示。
- 用户指出的三个案例通过公开 `reproject --recover-native-presentation` 命令恢复；再次重投影可复用恢复文件，完整规格完全一致。

证据位于服务器 `diagnostics/fidelity-v5/delivery/verification.json`，九类对比页位于 `deliveries/fidelity-v5/comparison.html`。此前 `production_no_clip_v3`、`production_diverse_v4` 等目录保留。以上结果适用于已验证版本和样本，不代表任意未来配置均会通过。

## Git 管理范围

`.gitignore` 使用核心文件白名单，提交源码、配置、测试、说明以及必要的 VSR 运行资源。生成数据、图像、字体、`node_modules`、虚拟环境、缓存、日志、历史交付包、诊断文件和密钥均不纳入 Git。`words.txt` 是上游生成标题/标签所需的词表，因此随核心源码保留。

服务器工作树位于 `/mnt/shared-storage-user/mineru2-shared/users/wangxinhan/proj/data_generation/vsr_v1`。现有数据仍在服务器的 `runs/`；本仓库不包含这些数据。日常更新使用 `git status` 检查后提交并推送至 `main`。

上游固定版本及许可证见 [THIRD_PARTY.md](THIRD_PARTY.md)。当前复现九类生成能力，不宣称复现论文历史 800K 数据或未公开的质量过滤器。
