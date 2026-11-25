import assert from 'node:assert/strict';

const percentFormat = '.4~p';
const months = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'];
const metric = (axis, names, range, digits, percent = false) => ({axis, names, range, digits, percent});

// Units, ranges and series names are paired by domain and axis.
const themes = [
  {
    title: ['Parcel deliveries', '包裹配送'], period: 'month',
    bar: metric(['Parcels', '包裹数'], [['Urban', '城区'], ['Suburban', '近郊'], ['Regional', '远郊']], [320, 1450], 0),
    shared: [['Service target', '服务目标'], ['Staffing plan', '排班计划'], ['Prior year', '上年同期']],
    right: metric(['On-time delivery (%)', '准时送达率 (%)'], [['Urban on-time', '城区准时率'], ['Suburban on-time', '近郊准时率'], ['Regional on-time', '远郊准时率']], [73, 99.5], 1, true),
  },
  {
    title: ['District electricity demand', '区域用电需求'], period: 'quarter',
    bar: metric(['Energy (MWh)', '电量 (MWh)'], [['East', '东区'], ['West', '西区'], ['Central', '中心区']], [16, 93], 1),
    shared: [['Baseline', '基线'], ['Demand forecast', '需求预测'], ['Planned capacity', '计划供给']],
    right: metric(['Peak load (kW)', '峰值负荷 (kW)'], [['East peak', '东区峰值'], ['West peak', '西区峰值'], ['Central peak', '中心区峰值']], [50, 215], 1),
  },
  {
    title: ['Metro ridership', '地铁客流'], period: 'month',
    bar: metric(['Trips (thousand)', '乘次 (千次)'], [['Line A', 'A线'], ['Line B', 'B线'], ['Line C', 'C线']], [180, 980], 1),
    shared: [['Schedule forecast', '运力预测'], ['Prior year', '上年同期'], ['Planning baseline', '规划基线']],
    right: metric(['Annual change (%)', '同比变化 (%)'], [['Line A change', 'A线同比'], ['Line B change', 'B线同比'], ['Line C change', 'C线同比']], [-24, 24], 2, true),
  },
  {
    title: ['Greenhouse harvest', '温室收成'], period: 'week',
    bar: metric(['Harvest (kg)', '收获量 (kg)'], [['House A', 'A棚'], ['House B', 'B棚'], ['House C', 'C棚']], [5, 36], 2),
    shared: [['Harvest target', '收获目标'], ['Model estimate', '模型估算'], ['Trial baseline', '试验基线']],
    right: metric(['Soil moisture (%)', '土壤含水率 (%)'], [['House A moisture', 'A棚含水率'], ['House B moisture', 'B棚含水率'], ['House C moisture', 'C棚含水率']], [14, 41], 1, true),
  },
  {
    title: ['River flow monitoring', '河流流量监测'], period: 'month',
    bar: metric(['Discharge (m³/s)', '流量 (m³/s)'], [['North gauge', '北站'], ['South gauge', '南站'], ['Outlet gauge', '出口站']], [9, 88], 1),
    shared: [['Seasonal norm', '季节均值'], ['Model forecast', '模型预报'], ['Upstream reference', '上游参照']],
    right: metric(['Water level (m)', '水位 (m)'], [['North level', '北站水位'], ['South level', '南站水位'], ['Outlet level', '出口水位']], [0.7, 4.9], 2),
  },
  {
    title: ['Production yield and benchmarks', '生产良率与基准'], period: 'week',
    bar: metric(['First-pass yield (%)', '首检良率 (%)'], [['Cell A', 'A产线'], ['Cell B', 'B产线'], ['Cell C', 'C产线']], [54, 99.9], 1, true),
    shared: [['Yield target', '良率目标'], ['Site benchmark', '工厂基准'], ['Prior shift', '上班次']],
    right: metric(['Rework cases', '返工件数'], [['Cell A rework', 'A线返工'], ['Cell B rework', 'B线返工'], ['Cell C rework', 'C线返工']], [6, 95], 0),
  },
  {
    title: ['Warehouse inventory balance', '仓储库存净变动'], period: 'quarter',
    bar: metric(['Net stock change (units)', '库存净变化 (件)'], [['Depot North', '北仓'], ['Depot South', '南仓'], ['Depot West', '西仓']], [-400, 400], 0),
    shared: [['Inventory forecast', '库存预测'], ['Prior year', '上年同期'], ['Planned change', '计划变动']],
    right: metric(['Turnover (cycles)', '周转次数'], [['North turnover', '北仓周转'], ['South turnover', '南仓周转'], ['West turnover', '西仓周转']], [1.2, 8.5], 2),
  },
];

