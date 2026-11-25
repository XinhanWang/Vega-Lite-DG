import assert from 'node:assert/strict';
import {exportTables, writeTables} from './export_tables.mjs';
import {combinationDrawing, sampleCombination} from './combination.mjs';
import {pngAt200Dpi} from './png_metadata.mjs';
import {radarPreview, renderRadarSource} from './radar_render.mjs';
import {spawnSync} from 'node:child_process';
import {createHash} from 'node:crypto';
import fs from 'node:fs';
import path from 'node:path';
import {fileURLToPath} from 'node:url';
import {Resvg} from '@resvg/resvg-js';
import * as vega from 'vega';
import * as vl from 'vega-lite';

const [configFile, output] = process.argv.slice(2);
if (!configFile || !output) {
  throw new Error('Usage: node generate_chartarena_extensions.mjs CONFIG OUTPUT');
}
const read = file => JSON.parse(fs.readFileSync(file, 'utf8'));
const write = (file, value) => fs.writeFileSync(file, JSON.stringify(value, null, 2) + '\n');
const config = read(configFile);
const root = path.dirname(fileURLToPath(import.meta.url));
const fontName = 'Noto Sans CJK SC';
const fontFile = path.join(root, 'assets/fonts/NotoSansCJKsc-Regular.otf');
const batchSize = 128;

