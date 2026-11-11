# 第三方来源

`generation/` 是面向原生 Vega-Lite 的独立数据、样式与坐标采样实现。九类图表、数据家族命名、部分分布设计和样式控制参考了 VSR 生成器；不导入或运行其绘图、后处理代码。

- VSR 上游：https://github.com/InternLM/VSR
- 参考提交：`1fd040346add205ffbada9748273cad3bc9159e5`
- VSR 许可证：Apache License 2.0，保留于 [vendor/VSR/LICENSE](vendor/VSR/LICENSE)。
- `generation/` 的抽样公式、标签和编排已针对独立 RNG、直接控制、完整类别标签和原生 Vega-Lite 流程重写；不保证与旧生成器逐种子相同。

Vega-Lite、Vega 和 Resvg 通过 npm 安装，版本固定在 `package.json`。字体由 `bootstrap.py` 下载到项目本地 `assets/fonts`，字体文件不纳入 Git；使用与再分发应遵循各字体本身的许可。字体元数据由 fontTools 读取，不需要 Matplotlib。

设计参考：[ChartCoder](https://github.com/thunlp/ChartCoder/tree/main/data_generator)、[Vega-Lite 官方示例](https://vega.github.io/vega-lite/examples/)。本项目没有将这些项目的数据集或安装目录打包进仓库。
