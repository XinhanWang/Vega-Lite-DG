"""Scientific radar geometry and PNG resolution regressions."""
import json
from pathlib import Path
import shutil
import subprocess
import unittest
from unittest.mock import patch

from generation.sampling_policy import EXTENSIONS, plan, radar_label_factor, unit, validate

ROOT = Path(__file__).resolve().parents[1]


class RadarRenderTests(unittest.TestCase):
    def test_expanded_scan_controls_are_accepted(self):
        policy = json.loads((ROOT / 'configs/chartarena-scan-extensions.json').read_text())['sampling']
        validate(policy, EXTENSIONS)
        for field, value in [('category_count', 37), ('series_count', 9), ('variant', 'unknown'),
                             ('radial_max', 0), ('layout', 'faceted'), ('per_dimension_scale', True)]:
            with self.subTest(field=field), self.assertRaises(ValueError):
                validate({'weighted': {'radar': {field: [{'value': value, 'weight': 1}]}}}, EXTENSIONS)

    @staticmethod
    def policy(dimensions, series, variant="line"):
        return {"weighted": {"radar": {
            "category_count": [{"value": dimensions, "weight": 1}],
            "series_count": [{"value": count, "weight": 9 - count} for count in series],
            "variant": [{"value": variant, "weight": 1}],
            "closed": [{"value": False, "weight": 1}],
            "point": [{"value": True, "weight": 1}],
            "dashed": [{"value": True, "weight": 1}],
            "stroke_width": [{"value": 3, "weight": 1}],
        }}, "label_probability": {"radar": .5}}

    def test_series_weights_are_conditioned_at_dimension_boundaries(self):
        for dimensions, limit in [(4, 8), (8, 8), (9, 6), (15, 6), (16, 4), (23, 4), (24, 3), (36, 3)]:
            with self.subTest(dimensions=dimensions):
                original = self.policy(dimensions, range(1, 9))
                filtered = self.policy(dimensions, range(1, limit + 1))
                chosen = set()
                for seed in range(128):
                    actual = plan("radar", seed, original)
                    self.assertEqual(actual, plan("radar", seed, filtered))
                    self.assertEqual(actual[1]["category_count"], dimensions)
                    chosen.add(actual[1]["series_count"])
                self.assertEqual(chosen, set(range(1, limit + 1)))

    def test_density_scales_the_configured_label_probability(self):
        for points, factor in [(24, 1), (25, .5), (48, .5), (49, .2), (72, .2), (73, 0)]:
            self.assertEqual(radar_label_factor(points), factor)
        for dimensions, series, cutoff in [(4, 6, .5), (5, 5, .25), (8, 6, .25),
                                           (7, 7, .1), (12, 6, .1), (25, 3, 0)]:
            policy = self.policy(dimensions, [series])
            for value in (0, max(0, cutoff - .01), cutoff):
                def draw(kind, seed, field):
                    return value if field == "value_labels" else unit(kind, seed, field)
                with self.subTest(dimensions=dimensions, series=series, draw=value), patch(
                    "generation.sampling_policy.unit", side_effect=draw
                ):
                    self.assertEqual(plan("radar", 9, policy)[0]["value_labels"], value < cutoff)

    def test_radar_variant_constraints(self):
        for variant in ("line", "filled", "polar_bar", "stacked_polar_bar"):
            for seed in range(24):
                with self.subTest(variant=variant):
                    _, choices = plan("radar", seed, self.policy(8, range(1, 9), variant))
                    if variant == "line":
                        self.assertIs(choices["closed"], False)
                        self.assertIs(choices["point"], True)
                    elif variant == "filled":
                        self.assertIs(choices["closed"], True)
                        self.assertLessEqual(choices["series_count"], 4)
                    else:
                        self.assertFalse({"closed", "point", "dashed", "stroke_width"} & choices.keys())
                        if variant == "stacked_polar_bar":
                            self.assertGreaterEqual(choices["series_count"], 2)
        with self.assertRaisesRegex(ValueError, "No radar series_count weight"):
            plan("radar", 0, self.policy(4, [1], "stacked_polar_bar"))

    def test_radial_rendering_and_png_density(self):
        node = shutil.which('node')
        if not node:
            self.skipTest('Node is required for radar target rendering')
        program = r'''
import assert from 'node:assert/strict';
import {radarPreview, renderRadarSource} from './radar_render.mjs';
import {pngAt200Dpi} from './png_metadata.mjs';
import {exportTables, writeTables} from './export_tables.mjs';
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
for (const variant of ['line', 'filled', 'polar_bar', 'stacked_polar_bar']) {
  for (const count of [4, 12, 24, 36]) {
    const categories = Array.from({length: count}, (_, i) => 'Dimension ' + i);
    const rows = categories.flatMap(category => [
      {category, series: 'A', value: 2}, {category, series: 'B', value: 3}]);
    const compact = {title: 'Radar test', data: {values: rows}, mark: {type: 'line'},
      encoding: {x: {field: 'category', type: 'nominal', sort: categories},
        y: {field: 'value', type: 'quantitative', title: null, scale: {domain: [0, 10]}},
        color: {field: 'series', type: 'nominal'}},
      usermeta: {chartType: 'radar', table_export: {tables: [{id: 'data', path: '/data/values'}]}}};
    const options = {variant, grid: 'circle', rotation: -90, tickCount: 5, point: true,
      strokeWidth: 2, strokeDash: []};
    const before = JSON.stringify(compact);
    const drawing = renderRadarSource(compact, options);
    assert.equal(JSON.stringify(compact), before);
    const points = drawing.data.find(d => d.name === 'observations').values;
    assert.deepEqual(points.map(({category, series, value}) => ({category, series, value})), rows);
    const {radius} = drawing.usermeta.radarGeometry;
    assert.equal(points[0].__outer, radius * .2);
    assert.equal(points[1].__outer, radius * (variant === 'stacked_polar_bar' ? .5 : .3));
    assert.equal(points[1].__inner, variant === 'stacked_polar_bar' ? radius * .2 : 0);
    assert.equal(drawing.data.filter(d => d.name === 'observations').length, 1);
    assert.equal(drawing.data.find(d => d.name === 'ticks').values.at(-1).label, '10');
    assert.equal(drawing.data.find(d => d.name === 'labels').values.length, count);
    assert.equal(drawing.data.find(d => d.name === 'legend').values.length, 2);
    assert(!drawing.data.some(source => source.name === 'valueLabels'));
    if (variant === 'filled') {
      const dataMarks = drawing.marks.find(mark => mark.from?.facet?.name === 'series').marks;
      assert.equal(dataMarks[0].encode.enter.interpolate.value, 'linear-closed');
      assert.throws(() => renderRadarSource(compact, {...options, closed: false}), /closed outline/);
    }
    if (variant === 'stacked_polar_bar') {
      const single = {...compact, data: {values: rows.filter(row => row.series === 'A')}};
      assert.throws(() => renderRadarSource(single, options), /at least two series/);
      const excessive = rows.map((row, i) => i < 2 ? {...row, value: 6} : row);
      assert.throws(() => renderRadarSource({...compact, data: {values: excessive}}, options), /domain/);
    }
    if (variant === 'line' && count === 4) {
      const clustered = {...compact, data: {values: rows.map(row => ({...row, value: .05}))}};
      const labeled = renderRadarSource(clustered, {...options, valueLabels: true});
      const densePoints = labeled.data.find(source => source.name === 'observations').values;
      assert(densePoints.some(point => point.__label === null));
      assert(densePoints.some(point => point.__label === '0.05'));
      assert(densePoints.every(point => point.value === .05));
      assert(labeled.data.some(source => source.name === 'valueLabels'));
      const directory = fs.mkdtempSync(path.join(os.tmpdir(), 'radar-tables-'));
      try {
        const [table] = exportTables(compact);
        assert.deepEqual(table.rows, rows);
        writeTables(directory, compact);
        assert.equal(fs.readFileSync(path.join(directory, 'data.md'), 'utf8'), table.markdown);
        assert.equal(fs.readFileSync(path.join(directory, 'data.csv'), 'utf8'), table.csv);
        assert(!JSON.stringify(radarPreview(compact)).includes('Score'));
        const legacy = {...compact, usermeta: {chartType: 'radar'}};
        assert.throws(() => writeTables(directory, legacy), /table_export/);
        assert.throws(() => radarPreview(legacy));
        assert.equal(JSON.stringify(compact), before);
      } finally {
        fs.rmSync(directory, {recursive: true});
      }
    }
    compact.data.values[0].value = 11;
    assert.throws(() => renderRadarSource(compact, options), /domain/);
  }
}
const png = Buffer.from('iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+aG0YAAAAASUVORK5CYII=', 'base64');
const tagged = pngAt200Dpi(png);
assert.deepEqual(pngAt200Dpi(tagged), tagged);
const position = tagged.indexOf(Buffer.from('pHYs'));
assert.equal(tagged.readUInt32BE(position + 4), 7874);
assert.equal(tagged.readUInt32BE(position + 8), 7874);
assert.equal(tagged[position + 12], 1);
assert.throws(() => pngAt200Dpi(Buffer.from('invalid')), /PNG/);
console.log('16 radar structures and PNG density verified');
'''
        result = subprocess.run([node, '--input-type=module', '-e', program], cwd=ROOT,
                                capture_output=True, text=True, timeout=30)
        self.assertEqual(result.returncode, 0, result.stderr)