function planBatch(kind, start, count) {
  const planning = spawnSync('python3', ['-B', '-c', `
import json, sys
from generation.sampling_policy import EXTENSIONS, RADAR_THEMES, plan, validate
from generation.chart_text import sample_chart_text
from workflow.config import task_seed
cfg = json.load(sys.stdin)
policy = cfg.get('sampling', {})
validate(policy, EXTENSIONS)
overrides = cfg.get('controls', {})
if not isinstance(overrides, dict) or set(overrides) - {'all', *EXTENSIONS} or not all(isinstance(x, dict) for x in overrides.values()):
    raise ValueError('Extension controls must be objects keyed by all, radar or combination')
kind, start, count = sys.argv[1], int(sys.argv[2]), int(sys.argv[3])
output = []
for index in range(start, start + count):
    seed = task_seed(cfg['seed'], kind, index)
    explicit = {**overrides.get('all', {}), **overrides.get(kind, {})}
    sample, choices = plan(kind, seed, policy, controls=explicit, target_side=cfg['target_side'])
    theme = sample.get('theme', 0)
    item = dict(sample=sample, choices=choices)
    if kind == 'radar':
        item['radar'] = RADAR_THEMES[theme % len(RADAR_THEMES)]
        if sample.get('text_profile') == 'expanded-v1':
            item['words'] = sample_chart_text(kind, seed, sample['language'],
                                             max(12, choices['category_count']), choices['series_count'])
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
  assert(Number.isSafeInteger(value) && value >= 0, 'Expected nonnegative integer counts');
}
assert(config.target_side >= 64, 'target_side must be at least 64');
assert.deepEqual(Object.keys(config.counts).sort(), ['combination', 'radar']);

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

function radarSpec(index, item, rand) {
  const [baseTitle, pool] = isChinese(item) ? item.radar : radarThemes[index % radarThemes.length];
  const choices = item.choices;
  const dimensionCount = choices.category_count;
  const categories = Array.from({length: dimensionCount}, (_, i) =>
    item?.words?.categories[i] ?? pool[i] ?? (isChinese(item) ? `指标${i+1}` : `Measure ${i+1}`));
  const groupNames = Array.from({length: 8}, (_, i) => isChinese(item)
    ? `方案${'甲乙丙丁戊己庚辛'[i]}` : `Group ${'ABCDEFGH'[i]}`);
  const seriesCount = choices.series_count;
  const names = (item?.words?.series ?? groupNames).slice(0, seriesCount);
  assert.equal(names.length, seriesCount);
  const multiple = names.length > 1;
  const {radial_max: radialMax, variant, data_pattern: dataPattern} = choices;
  const baselines = categories.map(() => rand(30, 80));
  const fractions = categories.map((category, i) => names.map((_, s) => {
    const angle = i / categories.length * Math.PI * 2;
    const patterns = {
      random: () => rand(5, 98),
      correlated: () => Math.max(2, Math.min(98, baselines[i] + s * 4 + rand(-12, 12))),
      peaked: () => Math.max(2, Math.min(98, 8 + 85 * Math.exp(-Math.pow((i - categories.length * .25) / (categories.length * .15), 2)) + rand(-4, 4))),
      spiky: () => rand(0, 3) === 0 ? rand(65, 98) : rand(3, 30),
      smooth: () => Math.max(2, Math.min(98, 50 + 35 * Math.sin(angle + s * .6) + rand(-6, 6))),
      flat: () => 58 + s * 4 + rand(-8, 8),
    };
    return patterns[dataPattern]();
  }));
  const rows = categories.flatMap((category, i) => names.map((series, s) => {
    const divisor = variant === 'stacked_polar_bar' ? fractions[i].reduce((a, b) => a + b, 0) / (.15 + .8 * Math.max(...fractions[i]) / 100) : 100;
    return {category, value: fractions[i][s] * radialMax / divisor,
      ...(multiple ? {series} : {})};
  }));
  const radar = {
    variant, grid: choices.grid ?? 'polygon', rotation: choices.rotation ?? -90,
    closed: choices.closed ?? true,
    tickCount: choices.tick_count ?? 5, valueLabels: Boolean(item?.sample.value_labels),
    point: choices.point ?? false,
    strokeWidth: choices.stroke_width ?? 2,
    strokeDash: choices.dashed ? [6, 3] : [],
  };
  const compact = {
    title: item?.words?.title ?? baseTitle,
    data: {values: rows},
    mark: {type: 'line'},
    encoding: {
      x: {field: 'category', type: 'nominal', sort: categories},
      y: {field: 'value', type: 'quantitative', title: null, scale: {domain: [0, radialMax]}},
      ...(multiple ? {color: {field: 'series', type: 'nominal'}} : {}),
    },
    usermeta: {chartType: 'radar', table_export: {tables: [{id: 'data', path: '/data/values'}]}},
  };
  return {compact, radar};
}

function prepareRadarDrawing(compact, drawing, item) {
  const rows = drawing.data.find(source => source.name === 'observations').values;
  const keys = rows => rows.map(({category, value, series}) => JSON.stringify([category, value, series])).sort();
  assert.deepEqual(keys(rows), keys(compact.data.values));
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
          const black = ['#222222','#333333','#555555','#666666','#000000'].includes(color);
          const grey = ['#d1d5db','#cccccc','#bbbbbb','#dddddd','#999999'].includes(color);
          if (black || grey) value.value = black ? style.text : style.grid;
        }
        if (key === 'scales') {
          for (const scale of value) {
            if (scale.type === 'ordinal') scale.range = [...style.colors, '#39a2b6', '#a5a12e', '#c77b9d', '#7d6d55'];
          }
        }
        if (key === 'font' && isChinese(item) && typeof value.value === 'string') value.value = fontName;
        recolor(value);
      }
    };
    recolor(drawing.marks);
    for (const scale of drawing.scales ?? []) {
      if (scale.type === 'ordinal' && Array.isArray(scale.range)) scale.range = [...style.colors, "#39a2b6", "#a5a12e", "#c77b9d", "#7d6d55"];
    }
    const ratio = item.sample.aspect_ratio;
    const width = drawing.width + 60, height = drawing.height + 60;
    const horizontal = 30 + Math.max(0, Math.round((height * ratio - width) / 2));
    const vertical = 30 + Math.max(0, Math.round((width / ratio - height) / 2));
    drawing.padding = {top:vertical,bottom:vertical,left:horizontal,right:horizontal};
  }
  return drawing;
}

const tableRows = spec => exportTables(spec).flatMap(table => table.rows);

function auditCombinationMarks(view, compiled, compact, nodes) {
  const bars = compact.data.values;
  const lines = compact.layer.at(-1).data.values;
  const intervals = bars.filter(row => Object.hasOwn(row, 'lower'));
  const visibleAxes = compiled.axes.filter(axis => !axis.grid);
  const yScales = new Set(visibleAxes.filter(axis => ['left', 'right'].includes(axis.orient)).map(axis => axis.scale));
  assert.equal(yScales.size, compact.resolve ? 2 : 1, 'Rendered number of Y scales differs from Compact');
  const axes = Object.fromEntries(visibleAxes.map(axis => [axis.orient, axis.scale]));
  const left = view.scale(axes.left);
  const right = view.scale(axes.right ?? axes.left);
  const x = view.scale(axes.bottom);
  const offset = new Set(bars.map(row => row.series)).size > 1 ? view.scale('xOffset') : null;
  const categoryCenter = row => x(row.category) + x.bandwidth() / 2;
  const barCenter = row => offset ? x(row.category) + offset(row.series) + offset.bandwidth() / 2 : categoryCenter(row);
  const kinds = [
    [bars, node => node.mark?.name === 'combination_bars_marks', left, row => [0, row.value], barCenter],
    [lines, node => node.mark?.name === 'combination_lines_marks', right, row => [row.value], categoryCenter],
    [intervals, node => node.mark?.marktype === 'rule' && node.mark.name.startsWith('combination_intervals_'),
      left, row => [row.lower, row.upper], barCenter],
  ];
  for (const [rows, match, y, values, center] of kinds) {
    const fields = Object.keys(rows[0] ?? {});
    const keys = records => records.map(row => JSON.stringify(fields.map(field => row[field]))).sort();
    const marks = nodes.filter(match);
    assert.deepEqual(keys(marks.map(mark => mark.datum)), keys(rows), 'Rendered observations differ from Compact');
    for (const mark of marks) {
      const expected = values(mark.datum).map(y).sort((a, b) => a - b);
      const actual = expected.length === 1 ? [mark.y] : [mark.y, mark.y2].sort((a, b) => a - b);
      assert(actual.every((pixel, i) => Math.abs(pixel - expected[i]) < 1e-6),
        'Rendered Y positions differ from Compact');
      const renderedCenter = mark.x + (mark.width ?? 0) / 2;
      assert(Math.abs(renderedCenter - center(mark.datum)) < 1e-6, 'Rendered X positions differ from Compact');
    }
  }
  assert.equal(axes.right !== undefined, Boolean(compact.resolve), 'Rendered Y axes differ from Compact');
  assert.deepEqual(x.domain(), [...new Set(bars.map(row => row.category))]);
}

const training = [];
const manifest = [];
fs.mkdirSync(output);
write(path.join(output, 'config.json'), config);

async function renderImage(compiled, compact, item, id) {
  const view = new vega.View(vega.parse(compiled), {renderer: 'none', logLevel: vega.Warn});
  const isRadar = compact.usermeta?.chartType === 'radar';
  let svg;
  try {
    await view.runAsync();
    if (isRadar || compact.layer) {
      const unwrapped = value => (Array.isArray(value) ? value.join('') : value).replace(/\s+/gu, '');
      const visible = new Set();
      const observations = [];
      function collect(node) {
        if (compact.layer && node.datum?.category && node.datum?.series) observations.push(node);
        if (node.mark?.marktype === 'text' && node.opacity !== 0
            && (typeof node.text === 'string' || Array.isArray(node.text))) {
          visible.add(unwrapped(node.text));
        }
        for (const child of node.items ?? []) collect(child);
      }
      collect(view.scenegraph().root);
      if (compact.layer) auditCombinationMarks(view, compiled, compact, observations);
      const expected = new Set([compact.title,
        ...tableRows(compact).flatMap(row => [row.category, row.series]).filter(Boolean)]);
      if (isRadar) {
        const ticks = compiled.data.find(source => source.name === 'ticks').values;
        for (const tick of ticks) expected.add(tick.label);
      }
      for (const text of expected) assert(visible.has(unwrapped(text)), `Visible text missing for ${id}: ${text}`);
    }
    svg = await view.toSVG();
  } finally {
    view.finalize();
  }
  assert(svg.includes('<svg') && (item?.words || compact.layer || svg.includes(compact.title)));
  const svgCanvas = svg.match(/width="([\d.]+)" height="([\d.]+)"/);
  assert(svgCanvas, 'Vega rendered without canvas dimensions');
  const mode = Number(svgCanvas[1]) >= Number(svgCanvas[2]) ? 'width' : 'height';
  const font = isChinese(item) ? {fontFiles:[fontFile], defaultFontFamily:fontName} : undefined;
  if (isChinese(item)) assert(svg.includes(fontName), 'Missing Chinese face in SVG');
  const png = pngAt200Dpi(new Resvg(svg, {fitTo: {mode, value: config.target_side}, ...(font ? {font} : {})}).render().asPng());
  assert(png.subarray(0, 8).equals(Buffer.from([137, 80, 78, 71, 13, 10, 26, 10])));
  return {svg, png};
}

async function render(kind, index, compact, full, compiled, preview, item, sampling) {
  const id = `${kind}-${String(index).padStart(6, '0')}`;
  const relative = `samples/${id}`;
  const directory = path.join(output, relative);
  const {svg, png} = await renderImage(compiled, compact, item, id);
  const compactImage = await renderImage(preview, compact, item, id + ' preview');
  fs.mkdirSync(directory, {recursive: true});
  const fullName = kind === 'radar' ? 'full.vega.json' : 'full.vl.json';
  write(path.join(directory, fullName), full);
  write(path.join(directory, 'compact.vl.json'), compact);
  write(path.join(directory, 'compact.preview.vega.json'), preview);
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
  if (item || sampling) entry.sampling = {...item?.sample, ...item?.choices, ...sampling};
  manifest.push(entry);
  training.push({id, image: entry.image, messages: [
    {role: 'user', content: '将图表转换为精简 Vega-Lite JSON。'},
    {role: 'assistant', content: JSON.stringify(compact)},
  ]});
}

function fitCombinationXAxis(spec, compact) {
  const categories = [...new Set(tableRows(compact).map(row => row.category))];
  const {labelFontSize} = spec.config.axis;
  const measure = text => Array.from(text).reduce((width, char) =>
    width + (/\p{Script=Han}/u.test(char) ? labelFontSize : .72 * labelFontSize), 0);
  const x = spec.encoding.x;
  const angle = x.axis.labelAngle * Math.PI / 180;
  const longest = Math.max(...categories.map(measure)) * Math.cos(angle);
  spec.width = Math.max(spec.width, Math.ceil(categories.length * (longest + 9)));
  x.axis.values = categories;
}

function compileCombination(spec) {
  const warnings = [];
  const logger = vega.logger(vega.Warn, (_, level, ...messages) => warnings.push([level, ...messages]));
  const compiled = vl.compile(spec, {logger}).spec;
  assert.deepEqual(warnings, [], 'Vega-Lite reported a compilation diagnostic');
  return compiled;
}

const previewStyle = {
  font: 'sans-serif', width: 520, height: 290, legend: 'top', ticks: true,
  grid: true, gridDash: [], axisDomain: true, barWidth: .85, categoryGap: .24,
  groupGap: .1, lineWidth: 2, lineDash: [], point: false, labels: false, labelSize: 11,
  titleSize: 16, titleAnchor: 'middle', barOpacity: .9, colorAxes: false, rotation: 0,
};

function sampleCombinationStyle(index, item) {
  const rand = randomSource('combination-style', index);
  const choose = values => values[rand(0, values.length - 1)];
  const profile = item.choices.profile;
  const palette = appearances[profile];
  const extra = profile === 'dark_contrast' ? ['#fbda79', '#a2b6fa'] : ['#5a6834', '#866658'];
  const colors = [...palette.colors, ...extra];
  const shift = rand(0, colors.length - 1);
  const height = choose([245, 275, 320, 365]);
  const aspect = item.sample.aspect_ratio;
  const labelSize = choose([10, 11, 12, 13]);
  const point = item.choices.point ? {filled: choose([true, false]),
    shape: choose(['circle', 'square', 'diamond', 'triangle-up']), size: choose([26, 40, 56])} : false;
  return {
    style: {...palette, colors: [...colors.slice(shift), ...colors.slice(0, shift)]},
    profile, aspect,
    options: {
      ...previewStyle,
      width: Math.round(height * aspect), height,
      font: isChinese(item) ? fontName : choose(['DejaVu Sans', 'DejaVu Serif', 'Nimbus Sans']),
      grid: rand(1, 5) !== 1, gridDash: choose([[], [], [4, 3], [2, 3]]), ticks: rand(1, 4) !== 1,
      axisDomain: rand(1, 4) !== 1, colorAxes: rand(1, 3) === 1,
      barWidth: choose([.65, .8, .95]), categoryGap: choose([.12, .22, .33, .43]),
      groupGap: rand(5, 23) / 100, barOpacity: item.choices.opacity,
      lineWidth: item.choices.stroke_width, lineDash: item.choices.dashed ? choose([[6, 3], [2, 3]]) : [], point,
      legend: choose(['top', 'top', 'bottom', 'bottom', 'right', 'left']),
      labels: item?.sample.value_labels ?? rand(1, 4) === 1, labelSize,
      titleSize: labelSize + choose([4, 6, 7]), titleAnchor: choose(['start', 'middle']),
      rotation: item.choices.rotation,
    },
  };
}

function finalTargets(kind, start, items, build) {
  const targets = [];
  let pending = Array.from(items.keys());
  for (let attempt = 0; pending.length; attempt++) {
    const candidates = pending.map(offset => build(start + offset, items[offset],
      randomSource(attempt ? `${kind}:precision:${attempt}` : kind, start + offset)));
    const input = candidates.map(({compact, radar, places}) => {
      const table = (rows, y, position) => ({rows, places: places?.[position],
        percent: y.axis?.format?.endsWith('p') ?? false});
      const tables = [table(compact.data.values, compact.encoding.y, 0)];
      if (!radar) {
        const line = compact.layer.at(-1);
        tables.push(table(line.data.values, line.encoding?.y ?? compact.encoding.y, 1));
      }
      return {tables, ...(radar ? {radial_max: compact.encoding.y.scale.domain[1],
        stacked: radar.variant === 'stacked_polar_bar'} : {})};
    });
    const result = spawnSync('python3', ['-B', '-c', `
import json, sys
from precision import PRECISION_ATTEMPTS, PRECISION_VERSION, PrecisionError, extension_observations
results = []
for candidate in json.load(sys.stdin):
    try:
        results.append(dict(tables=extension_observations(**candidate)))
    except PrecisionError as error:
        results.append(dict(error=str(error)))
json.dump(dict(results=results, attempts=PRECISION_ATTEMPTS, version=PRECISION_VERSION), sys.stdout)
`], {cwd: root, input: JSON.stringify(input), encoding: 'utf8', maxBuffer: 16 * 1024 * 1024});
    assert.equal(result.status, 0, result.stderr || String(result.error));
    const {results, attempts, version} = JSON.parse(result.stdout);
    pending = pending.filter((offset, i) => {
      const projected = results[i];
      if (projected.error) {
        assert(attempt + 1 < attempts, `${kind}-${start + offset}: ${projected.error}`);
        return true;
      }
      const target = candidates[i];
      target.compact.data.values = projected.tables[0].rows;
      if (!target.radar) target.compact.layer.at(-1).data.values = projected.tables[1].rows;
      targets[offset] = {...target, precision: {precision_version: version, precision_attempts: attempt + 1}};
      return false;
    });
  }
  return targets;
}

async function renderCombination(index, item, {compact, sampling, precision}) {
  const {style, options, profile, aspect} = sampleCombinationStyle(index, item);
  const full = combinationDrawing(compact, style, options);
  const preview = combinationDrawing(compact, appearances.publication_clean, {
    ...previewStyle, font: isChinese(item) ? fontName : previewStyle.font,
  });
  fitCombinationXAxis(full, compact);
  fitCombinationXAxis(preview, compact);
  assert.deepEqual(tableRows(full), tableRows(compact));
  assert.deepEqual(tableRows(preview), tableRows(compact));
  await render('combination', index, compact, full, compileCombination(full), compileCombination(preview),
    item, {...sampling, ...precision, profile, aspect_ratio: aspect, value_labels: options.labels});
}

for (let start = 0; start < radar; start += batchSize) {
  const items = planBatch('radar', start, Math.min(batchSize, radar - start));
  const targets = finalTargets('radar', start, items, radarSpec);
  for (const [offset, {compact, radar, precision}] of targets.entries()) {
    const item = items[offset];
    const preview = prepareRadarDrawing(compact, radarPreview(compact), item);
    const original = prepareRadarDrawing(compact, renderRadarSource(compact, radar), item);
    const drawing = fullRadar(original, item);
    await render('radar', start + offset, compact, drawing, drawing, preview, item,
      {...precision, variant: radar.variant});
  }
}
for (let start = 0; start < combination; start += batchSize) {
  const items = planBatch('combination', start, Math.min(batchSize, combination - start));
  const targets = finalTargets('combination', start, items, (_, item, rand) => sampleCombination(item, rand));
  for (const [offset, target] of targets.entries()) {
    await renderCombination(start + offset, items[offset], target);
  }
}
for (const [name, records] of [['manifest', manifest], ['train', training]]) {
  fs.writeFileSync(path.join(output, name + '.jsonl'), records.map(record => JSON.stringify(record)).join('\n') + '\n');
}
write(path.join(output, 'validation.json'), {
  requested: radar + combination, accepted: manifest.length, rejected: 0, counts: config.counts,
});
console.log(JSON.stringify({accepted: manifest.length, counts: config.counts, vega: vega.version, vega_lite: vl.version}));
