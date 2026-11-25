import assert from 'node:assert/strict';

const value = x => ({value: x});
const field = x => ({field: x});
const color = {scale: 'color', field: '__series'};
const measure = text => Array.from(String(text)).reduce((sum, ch) =>
  sum + (/\p{Script=Han}/u.test(ch) ? 1 : .65), 0);

const NUMBER_SIZE = 9;
const NUMBER_OFFSET = -7;

function fitValueLabels(observations, ticks) {
  // Keep labels at their owning data points and give radial ticks priority.
  const bounds = (x, y, label, centered) => {
    const width = measure(label) * NUMBER_SIZE;
    const left = centered ? x - width / 2 : x;
    return {left: left - 1, right: left + width + 1, top: y - NUMBER_SIZE - 2, bottom: y + 2};
  };
  const occupied = ticks.map(({x, y, label}) => bounds(x, y, label, false));
  for (const row of observations) {
    const box = bounds(row.__px, row.__py + NUMBER_OFFSET, row.__label, true);
    if (occupied.some(other => box.left < other.right && other.left < box.right
        && box.top < other.bottom && other.top < box.bottom)) {
      row.__label = null;
    } else {
      occupied.push(box);
    }
  }
}

export function radarPreview(compact) {
  assert.equal(compact.usermeta?.chartType, 'radar');
  assert.deepEqual(compact.usermeta.table_export?.tables, [{id: 'data', path: '/data/values'}]);
  assert.equal(compact.encoding.y.title, null);
  return renderRadarSource(compact, {
    variant: 'line', grid: 'polygon', rotation: -90, tickCount: 5,
    closed: true, point: false, strokeWidth: 2, strokeDash: [],
  });
}

