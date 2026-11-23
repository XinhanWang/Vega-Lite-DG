import assert from 'node:assert/strict';
import {writeTables} from './export_tables.mjs';
import {spawnSync} from 'node:child_process';
import {createHash} from 'node:crypto';
import fs from 'node:fs';
import path from 'node:path';
import vm from 'node:vm';
import {Resvg} from '@resvg/resvg-js';
import * as vega from 'vega';
import * as vl from 'vega-lite';

const [configFile, output, studioDirectory, adapterDirectory] = process.argv.slice(2);
if (!adapterDirectory) {
  throw new Error('Usage: node generate_chartarena_extensions.mjs CONFIG OUTPUT STUDIO_DIR ADAPTER_DIR');
}
const read = file => JSON.parse(fs.readFileSync(file, 'utf8'));
const write = (file, value) => fs.writeFileSync(file, JSON.stringify(value, null, 2) + '\n');
const plain = value => JSON.parse(JSON.stringify(value));
const config = read(configFile);
const {radar, combination} = config.counts;
for (const value of [config.seed, radar, combination, config.target_side]) {
  assert(Number.isSafeInteger(value) && value > 0, 'Expected positive seed, counts and target size');
}
assert.deepEqual(Object.keys(config.counts).sort(), ['combination', 'radar']);

const studio = fs.readFileSync(path.join(studioDirectory, 'studio.js'), 'utf8').split('const $=id=>')[0];
const context = vm.createContext({});
vm.runInContext(studio + ';globalThis.api={defaultProject,makeSpec,importSpec,renderSpec};', context);
const {defaultProject, makeSpec, importSpec, renderSpec} = context.api;
const schema = 'https://vega.github.io/schema/vega-lite/v6.json';

function randomSource(kind, index) {
  let counter = 0;
  return (min, max) => {
    const key = `${config.seed}:${kind}:${index}:${counter++}`;
    const number = createHash('sha256').update(key).digest().readUInt32BE();
    return min + Math.floor(number / 2 ** 32 * (max - min + 1));
  };
}

const radarThemes = [
  ['Model evaluation', ['Accuracy', 'Stability', 'Efficiency', 'Coverage', 'Robustness', 'Clarity', 'Latency', 'Recall']],
  ['Service survey', ['Speed', 'Support', 'Access', 'Usability', 'Quality', 'Trust', 'Value', 'Reliability']],
  ['Site assessment', ['Transit', 'Safety', 'Capacity', 'Amenities', 'Cost', 'Access', 'Noise', 'Location']],
  ['Product testing', ['Design', 'Handling', 'Power', 'Durability', 'Comfort', 'Setup', 'Precision', 'Finish']],
];

function radarSpec(index) {
  const rand = randomSource('radar', index);
  const [title, pool] = radarThemes[index % radarThemes.length];
  const categories = pool.slice(0, rand(4, pool.length));
  const names = ['Group A', 'Group B', 'Group C'].slice(0, 1 + index % 3);
  const multiple = names.length > 1;
  const rows = categories.flatMap(category => names.map(series => ({
    category, value: rand(23, 96), ...(multiple ? {series} : {}),
  })));
  return {
    title,
    data: {values: rows},
    mark: {type: 'bar'},
    encoding: {
      x: {field: 'category', type: 'nominal', sort: categories},
      y: {field: 'value', type: 'quantitative', title: 'Score', scale: {domain: [0, 100]}},
      ...(multiple ? {
        xOffset: {field: 'series', type: 'nominal'},
        color: {field: 'series', type: 'nominal'},
      } : {}),
    },
    usermeta: {chartType: 'radar', table_export: {tables: [{id: 'data', path: '/data/values'}]}},
  };
}

const combinationThemes = [
  ['Orders and targets', 'Orders', 'Target', 'Orders', 'Fulfilment (%)'],
  ['Energy use and baseline', 'Usage', 'Baseline', 'Energy (MWh)', 'Demand (kW)'],
  ['Attendance and plan', 'Attendance', 'Plan', 'Visitors', 'Occupancy (%)'],
  ['Delivery and forecast', 'Delivered', 'Forecast', 'Units', 'On time (%)'],
];
const months = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep'];

