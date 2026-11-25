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
        for field, value in [('category_count', 37), ('series_count', 9), ('variant', 'unknown'), ('radial_max', 0)]:
            with self.subTest(field=field), self.assertRaises(ValueError):
                validate({'weighted': {'radar': {field: [{'value': value, 'weight': 1}]}}}, EXTENSIONS)

    def test_radial_rendering_and_png_density(self):
        node = shutil.which('node')
        if not node:
            self.skipTest('Node is required for radar target rendering')
        program = r'''
import assert from 'node:assert/strict';
import {renderRadarTarget} from './radar_render.mjs';
import {pngAt200Dpi} from './png_metadata.mjs';
for (const variant of ['line', 'filled', 'polar_bar', 'stacked_polar_bar']) {
  for (const count of [4, 12, 24, 36]) {
    const categories = Array.from({length: count}, (_, i) => 'Dimension ' + i);
    const rows = categories.flatMap(category => [
      {category, series: 'A', value: 2}, {category, series: 'B', value: 3}]);
    const compact = {title: 'Radar test', data: {values: rows}, mark: {type: 'line', point: true},
      encoding: {x: {sort: categories}, y: {scale: {domain: [0, 10]}}},
      usermeta: {chartType: 'radar', radar: {variant, grid: 'circle', rotation: -90, tickCount: 5}}};
    const before = JSON.stringify(compact);
    const drawing = renderRadarTarget(compact);
    assert.equal(JSON.stringify(compact), before);
    const points = drawing.data.find(d => d.name === 'observations').values;
    assert.deepEqual(points.map(({category, series, value}) => ({category, series, value})), rows);
    const {radius} = drawing.usermeta.radarGeometry;
    assert.equal(points[0].__outer, radius * .2);
    assert.equal(points[1].__outer, radius * (variant === 'stacked_polar_bar' ? .5 : .3));
    assert.equal(points[1].__inner, variant === 'stacked_polar_bar' ? radius * .2 : 0);
    compact.usermeta.radar.dimensionDomains = Object.fromEntries(categories.map(c => [c, [0, 20]]));
    assert.equal(renderRadarTarget(compact).data[0].values[0].__outer, radius * .1);
    compact.data.values[0].value = 21;
    assert.throws(() => renderRadarTarget(compact), /domain/);
  }
}
const categories = ['North', 'East', 'South', 'West'];
const panelRows = categories.flatMap(category => ['A', 'B', 'C'].map(series => ({category, series, value: 3})));
const panels = renderRadarTarget({title: 'Panels', mark: {type: 'line'}, data: {values: panelRows},
  encoding: {x: {sort: categories}, y: {scale: {domain: [0, 10]}}},
  usermeta: {radar: {variant: 'line', layout: 'faceted', grid: 'polygon', rotation: 0, tickCount: 4}}});
assert.equal(panels.marks.length, 3);
assert.equal(panels.data[0].values.length, panelRows.length);
const legacyView = {marks: []};
assert.equal(renderRadarTarget({usermeta: {}}, legacyView), legacyView);
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