const patterns = {
  rising: (t, p) => .12 + .76 * t ** p.curve,
  falling: (t, p) => .88 - .76 * t ** p.curve,
  cyclical: (t, p) => .5 + .32 * Math.sin(2 * Math.PI * p.cycles * t + p.phase),
  peak: (t, p) => .19 + .67 * Math.exp(-((t - p.change) ** 2) / .022),
  shift: (t, p) => t < p.change ? .23 + .07 * t : .74 + .08 * t,
  steady: (t, p) => p.level,
  crossing: (t, p) => p.direction > 0 ? .12 + .76 * t : .88 - .76 * t,
};
const positivePatterns = Object.keys(patterns).filter(name => name !== 'crossing');
const choose = (rand, values) => values[rand(0, values.length - 1)];

function seriesValues(rand, descriptor, count, pattern) {
  const [low, high] = descriptor.range;
  const options = {
    curve: rand(6, 19) / 10, phase: rand(0, 62) / 10, cycles: rand(1, 2),
    level: rand(34, 67) / 100, change: rand(32, 68) / 100, direction: choose(rand, [-1, 1]),
  };
  const offset = rand(-12, 12) / 100;
  const noise = pattern === 'steady' ? 2 : rand(2, 7);
  return Array.from({length: count}, (_, i) => {
    const fraction = patterns[pattern](i / (count - 1), options) + offset + rand(-noise, noise) / 100;
    return low + Math.max(0, Math.min(1, fraction)) * (high - low);
  });
}

function periodLabels(period, count, chinese, rand) {
  const startYear = rand(2018, 2023);
  return Array.from({length: count}, (_, i) => {
    if (period === 'week') return chinese ? `第${i + 1}周` : `W${String(i + 1).padStart(2, '0')}`;
    if (period === 'month') {
      const month = i % 12;
      const year = startYear + Math.floor(i / 12);
      const label = chinese ? `${month + 1}月` : months[month];
      return count <= 12 ? label : chinese ? `${year}年${label}` : `${label} ${year}`;
    }
    const year = startYear + Math.floor(i / 4);
    const quarter = i % 4 + 1;
    return chinese ? `${year}年Q${quarter}` : `Q${quarter} ${year}`;
  });
}

function axis(descriptor, language) {
  return {field: 'value', type: 'quantitative', title: descriptor.axis[language],
    ...(descriptor.percent ? {axis: {format: percentFormat}} : {})};
}

