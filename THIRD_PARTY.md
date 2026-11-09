# 第三方来源

`vendor/VSR` 只包含运行本管线所需的作者生成器、原生后处理代码、词表和许可证，不包含上游模型、数据集、图片或安装环境。

- 上游：https://github.com/InternLM/VSR
- 固定提交：`1fd040346add205ffbada9748273cad3bc9159e5`
- `chart_generation/*.py`、`chart_generation/words.txt`、`data_pipeline/*.py` 为固定上游源码/运行资源。
- 许可证：Apache License 2.0，见 [vendor/VSR/LICENSE](vendor/VSR/LICENSE)。

Vega-Lite、Vega 和 Resvg 通过 npm 安装，版本固定在 `package.json`。字体由 `bootstrap.py` 按 VSR 配置下载到项目本地，字体文件不纳入 Git；使用与再分发应遵循各字体本身的许可。

设计参考：[ChartCoder](https://github.com/thunlp/ChartCoder/tree/main/data_generator)、[Vega-Lite 官方示例](https://vega.github.io/vega-lite/examples/)。本项目没有将这些项目的数据集或安装目录打包进仓库。
