import assert from 'node:assert/strict';
import {writeTables} from './export_tables.mjs';
import {spawnSync} from 'node:child_process';
import {createHash} from 'node:crypto';
import fs from 'node:fs';
import path from 'node:path';
import vm from 'node:vm';
import {fileURLToPath} from 'node:url';
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
const root = path.dirname(fileURLToPath(import.meta.url));
const fontName = 'Noto Sans CJK SC';
const fontFile = path.join(root, 'assets/fonts/NotoSansCJKsc-Regular.otf');
const batchSize = 128;

function planBatch(kind, start, count) {
  if (!config.sampling) return Array(count).fill(undefined);
  const planning = spawnSync('python3', ['-B', '-c', `
import json, sys
from generation.sampling_policy import EXTENSIONS, RADAR_THEMES, THEMES, plan, validate
from generation.chart_text import sample_chart_text
from workflow.config import task_seed
cfg = json.load(sys.stdin)
validate(cfg['sampling'], EXTENSIONS)
kind, start, count = sys.argv[1], int(sys.argv[2]), int(sys.argv[3])
output = []
for index in range(start, start + count):
    seed = task_seed(cfg['seed'], kind, index)
    sample, choices = plan(kind, seed, cfg['sampling'])
    theme = sample.get('theme', 0)
    item = dict(sample=sample, choices=choices, theme=THEMES[theme],
                radar=RADAR_THEMES[theme % len(RADAR_THEMES)])
    if sample.get('text_profile') == 'expanded-v1':
        item['words'] = sample_chart_text(kind, seed, sample['language'], 12,
                                         4 if kind == 'radar' else 2)
    output.append(item)
json.dump(output, sys.stdout, ensure_ascii=False)
`, kind, String(start), String(count)], {cwd: root, input: JSON.stringify(config),
                                       encoding: 'utf8', maxBuffer: 16 * 1024 * 1024});
  assert.equal(planning.status, 0, planning.stderr || String(planning.error));
  const items = JSON.parse(planning.stdout);
  if (items.some(isChinese)) {
    assert(fs.existsSync(fontFile), 'Chinese font missing. Run python bootstrap.py --with-cjk');
  }
  return items;
}

const isChinese = item => item?.sample.language === 'zh';
const appearances = {
  publication_clean: {background: '#ffffff', text: '#20252b', grid: '#e2e5e7', colors: ['#4074a7','#bf6725','#418766','#a45382']},
  compact_report: {background: '#fafbf8', text: '#23392f', grid: '#d4ded8', colors: ['#367459','#a57136','#4b659e','#ac5755']},
  monochrome_minimal: {background: '#ffffff', text: '#242424', grid: '#dedede', colors: ['#37506a','#777777','#161616','#8d7866']},
  colorful_analytic: {background: '#ffffff', text: '#252131', grid: '#e8e3ed', colors: ['#755497','#ce6956','#2b867f','#a57722']},
  editorial: {background: '#faf6ee', text: '#382a22', grid: '#e9dfd1', colors: ['#ad5446','#497389','#8f7743','#65547d']},
  dark_contrast: {background: '#242831', text: '#f1f0eb', grid: '#555962', colors: ['#78aeed','#f1a463','#7dc7a2','#d5a4cd']},
};
const appearance = item => appearances[item?.choices.profile] ?? appearances.publication_clean;
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