export function sampleCombination(item, rand) {
  const choices = item.choices;
  const language = Number(item?.sample.language === 'zh');
  const barCount = choices.bar_series_count;
  const lineCount = choices.line_series_count;
  const dual = choices.dual_axis;
  const errors = choices.error_bars;
  const categoryCount = choices.category_count;
  const theme = choose(rand, themes);
  const {bar} = theme;
  const line = dual ? theme.right : {...bar, names: theme.shared};
  const categories = periodLabels(theme.period, categoryCount, language, rand);
  const barPatterns = [];
  const linePatterns = [];
  function makeRows(descriptor, count, sampledPatterns, intervals) {
    const series = descriptor.names.slice(0, count).map((names, i) => {
      const pattern = descriptor.range[0] < 0 && i === 0 ? 'crossing' : choose(rand, positivePatterns);
      sampledPatterns.push(pattern);
      return {name: names[language], values: seriesValues(rand, descriptor, categoryCount, pattern)};
    });
    return categories.flatMap((category, index) => series.map(({name, values}) => {
      const value = values[index];
      const delta = (descriptor.range[1] - descriptor.range[0]) / 100;
      const bounds = intervals ? {
        lower: Math.max(descriptor.range[0], value - rand(2, 6) * delta),
        upper: Math.min(descriptor.range[1], value + rand(2, 6) * delta),
      } : {};
      return {category, value, ...bounds, series: name};
    }));
  }
  const bars = makeRows(bar, barCount, barPatterns, errors);
  const lines = makeRows(line, lineCount, linePatterns, false);
  const periods = {month: ['Month', '月份'], week: ['Week', '周次'], quarter: ['Quarter', '季度']};
  const x = {field: 'category', type: 'nominal', sort: null, title: periods[theme.period][language]};
  const y = axis(bar, language);
  const color = {field: 'series', type: 'nominal', sort: null};
  const offset = barCount > 1 ? {xOffset: {...color}} : undefined;
  const barLayer = {mark: {type: 'bar'}};
  const errorLayer = errors ? {mark: {type: 'errorbar'}, encoding: {
    y: {field: 'lower', type: 'quantitative'}, y2: {field: 'upper'},
  }} : undefined;
  const barLayers = errorLayer ? [barLayer, errorLayer] : [barLayer];
  const groupBars = dual && errors;
  if (!groupBars && offset) {
    barLayer.encoding = offset;
    if (errorLayer) Object.assign(errorLayer.encoding, offset);
  }
  // Independent Y scales are resolved per top-level layer. The bar and
  // its intervals need a single layer group to share their Y scale.
  const layer = groupBars ? [{layer: barLayers, ...(offset ? {encoding: offset} : {})}] : barLayers;
  const lineIndex = layer.length;
  layer.push({data: {values: lines}, mark: {type: 'line'},
    ...(dual ? {encoding: {y: axis(line, language)}} : {})});
  const compact = {
    title: theme.title[language], data: {values: bars}, encoding: {x, y, color}, layer,
    ...(dual ? {resolve: {scale: {y: 'independent'}}} : {}),
    usermeta: {table_export: {tables: [
      {id: 'bars', path: '/data/values'},
      {id: 'lines', path: `/layer/${lineIndex}/data/values`},
    ]}},
  };
  validateCombination(compact);
  const sampling = {bar_series_count: barCount, line_series_count: lineCount, dual_axis: dual,
    error_bars: errors, bar_patterns: barPatterns, line_patterns: linePatterns};
  return {compact, sampling, places: [bar.digits, line.digits]};
}