function combinationSpec(index) {
  const rand = randomSource('combination', index);
  const [title, barName, lineName, yTitle, rightYTitle] = combinationThemes[Math.floor(index / 2) % combinationThemes.length];
  const project = defaultProject('barline_n');
  project.title = title;
  project.xTitle = 'Month';
  project.yTitle = yTitle;
  project.dualYAxis = index % 2 === 1;
  project.rightYTitle = project.dualYAxis ? rightYTitle : '';
  project.categories = months.slice(0, rand(5, months.length));
  project.categoryObjects = project.categories.map(category => ({key: category, name: category}));
  project.errorBars = Math.floor(index / 2) % 3 === 0;
  project.series[0].name = barName;
  project.series[1].name = project.dualYAxis ? rightYTitle.replace(/ \(.*/, '') : lineName;
  const start = rand(35, 90);
  const drift = rand(-2, 5);
  const measured = project.categories.map((_, i) => start + i * drift + rand(-15, 15));
  project.rows = project.series.flatMap(series => project.categories.map((category, i) => {
    const bar = series.role === 'bar';
    const value = bar ? measured[i] : project.dualYAxis ? rand(57, 97) : measured[i] + rand(-14, 20);
    return {category, value, series: series.name, _categoryKey: category, _seriesKey: series.key,
      ...(bar && project.errorBars ? {lower: value - rand(1, 5), upper: value + rand(2, 7)} : {})};
  }));
  const compact = plain(makeSpec(project));
  assert.deepEqual(plain(makeSpec(importSpec(compact))), compact);
  assert.deepEqual(tableRows(compact).map(row => row.value), plain(project.rows).map(row => row.value));
  return compact;
}

const radarTargets = Array.from({length: radar}, (_, index) => radarSpec(index));
const radarProjection = spawnSync('python3', ['-B', '-c',
  'import json,sys; from chart_gt_adapter.extensions import radar_to_vega; json.dump([radar_to_vega(s) for s in json.load(sys.stdin)],sys.stdout)'],
{input: JSON.stringify(radarTargets.map(spec => ({...spec, usermeta: {chartType: 'radar'}}))), cwd: adapterDirectory, encoding: 'utf8', maxBuffer: 16 * 1024 * 1024});
assert.equal(radarProjection.status, 0, radarProjection.stderr || String(radarProjection.error ?? 'Radar adapter failed'));
const radarViews = JSON.parse(radarProjection.stdout);
assert.equal(radarViews.length, radarTargets.length);

function fullRadar(compact, drawing) {
  const rows = drawing.data.find(source => source.name === 'observations').values;
  const keys = rows => rows.map(({category, value, series}) => JSON.stringify([category, value, series])).sort();
  assert.deepEqual(keys(rows), keys(compact.data.values));
  for (const row of rows) {
    assert(Math.abs(Math.hypot(row.__px - 250, row.__py - 235) - 1.8 * row.value) < 1e-8);
  }
  if (!compact.encoding.color) {
    drawing.marks = drawing.marks.filter(mark => mark.from?.data !== 'legend');
  }
  drawing.background = '#ffffff';
  return drawing;
}

function tableRows(spec) {
  return spec.usermeta.table_export.tables.flatMap(({path}) =>
    path.slice(1).split('/').reduce((node, key) => node[key], spec));
}

const training = [];
const manifest = [];
fs.mkdirSync(output);
write(path.join(output, 'config.json'), config);

async function render(kind, index, compact, full, compiled) {
  const id = `${kind}-${String(index).padStart(6, '0')}`;
  const relative = `samples/${id}`;
  const directory = path.join(output, relative);
  const view = new vega.View(vega.parse(compiled), {renderer: 'none', logLevel: vega.Warn});
  let svg;
  try {
    await view.runAsync();
    svg = await view.toSVG();
  } finally {
    view.finalize();
  }
  assert(svg.includes('<svg') && svg.includes(compact.title));
  const svgCanvas = svg.match(/width="([\d.]+)" height="([\d.]+)"/);
  assert(svgCanvas, 'Vega rendered without canvas dimensions');
  const mode = Number(svgCanvas[1]) >= Number(svgCanvas[2]) ? 'width' : 'height';
  const png = new Resvg(svg, {fitTo: {mode, value: config.target_side}}).render().asPng();
  assert(png.subarray(0, 8).equals(Buffer.from([137, 80, 78, 71, 13, 10, 26, 10])));
  fs.mkdirSync(directory, {recursive: true});
  const fullName = kind === 'radar' ? 'full.vega.json' : 'full.vl.json';
  write(path.join(directory, fullName), full);
  write(path.join(directory, 'compact.vl.json'), compact);
  writeTables(directory, compact);
  fs.writeFileSync(path.join(directory, 'chart.svg'), svg);
  fs.writeFileSync(path.join(directory, 'chart.png'), png);
  const entry = {id, kind, status: 'accepted', sample: relative, image: `${relative}/chart.png`,
    full: `${relative}/${fullName}`, compact: `${relative}/compact.vl.json`,
    observations: tableRows(compact).length, svg_sha256: createHash('sha256').update(svg).digest('hex'),
    png_sha256: createHash('sha256').update(png).digest('hex')};
  manifest.push(entry);
  training.push({id, image: entry.image, messages: [
    {role: 'user', content: '将图表转换为精简 Vega-Lite JSON。'},
    {role: 'assistant', content: JSON.stringify(compact)},
  ]});
}

for (const [index, compact] of radarTargets.entries()) {
  const drawing = fullRadar(compact, radarViews[index]);
  await render('radar', index, compact, drawing, drawing);
}
for (let index = 0; index < combination; index++) {
  const compact = combinationSpec(index);
  const full = {$schema: schema, ...plain(renderSpec(compact)), width: 510, height: 290, background: '#ffffff'};
  assert.deepEqual(tableRows(full), tableRows(compact));
  const warnings = [];
  const logger = vega.logger(vega.Warn, (_, level, ...messages) => warnings.push([level, ...messages]));
  const compiled = vl.compile(full, {logger}).spec;
  assert.deepEqual(warnings, [], 'Vega-Lite reported a compilation diagnostic');
  await render('combination', index, compact, full, compiled);
}
for (const [name, records] of [['manifest', manifest], ['train', training]]) {
  fs.writeFileSync(path.join(output, name + '.jsonl'), records.map(record => JSON.stringify(record)).join('\n') + '\n');
}
write(path.join(output, 'validation.json'), {
  requested: radar + combination, accepted: manifest.length, rejected: 0, counts: config.counts,
});
console.log(JSON.stringify({accepted: manifest.length, counts: config.counts, vega: vega.version, vega_lite: vl.version}));