/** Draw the synthetic source image with its sampled presentation settings. */
export function renderRadarSource(compact, options) {
  const categories = compact.encoding.x.sort;
  const rows = compact.data.values;
  const series = [...new Set(rows.map(row => row.series ?? ''))];
  const domain = compact.encoding.y.scale.domain;
  const count = categories.length;
  const radius = count > 20 ? 240 : 205;
  const center = radius + 35;
  const rotation = options.rotation * Math.PI / 180;
  const angleFor = i => rotation + i * Math.PI * 2 / count;
  const [minimum, maximum] = domain;
  const radialPosition = number => {
    assert(number >= minimum - 1e-8 && number <= maximum + 1e-8, 'Radar data exceeds its domain');
    return radius * (number - minimum) / (maximum - minimum);
  };
  const observations = [];
  const stacked = options.variant === 'stacked_polar_bar';
  const polarBar = options.variant === 'polar_bar' || stacked;
  if (stacked) assert(series.length >= 2, 'Stacked radar requires at least two series');
  if (options.variant === 'filled') {
    assert(series.length <= 4 && options.closed !== false, 'Filled radar requires a closed outline and at most four series');
  }
  for (let i = 0; i < count; i++) {
    let cumulative = 0;
    for (let s = 0; s < series.length; s++) {
      const row = rows.find(row => row.category === categories[i] && (row.series ?? '') === series[s]);
      assert(row, 'Each series requires one row per radar dimension');
      const outerValue = stacked ? cumulative + row.value : row.value;
      const outer = radialPosition(outerValue);
      const inner = stacked ? radialPosition(cumulative) : 0;
      const angle = angleFor(i);
      const halfWidth = Math.PI / count * .78;
      const groupedWidth = halfWidth * 2 / series.length;
      const arcStart = angle + Math.PI / 2 - halfWidth + (stacked ? 0 : s * groupedWidth);
      const arcEnd = stacked ? angle + Math.PI / 2 + halfWidth : arcStart + groupedWidth * .9;
      const labelAngle = polarBar ? (arcStart + arcEnd) / 2 - Math.PI / 2 : angle;
      observations.push({...row, __series: series[s], __order: i,
        __px: center + outer * Math.cos(labelAngle), __py: center + outer * Math.sin(labelAngle),
        __inner: inner, __outer: outer, __start: arcStart, __end: arcEnd,
        __label: String(row.value)});
      cumulative += row.value;
    }
  }
  assert.equal(observations.length, rows.length);
  const spokes = categories.map((category, i) => ({
    x: center, y: center, x2: center + radius * Math.cos(angleFor(i)),
    y2: center + radius * Math.sin(angleFor(i)),
  }));
  const rings = [];
  for (let ring = 1; ring <= options.tickCount; ring++) {
    for (let i = 0; i < count; i++) {
      const r = radius * ring / options.tickCount;
      rings.push({ring, order: i, x: center + r * Math.cos(angleFor(i)), y: center + r * Math.sin(angleFor(i))});
    }
  }
  const fontSize = count > 20 ? 10 : 12;
  const labels = categories.map((category, i) => {
    const angle = angleFor(i);
    const cos = Math.cos(angle);
    const dense = count > 16;
    const degrees = angle * 180 / Math.PI;
    const left = cos < -.1;
    return {label: category, x: center + (radius + 18) * cos,
      y: center + (radius + 18) * Math.sin(angle),
      align: Math.abs(cos) < .1 ? 'center' : left ? 'right' : 'left',
      angle: dense ? degrees + (left ? 180 : 0) : 0};
  });
  const ticks = Array.from({length: options.tickCount}, (_, i) => {
    const fraction = (i + 1) / options.tickCount;
    const r = radius * fraction;
    return {x: center + r * Math.cos(rotation) + 5, y: center + r * Math.sin(rotation) - 3,
      label: String(Number((minimum + (maximum - minimum) * fraction).toPrecision(4)))};
  });
  const legendWidth = Math.max(120, ...series.map(name => measure(name) * 12 + 30));
  const legendColumns = Math.max(1, Math.min(3, Math.floor(center * 2 / legendWidth)));
  const legend = series.filter(Boolean).map((name, i) => ({__series: name, label: name,
    x: 15 + i % legendColumns * legendWidth,
    y: center * 2 + 42 + Math.floor(i / legendColumns) * 23}));
  const gridMarks = options.grid === 'circle'
    ? [{type: 'arc', from: {data: 'gridCircles'}, encode: {enter: {
      x: value(center), y: value(center), startAngle: value(0), endAngle: value(Math.PI * 2),
      innerRadius: field('radius'), outerRadius: field('radius'), stroke: value('#dddddd'), strokeWidth: value(.8)}}}]
    : [{type: 'group', from: {facet: {name: 'ring', data: 'rings', groupby: 'ring'}}, marks: [
      {type: 'line', from: {data: 'ring'}, sort: {field: 'order'}, encode: {enter: {
        x: field('x'), y: field('y'), interpolate: value('linear-closed'), stroke: value('#dddddd')}}}]}];
  const dataMarks = polarBar
    ? [{type: 'arc', from: {data: 'observations'}, encode: {enter: {
      x: value(center), y: value(center), innerRadius: field('__inner'), outerRadius: field('__outer'),
      startAngle: field('__start'), endAngle: field('__end'), fill: color, fillOpacity: value(.8),
      stroke: value('#ffffff'), strokeWidth: value(.5)}}}]
    : [{type: 'group', from: {facet: {name: 'series', data: 'observations', groupby: '__series'}}, marks: [
      {type: 'line', from: {data: 'series'}, sort: {field: '__order'}, encode: {enter: {
        x: field('__px'), y: field('__py'), interpolate: value(options.closed === false ? 'linear' : 'linear-closed'), stroke: color,
        strokeWidth: value(options.strokeWidth), strokeDash: value(options.strokeDash),
        fill: color, fillOpacity: value(options.variant === 'filled' ? .22 : 0)}}}]}];
  if (options.point && !polarBar) dataMarks.push({type: 'symbol', from: {data: 'observations'}, encode: {enter: {
    x: field('__px'), y: field('__py'), fill: color, size: value(count > 20 ? 18 : 35)}}});
  if (options.valueLabels) {
    fitValueLabels(observations, ticks);
    dataMarks.push({type: 'text', from: {data: 'valueLabels'}, encode: {enter: {
      x: field('__px'), y: field('__py'), dy: value(NUMBER_OFFSET), text: field('__label'),
      fill: color, fontSize: value(NUMBER_SIZE), align: value('center'), baseline: value('bottom')}}});
  }
  const width = Math.max(center * 2 + 25, legendColumns * legendWidth + 25);
  const height = center * 2 + 35 + Math.ceil(legend.length / legendColumns) * 23;
  const result = {
    $schema: 'https://vega.github.io/schema/vega/v6.json', width, height, padding: 35,
    title: compact.title,
    data: [{name: 'observations', values: observations}, {name: 'spokes', values: spokes},
      {name: 'rings', values: rings}, {name: 'gridCircles', values: Array.from({length: options.tickCount}, (_, i) =>
        ({radius: radius * (i + 1) / options.tickCount}))},
      {name: 'labels', values: labels}, {name: 'ticks', values: ticks}, {name: 'legend', values: legend},
      ...(options.valueLabels ? [{name: 'valueLabels', source: 'observations',
        transform: [{type: 'filter', expr: 'datum.__label !== null'}]}] : [])],
    scales: [{name: 'color', type: 'ordinal', domain: series, range: {scheme: 'tableau10'}}],
    marks: [...gridMarks, {type: 'rule', from: {data: 'spokes'}, encode: {enter: {
      x: field('x'), y: field('y'), x2: field('x2'), y2: field('y2'), stroke: value('#cccccc'), strokeWidth: value(.8)}}},
      ...dataMarks,
      {type: 'text', from: {data: 'ticks'}, encode: {enter: {
        x: field('x'), y: field('y'), text: field('label'), fontSize: value(9), fill: value('#666666')}}},
      {type: 'symbol', from: {data: 'legend'}, encode: {enter: {
        x: field('x'), y: field('y'), fill: color, size: value(55)}}},
      {type: 'text', from: {data: 'legend'}, encode: {enter: {
        x: {field: 'x', offset: 12}, y: field('y'), text: field('label'), baseline: value('middle'), fontSize: value(12)}}},
      {type: 'text', from: {data: 'labels'}, encode: {enter: {
        x: field('x'), y: field('y'), text: field('label'), align: field('align'), angle: field('angle'),
        baseline: value('middle'), fontSize: value(fontSize)}}}],
    usermeta: {radarGeometry: {center, radius}},
  };
  return result;
}