export function validateCombination(spec) {
  const [first] = spec.layer;
  const lineIndex = spec.layer.length - 1;
  const line = spec.layer[lineIndex];
  const grouped = Array.isArray(first.layer);
  const barLayers = grouped ? first.layer : spec.layer.slice(0, lineIndex);
  const [bar, error] = barLayers;
  const dual = spec.resolve?.scale?.y === 'independent';
  assert.deepEqual(barLayers.map(node => node.mark.type), error ? ['bar', 'errorbar'] : ['bar']);
  assert.equal(line.mark.type, 'line');
  assert.equal(grouped, dual && Boolean(error));
  if (grouped) assert.equal(lineIndex, 1);
  assert.deepEqual(spec.usermeta.table_export.tables, [
    {id: 'bars', path: '/data/values'}, {id: 'lines', path: `/layer/${lineIndex}/data/values`},
  ]);
  assert.deepEqual(Object.keys(spec.encoding).sort(), ['color', 'x', 'y']);
  assert.equal(spec.encoding.x.type, 'nominal');
  assert.equal(spec.encoding.x.sort, null);
  assert.equal(spec.encoding.y.field, 'value');
  assert.notEqual(spec.encoding.y.scale?.type, 'linear');
  assert.equal(spec.encoding.color.field, 'series');
  const series = new Set(spec.data.values.map(row => row.series));
  const offset = series.size > 1 ? {xOffset: {...spec.encoding.color}} : undefined;
  if (grouped) assert.deepEqual(first.encoding, offset);
  assert.deepEqual(bar.encoding, grouped ? undefined : offset);
  if (dual) {
    assert.deepEqual(Object.keys(line.encoding), ['y']);
    assert.equal(line.encoding.y.field, 'value');
    assert.notEqual(line.encoding.y.scale?.type, 'linear');
  } else {
    assert.equal(line.encoding, undefined);
  }
  if (error) {
    assert.deepEqual(error.encoding, {
      ...(grouped ? undefined : offset), y: {field: 'lower', type: 'quantitative'}, y2: {field: 'upper'},
    });
  }
  for (const node of [...spec.layer, ...barLayers]) {
    assert.equal(Object.hasOwn(node, 'layer'), grouped && node === first);
    assert.equal(Object.hasOwn(node, 'data'), node === line);
    assert(!Object.hasOwn(node, 'transform'));
  }
  for (const [table, interval] of [[spec, Boolean(error)], [line, false]]) {
    assert(table.data.values.length);
    for (const row of table.data.values) {
      assert.deepEqual(Object.keys(row).sort(), interval
        ? ['category', 'lower', 'series', 'upper', 'value'] : ['category', 'series', 'value']);
      assert(typeof row.category === 'string' && typeof row.series === 'string' && Number.isFinite(row.value));
      if (interval) assert(Number.isFinite(row.lower) && Number.isFinite(row.upper) && row.lower <= row.value && row.value <= row.upper);
    }
  }
  assert(!Object.hasOwn(spec, 'transform'));
}

