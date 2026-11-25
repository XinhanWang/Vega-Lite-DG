"""Exercise the standalone ChartArena extension generator and its artifacts."""
import csv
import json
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]


class CombinationTests(unittest.TestCase):
    def test_standalone_render_and_export(self):
        node = shutil.which("node")
        if not node or not (ROOT / "node_modules/vega-lite").is_dir():
            self.skipTest("Requires Node and the pinned Vega-Lite runtime")
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            config = root / "config.json"
            output = root / "out"
            config.write_text(json.dumps({
                "seed": 20261124, "counts": {"radar": 1, "combination": 40}, "target_side": 400,
                "sampling": {"label_probability": {"combination": 1},
                             "weighted": {"combination": {"error_bars": [
                                 {"value": True, "weight": 1}, {"value": False, "weight": 1},
                             ]}}},
            }))
            run = subprocess.run(
                [node, "generate_chartarena_extensions.mjs", str(config), str(output)],
                cwd=ROOT, capture_output=True, text=True, timeout=120,
            )
            self.assertEqual(run.returncode, 0, run.stderr)
            self.assertEqual(json.loads((output / "validation.json").read_text())["accepted"], 41)

            structures, error_states = set(), set()
            targets = []
            percent_found = False
            for entry in map(json.loads, (output / "manifest.jsonl").read_text().splitlines()):
                sample = output / entry["sample"]
                compact = json.loads((output / entry["compact"]).read_text())
                full = json.loads((output / entry["full"]).read_text())
                self.assertGreater((sample / "chart.png").stat().st_size, 1024)
                self.assertGreater((sample / "compact.png").stat().st_size, 1024)
                tables = compact["usermeta"]["table_export"]["tables"]
                if entry["kind"] == "radar":
                    self.assertEqual(compact["usermeta"]["chartType"], "radar")
                    self.assertIsNone(compact["encoding"]["y"]["title"])
                    self.assertEqual(tables, [{"id": "data", "path": "/data/values"}])
                    full_rows = next(source["values"] for source in full["data"] if source["name"] == "observations")
                    expected = compact["data"]["values"]
                    self.assertEqual([{key: row[key] for key in expected[0]} for row in full_rows], expected)
                    self.check_table(sample, "data", expected)
                    continue

                targets.append(compact)
                layers = compact["layer"]
                line_index = len(layers) - 1
                line = layers[line_index]
                grouped = "layer" in layers[0]
                bar_layers = layers[0]["layer"] if grouped else layers[:-1]
                errors = len(bar_layers) == 2
                dual = "resolve" in compact
                error_states.add((dual, errors))
                self.assertEqual(grouped, dual and errors)
                if grouped:
                    self.assertEqual(line_index, 1)
                self.assertEqual([layer["mark"] for layer in bar_layers],
                                 [{"type": kind} for kind in (["bar", "errorbar"] if errors else ["bar"])])
                self.assertEqual(line["mark"], {"type": "line"})
                for layer in layers + bar_layers:
                    self.assertEqual("layer" in layer, grouped and layer is layers[0])
                    self.assertEqual("data" in layer, layer is line)
                    self.assertNotIn("transform", layer)
                self.assertNotIn("transform", compact)
                self.assertEqual(tables, [
                    {"id": "bars", "path": "/data/values"},
                    {"id": "lines", "path": f"/layer/{line_index}/data/values"},
                ])

                bar_rows, line_rows = compact["data"]["values"], line["data"]["values"]
                series_counts = [len({row["series"] for row in rows}) for rows in (bar_rows, line_rows)]
                offset = {"xOffset": {"field": "series", "type": "nominal", "sort": None}} if series_counts[0] > 1 else {}
                self.assertEqual(bar_layers[0].get("encoding"), None if grouped else offset or None)
                if grouped:
                    self.assertEqual(layers[0].get("encoding"), offset or None)
                if errors:
                    self.assertEqual(bar_layers[1]["encoding"], {
                        **({} if grouped else offset),
                        "y": {"field": "lower", "type": "quantitative"}, "y2": {"field": "upper"},
                    })
                    self.assertTrue(all(row["lower"] <= row["value"] <= row["upper"] for row in bar_rows))

                self.assertEqual(set(compact["encoding"]), {"x", "y", "color"})
                left_y = compact["encoding"]["y"]
                self.assertEqual(left_y["field"], "value")
                self.assertNotIn("stack", left_y)
                self.assertNotIn("scale", left_y)
                if dual:
                    self.assertEqual(compact["resolve"], {"scale": {"y": "independent"}})
                    self.assertEqual(set(line["encoding"]), {"y"})
                    self.assertNotIn("scale", line["encoding"]["y"])
                else:
                    self.assertNotIn("encoding", line)
                structures.add((series_counts[0] > 1, series_counts[1] > 1, dual))

                right_y = line.get("encoding", {}).get("y", left_y)
                for table, definition, rows, full_layer in zip(tables, (left_y, right_y),
                                                               (bar_rows, line_rows), full["layer"], strict=True):
                    self.assertEqual(full_layer["data"]["values"], rows)
                    self.assertTrue(all("series" in row and "series_role" not in row for row in rows))
                    self.check_table(sample, table["id"], rows)
                    if "%" in definition["title"]:
                        self.assertEqual(definition["axis"]["format"], ".4~p")
                        self.assertTrue(all(abs(row["value"]) < 1 for row in rows))
                        percent_found = True
            self.assertEqual(len(structures), 8)
            self.assertEqual(error_states, {(False, False), (False, True), (True, False), (True, True)})
            self.assertTrue(percent_found)
            self.check_compact_geometry(node, targets)

    def check_compact_geometry(self, node, targets):
        program = r"""
import assert from 'node:assert/strict';
import fs from 'node:fs';
import {combinationDrawing, validateCombination} from './combination.mjs';
import {compile} from 'vega-lite';
import * as vega from 'vega';

const targets = JSON.parse(fs.readFileSync(0, 'utf8'));
const close = (a, b) => assert(Math.abs(a - b) < 1e-6, `${a} differs from ${b}`);
for (const target of targets) {
  const spec = compile(target).spec;
  const axes = Object.fromEntries(spec.axes.filter(axis => !axis.grid).map(axis => [axis.orient, axis.scale]));
  const yScales = spec.scales.filter(scale => scale.name === 'y' || scale.name.endsWith('_y'));
  assert.equal(yScales.length, target.resolve ? 2 : 1);
  const view = new vega.View(vega.parse(spec), {renderer: 'none'});
  await view.runAsync();
  const rows = target.data.values;
  const series = [...new Set(rows.map(row => row.series))];
  const offset = series.length > 1 ? view.scale('xOffset') : null;
  if (offset) assert.deepEqual(offset.domain(), series);
  const x = view.scale(axes.bottom);
  assert.deepEqual(x.domain(), [...new Set(rows.map(row => row.category))]);
  const left = view.scale(axes.left);
  const right = view.scale(axes.right ?? axes.left);
  const marks = {rect: [], rule: [], line: []};
  function visit(item) {
    const type = item.mark?.marktype;
    if (marks[type] && item.datum?.category && item.datum?.series) marks[type].push(item);
    for (const child of item.items ?? []) visit(child);
  }
  visit(view.scenegraph().root);
  assert.equal(marks.rect.length, rows.length);
  assert.equal(marks.rule.length, rows.filter(row => 'lower' in row).length);
  assert.equal(marks.line.length, target.layer.at(-1).data.values.length);
  for (const item of [...marks.rect, ...marks.rule]) {
    const {category, series, value, lower, upper} = item.datum;
    const interval = item.mark.marktype === 'rule';
    const center = x(category) + (offset ? offset(series) + offset.bandwidth() / 2 : x.bandwidth() / 2);
    close(item.x + (item.width ?? 0) / 2, center);
    const actual = [item.y, item.y2].sort((a, b) => a - b);
    const expected = (interval ? [lower, upper] : [0, value]).map(left).sort((a, b) => a - b);
    actual.forEach((pixel, index) => close(pixel, expected[index]));
  }
  for (const item of marks.line) {
    close(item.x, x(item.datum.category) + x.bandwidth() / 2);
    close(item.y, right(item.datum.value));
  }
  view.finalize();
}

const log = targets.find(target => target.resolve && target.layer.at(-1).data.values.every(row => row.value > 0));
const scale = {type: 'log', base: 2};
log.layer.at(-1).encoding.y.scale = scale;
validateCombination(log);
const full = combinationDrawing(log, {text: '#000', grid: '#ddd', colors: ['#000']}, {
  width: 400, height: 240, legend: 'top', gridDash: [], lineDash: [], groupGap: .1,
  barWidth: .8, labelSize: 11, lineWidth: 2, categoryGap: .24, rotation: 0,
});
assert.deepEqual(full.layer.at(-1).encoding.y.scale, scale);
assert(compile(full).spec.scales.some(scale => scale.type === 'log' && scale.base === 2));
"""
        result = subprocess.run(
            [node, "--input-type=module", "-e", program], input=json.dumps(targets),
            cwd=ROOT, capture_output=True, text=True, timeout=60,
        )
        self.assertEqual(result.returncode, 0, result.stderr)

    def check_table(self, sample, table_id, rows):
        with (sample / f"{table_id}.csv").open(encoding="utf-8-sig", newline="") as stream:
            headers, *csv_rows = csv.reader(stream)
        markdown = (sample / f"{table_id}.md").read_text().splitlines()
        expected = [[str(value) for value in row.values()] for row in rows]
        self.assertEqual(csv_rows, expected)
        self.assertEqual(markdown[0], "| " + " | ".join(headers) + " |")
        self.assertEqual(markdown[2:], ["| " + " | ".join(row) + " |" for row in expected])