function radarSpec(index, item) {
  const rand = randomSource('radar', index);
  const [baseTitle, pool] = isChinese(item) ? item.radar : radarThemes[index % radarThemes.length];
  const dimensionCount = item?.choices.category_count ?? rand(4, pool.length);
  const categories = Array.from({length: dimensionCount}, (_, i) =>
    item?.words?.categories[i] ?? pool[i] ?? (isChinese(item) ? `指标${i+1}` : `Measure ${i+1}`));
  const names = (item?.words?.series ?? (isChinese(item) ? ['方案甲', '方案乙', '方案丙', '方案丁']
    : ['Group A', 'Group B', 'Group C', 'Group D'])).slice(0, item?.choices.series_count ?? (1 + index % 3));
  const multiple = names.length > 1;
  const radialMax = item?.choices.radial_max ?? 100;
  const rows = categories.flatMap(category => names.map(series => ({
    category, value: Number((rand(23, 96) * radialMax / 100).toPrecision(4)),
    ...(multiple ? {series} : {}),
  })));
  return {
    title: item?.words?.title ?? baseTitle,
    data: {values: rows},
    mark: {type: 'line'},
    encoding: {
      x: {field: 'category', type: 'nominal', sort: categories},
      y: {field: 'value', type: 'quantitative', title: isChinese(item) ? '得分' : 'Score', scale: {domain: [0, radialMax]}},
      ...(multiple ? {
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

function combinationSpec(index, item) {
  const rand = randomSource('combination', index);
  const defaults = isChinese(item)
    ? [item.theme[0] + '与目标比较', '实际值', '目标值', item.theme[1], '达成率 (%)']
    : combinationThemes[Math.floor(index / 2) % combinationThemes.length];
  const words = item?.words;
  const [title, barName, lineName, yTitle, rightYTitle] = words
    ? [words.title, ...words.series, words.value_axis, words.right_axis] : defaults;
  const project = defaultProject('barline_n');
  project.title = title;
  project.xTitle = words?.category_axis ?? (isChinese(item) ? '月份' : 'Month');
  project.yTitle = yTitle;
  project.dualYAxis = item?.choices.dual_axis ?? (index % 2 === 1);
  project.rightYTitle = project.dualYAxis ? rightYTitle : '';
  const categoryCount = item?.choices.category_count ?? rand(5, months.length);
  project.categories = Array.from({length:categoryCount}, (_, i) =>
    words ? words.categories[i] : isChinese(item) ? `${i+1}月` : months[i] ?? ['Oct','Nov','Dec'][i-9]);
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

function projectRadar(targets) {
  const radarProjection = spawnSync('python3', ['-B', '-c',
    'import json,sys; from chart_gt_adapter.extensions import radar_to_vega; json.dump([radar_to_vega(s) for s in json.load(sys.stdin)],sys.stdout)'],
    {input: JSON.stringify(targets.map(spec => ({...spec, usermeta: {chartType: 'radar'}}))),
     cwd: adapterDirectory, encoding: 'utf8', maxBuffer: 16 * 1024 * 1024});
  assert.equal(radarProjection.status, 0, radarProjection.stderr || String(radarProjection.error ?? 'Radar adapter failed'));
  const views = JSON.parse(radarProjection.stdout);
  assert.equal(views.length, targets.length);
  return views;
}

function prepareRadarPreview(compact, drawing, item) {
  const rows = drawing.data.find(source => source.name === 'observations').values;
  const keys = rows => rows.map(({category, value, series}) => JSON.stringify([category, value, series])).sort();
  assert.deepEqual(keys(rows), keys(compact.data.values));
  const [minimum, maximum] = compact.encoding.y.scale.domain;
  for (const row of rows) {
    const expected = 180 * (row.value - minimum) / (maximum - minimum);
    assert(Math.abs(Math.hypot(row.__px - 250, row.__py - 235) - expected) < 1e-8);
  }
  if (!compact.encoding.color) {
    drawing.marks = drawing.marks.filter(mark => mark.from?.data !== 'legend');
  }
  if (isChinese(item)) {
    drawing.config = {...drawing.config, text: {...drawing.config?.text, font: fontName}};
  }
  return drawing;
}

function fullRadar(drawing, item) {
  drawing.background = item ? appearance(item).background : '#ffffff';
  if (item) {
    const style = appearance(item);
    drawing.config = {...drawing.config, text: {...drawing.config?.text,
      ...(isChinese(item) ? {font:fontName} : {}), fill:style.text}};
    const recolor = node => {
      if (!node || typeof node !== 'object') return;
      for (const [key, value] of Object.entries(node)) {
        if (['stroke','fill'].includes(key) && value && /^#[0-9a-f]{6}$/i.test(value.value ?? '')) {
          const color = value.value.toLowerCase();
          const black = ['#222222','#333333','#555555','#000000'].includes(color);
          const grey = ['#d1d5db','#cccccc','#bbbbbb','#dddddd','#999999'].includes(color);
          if (black || grey) value.value = black ? style.text : style.grid;
        }
        if (key === 'font' && isChinese(item) && typeof value.value === 'string') value.value = fontName;
        recolor(value);
      }
    };
    recolor(drawing.marks);
    for (const scale of drawing.scales ?? []) {
      if (scale.type === 'ordinal' && Array.isArray(scale.range)) scale.range = style.colors;
    }
    const margin = Math.max(30, Math.round((drawing.height * (item.sample.aspect_ratio ?? 1) - drawing.width) / 2));
    drawing.padding = {top:30,bottom:30,left:margin,right:margin};
  }
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

async function renderImage(compiled, compact, item, id) {
  const view = new vega.View(vega.parse(compiled), {renderer: 'none', logLevel: vega.Warn});
  let svg;
  try {
    await view.runAsync();
    if (item?.words) {
      const unwrapped = value => (Array.isArray(value) ? value.join('') : value).replace(/\s+/gu, '');
      const visible = new Set();
      function collect(node) {
        if (node.mark?.marktype === 'text' && node.opacity !== 0
            && (typeof node.text === 'string' || Array.isArray(node.text))) {
          visible.add(unwrapped(node.text));
        }
        for (const child of node.items ?? []) collect(child);
      }
      collect(view.scenegraph().root);
      const expected = new Set([compact.title,
        ...tableRows(compact).flatMap(row => [row.category, row.series]).filter(Boolean)]);
      for (const text of expected) assert(visible.has(unwrapped(text)), `Visible text missing for ${id}: ${text}`);
    }
    svg = await view.toSVG();
  } finally {
    view.finalize();
  }
  assert(svg.includes('<svg') && (item?.words || svg.includes(compact.title)));
  const svgCanvas = svg.match(/width="([\d.]+)" height="([\d.]+)"/);
  assert(svgCanvas, 'Vega rendered without canvas dimensions');
  const mode = Number(svgCanvas[1]) >= Number(svgCanvas[2]) ? 'width' : 'height';
  const font = isChinese(item) ? {fontFiles:[fontFile], defaultFontFamily:fontName} : undefined;
  if (isChinese(item)) assert(svg.includes(fontName), 'Missing Chinese face in SVG');
  const png = new Resvg(svg, {fitTo: {mode, value: config.target_side}, ...(font ? {font} : {})}).render().asPng();
  assert(png.subarray(0, 8).equals(Buffer.from([137, 80, 78, 71, 13, 10, 26, 10])));
  return {svg, png};
}

async function render(kind, index, compact, full, compiled, preview, item) {
  const id = `${kind}-${String(index).padStart(6, '0')}`;
  const relative = `samples/${id}`;
  const directory = path.join(output, relative);
  const {svg, png} = await renderImage(compiled, compact, item, id);
  const compactImage = await renderImage(preview, compact, item, id + ' preview');
  fs.mkdirSync(directory, {recursive: true});
  const fullName = kind === 'radar' ? 'full.vega.json' : 'full.vl.json';
  write(path.join(directory, fullName), full);
  write(path.join(directory, 'compact.vl.json'), compact);
  writeTables(directory, compact);
  fs.writeFileSync(path.join(directory, 'chart.svg'), svg);
  fs.writeFileSync(path.join(directory, 'chart.png'), png);
  fs.writeFileSync(path.join(directory, 'compact.svg'), compactImage.svg);
  fs.writeFileSync(path.join(directory, 'compact.png'), compactImage.png);
  const entry = {id, kind, status: 'accepted', sample: relative, image: `${relative}/chart.png`,
    full: `${relative}/${fullName}`, compact: `${relative}/compact.vl.json`,
    compact_image: `${relative}/compact.png`,
    observations: tableRows(compact).length, svg_sha256: createHash('sha256').update(svg).digest('hex'),
    png_sha256: createHash('sha256').update(png).digest('hex')};
  if (item) entry.sampling = {...item.sample, ...item.choices};
  manifest.push(entry);
  training.push({id, image: entry.image, messages: [
    {role: 'user', content: '将图表转换为精简 Vega-Lite JSON。'},
    {role: 'assistant', content: JSON.stringify(compact)},
  ]});
}

function fitCombinationXAxis(spec, compact) {
  const categories = [...new Set(tableRows(compact).map(row => row.category))];
  const fontSize = spec.config?.axis?.labelFontSize ?? 10;
  const measure = text => Array.from(text).reduce((width, char) =>
    width + (/\p{Script=Han}/u.test(char) ? fontSize : .8 * fontSize), 0);
  const labels = categories.map(category => String(category).split(/\s+/u));
  const gap = 12;
  const longestWord = Math.max(...labels.flat().map(measure));
  spec.width = Math.max(spec.width, Math.ceil(categories.length * (longestWord + gap)));
  const available = spec.width / categories.length - gap;
  const display = Object.fromEntries(labels.map((words, index) => {
    const lines = [''];
    for (const word of words) {
      const last = lines.at(-1);
      const joined = last ? last + ' ' + word : word;
      if (last && measure(joined) > available) lines.push(word);
      else lines[lines.length - 1] = joined;
    }
    return [categories[index], lines.length > 1 ? lines : lines[0]];
  }));
  spec.encoding.x.axis = {...spec.encoding.x.axis,
    labelAngle: 0, labelAlign: 'center', labelBaseline: 'top', labelPadding: 5,
    labelExpr: '(' + JSON.stringify(display) + ')[toString(datum.value)]',
    labelLineHeight: Math.ceil(fontSize * 1.25),
    labelLimit: 0, labelOverlap: false, labelBound: false, minExtent: 0, titlePadding: 5};
}

function compileCombination(spec) {
  const warnings = [];
  const logger = vega.logger(vega.Warn, (_, level, ...messages) => warnings.push([level, ...messages]));
  const compiled = vl.compile(spec, {logger}).spec;
  assert.deepEqual(warnings, [], 'Vega-Lite reported a compilation diagnostic');
  return compiled;
}

async function renderCombination(index, item) {
  const compact = combinationSpec(index, item);
  const style = appearance(item);
  const full = {$schema: schema, ...plain(renderSpec(compact)), width: 510, height: 290, background: '#ffffff'};
  const preview = plain(full);
  if (isChinese(item)) {
    preview.config = {...preview.config, font: fontName, title: {fontWeight: 400}};
  }
  fitCombinationXAxis(preview, compact);
  if (item) {
    full.width = Math.round(full.height * (item.sample.aspect_ratio ?? 1.76));
    full.background = style.background;
    full.config = {...full.config,
      ...(isChinese(item) ? {font:fontName} : {}),
      title:{color:style.text, fontWeight:400},
      axis:{labelColor:style.text,titleColor:style.text,gridColor:style.grid},
      legend:{labelColor:style.text,titleColor:style.text},
      range:{category:style.colors}};
    if (item.words) fitCombinationXAxis(full, compact);
    if (item.sample.value_labels) {
      const annotation = {mark:{type:'text', dy:-5, baseline:'bottom', color:style.text, fontSize:10},
        encoding:{text:{field:'value',type:'nominal'}}};
      if (full.layer[0].layer) full.layer[0].layer.push(annotation);
      else full.layer.push(annotation);
    }
  }
  assert.deepEqual(tableRows(full), tableRows(compact));
  assert.deepEqual(tableRows(preview), tableRows(compact));
  await render('combination', index, compact, full, compileCombination(full), compileCombination(preview), item);
}
for (let start = 0; start < radar; start += batchSize) {
  const items = planBatch('radar', start, Math.min(batchSize, radar - start));
  const targets = items.map((item, offset) => radarSpec(start + offset, item));
  const views = projectRadar(targets);
  for (const [offset, compact] of targets.entries()) {
    const item = items[offset];
    const preview = prepareRadarPreview(compact, views[offset], item);
    const drawing = fullRadar(plain(preview), item);
    await render('radar', start + offset, compact, drawing, drawing, preview, item);
  }
}
for (let start = 0; start < combination; start += batchSize) {
  const items = planBatch('combination', start, Math.min(batchSize, combination - start));
  for (const [offset, item] of items.entries()) {
    await renderCombination(start + offset, item);
  }
}
for (const [name, records] of [['manifest', manifest], ['train', training]]) {
  fs.writeFileSync(path.join(output, name + '.jsonl'), records.map(record => JSON.stringify(record)).join('\n') + '\n');
}
write(path.join(output, 'validation.json'), {
  requested: radar + combination, accepted: manifest.length, rejected: 0, counts: config.counts,
});
console.log(JSON.stringify({accepted: manifest.length, counts: config.counts, vega: vega.version, vega_lite: vl.version}));