export function combinationDrawing(compact, style, options) {
  const spec = structuredClone(compact);
  const [first] = spec.layer;
  const [barMark, error] = first.layer ?? spec.layer.slice(0, -1);
  const lines = spec.layer.at(-1);
  const dual = Boolean(spec.resolve);
  const sharedEncoding = first.layer ? first.encoding : undefined;
  barMark.encoding = {...sharedEncoding, ...barMark.encoding, y: {...spec.encoding.y, stack: null}};
  if (error && sharedEncoding) error.encoding = {...sharedEncoding, ...error.encoding};
  const bars = error ? {data: spec.data, layer: [barMark, error]} : {data: spec.data, ...barMark};
  const bar = error ? barMark : bars;
  delete spec.data;
  if (dual) delete spec.encoding.y;
  spec.layer = [bars, lines];
  spec.usermeta.table_export.tables[0].path = '/layer/0/data/values';
  spec.usermeta.table_export.tables[1].path = '/layer/1/data/values';
  const {
    font, width, height, legend, ticks, grid, gridDash, axisDomain, barWidth, categoryGap,
    groupGap, lineWidth, lineDash, point, labels, labelSize, colorAxes, rotation,
  } = options;
  spec.$schema = 'https://vega.github.io/schema/vega-lite/v6.json';
  Object.assign(spec, {width, height, background: style.background, padding: 12});
  spec.config = {
    font, view: {stroke: null},
    title: {color: style.text, fontSize: options.titleSize, anchor: options.titleAnchor, offset: 12},
    axis: {labelColor: style.text, titleColor: style.text, gridColor: style.grid, domainColor: style.text,
      tickColor: style.text, labelFontSize: labelSize, titleFontSize: labelSize + 1, labelPadding: 5,
      titlePadding: 8, domain: axisDomain, ticks, labelLimit: 0},
    legend: {labelColor: style.text, labelFontSize: labelSize, labelLimit: 0},
    range: {category: style.colors},
  };
  const names = node => [...new Set(node.data.values.map(row => row.series))];
  const barNames = names(bars);
  const isBar = `indexof(${JSON.stringify(barNames)}, isObject(datum) ? datum.value : datum) >= 0`;
  spec.encoding.color = {...spec.encoding.color, scale: {domain: [...barNames, ...names(lines)]},
    legend: {title: null, orient: legend, columns: ['top', 'bottom'].includes(legend) ? 3 : 1,
      symbolType: {expr: `${isBar} ? "square" : "stroke"`},
      symbolDash: {expr: `${isBar} ? [] : ${JSON.stringify(lineDash)}`},
      symbolStrokeWidth: {expr: `${isBar} ? 1 : ${lineWidth}`},
    }};
  spec.encoding.x.scale = {type: 'band', paddingInner: categoryGap, paddingOuter: .24};
  spec.encoding.x.axis = {grid: false, labelOverlap: false, labelAngle: rotation, labelLimit: 0};
  const y = bar.encoding.y;
  const leftAxis = {...y.axis, grid, ...(gridDash.length ? {gridDash} : {}),
    ...(dual && colorAxes ? {titleColor: style.colors[0]} : {})};
  y.axis = leftAxis;
  if (error) {
    error.name = 'combination_intervals';
    error.mark = {type: 'errorbar', ticks: {size: 10}, color: style.text, opacity: .85};
    error.encoding.y = {...y, field: 'lower'};
  }
  if (bar.encoding.xOffset) {
    bar.encoding.xOffset.scale = {paddingInner: groupGap};
    if (error) error.encoding.xOffset.scale = {paddingInner: groupGap};
  }
  if (dual) {
    lines.encoding.y.axis = {...lines.encoding.y.axis, orient: 'right', grid: false,
      ...(colorAxes ? {titleColor: style.colors[barNames.length]} : {})};
    if (lines.encoding.y.scale?.type !== 'log') {
      lines.encoding.y.scale = {...lines.encoding.y.scale, zero: false};
    }
  } else {
    spec.encoding.y.axis = leftAxis;
  }
  bar.name = 'combination_bars';
  bar.mark = {type: 'bar', opacity: options.barOpacity,
    ...(bar.encoding.xOffset ? {size: {expr: `${barWidth} * bandwidth('xOffset')`}} : {width: {band: barWidth}})};
  lines.name = 'combination_lines';
  lines.mark = {type: 'line', strokeWidth: lineWidth, strokeDash: lineDash, point};
  if (labels) {
    const label = {mark: {type: 'text', dy: {expr: 'datum.value < 0 ? 9 : -9'}, baseline: 'middle',
      color: style.text, fontSize: labelSize},
    encoding: {...(bar.encoding.xOffset ? {xOffset: bar.encoding.xOffset} : {}), y,
      text: {field: 'value', type: 'quantitative', format: y.axis.format ?? ',~f'}}};
    // Dense groups have room for a single readable label per category.
    const longestLabel = Math.max(...bars.data.values.map(row => String(row.value).length + 1));
    const categories = new Set(bars.data.values.map(row => row.category)).size;
    const labelSpace = width * (1 - categoryGap) / (categories * barNames.length);
    if (barNames.length > 1 && labelSpace < .6 * labelSize * longestLabel + 5) {
      label.encoding.opacity = {
        condition: {test: `datum.series === ${JSON.stringify(barNames.at(-1))}`, value: 1}, value: 0,
      };
    }
    if (bars.layer) {
      label.encoding.y = {...y, field: 'upper'};
      bars.layer.push(label);
    } else {
      bars.layer = [{name: bars.name, mark: bars.mark, encoding: bars.encoding}, label];
      delete bars.name;
      delete bars.mark;
      delete bars.encoding;
    }
  }
  return spec;
}
