"""Scientific radar geometry and PNG resolution regressions."""
import json
import os
from pathlib import Path
import shutil
import subprocess
import unittest

from generation.sampling_policy import EXTENSIONS, validate

ROOT = Path(__file__).resolve().parents[1]


class RadarRenderTests(unittest.TestCase):
    def test_expanded_scan_controls_are_accepted(self):
        policy = json.loads((ROOT / 'configs/chartarena-scan-extensions.json').read_text())['sampling']
        validate(policy, EXTENSIONS)
        for field, value in [('category_count', 37), ('series_count', 9), ('variant', 'unknown'),
                             ('radial_max', 0), ('layout', 'faceted'), ('per_dimension_scale', True)]:
            with self.subTest(field=field), self.assertRaises(ValueError):
                validate({'weighted': {'radar': {field: [{'value': value, 'weight': 1}]}}}, EXTENSIONS)

    def test_radial_rendering_and_png_density(self):
        node = shutil.which('node')
        if not node:
            self.skipTest('Node is required for radar target rendering')
        program = r'''
import assert from 'node:assert/strict';
import {renderRadarSource} from './radar_render.mjs';
import {pngAt200Dpi} from './png_metadata.mjs';
import {writeTables} from './export_tables.mjs';
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
        y: {field: 'value', type: 'quantitative', scale: {domain: [0, 10]}},
        color: {field: 'series', type: 'nominal'}},
      usermeta: {chartType: 'radar'}};
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
    if (variant === 'line' && count === 4) {
      const directory = fs.mkdtempSync(path.join(os.tmpdir(), 'radar-tables-'));
      try {
        writeTables(directory, compact);
        assert.equal(fs.readFileSync(path.join(directory, 'data.md'), 'utf8').split('\n').length,
          rows.length + 2);
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
