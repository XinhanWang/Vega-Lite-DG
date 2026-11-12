# Pie and Box Plot

Both types use the existing native Vega-Lite → Vega SVG → Resvg PNG pipeline.
The original nine chart samplers and compact rules are unchanged. The generator
version is `vega-lite-native/1.3`; training targets retain the upstream
`compact-v4` contract, object marks and stable specification field ordering.

## Sampling controls

Both accept `category_count` (2–8), `family`, `profile`, `style`, `show_legend`
and `legend_position` (`left`, `right`, `top`, `bottom`).

| Type | Controls |
| --- | --- |
| `pie` | `family`: balanced/dominant/long_tail/bimodal; `donut`: boolean; `value_mode`: percent/absolute; `label_mode`: legend_value/value/category_value |
| `boxplot` | `family`: normal/uniform/skewed/bimodal/heavy_tail; `orientation`: horizontal/vertical; `outlier_mode`: none/natural/injected |

Pie percentages sum to exactly 100. Absolute values are displayed in the full
chart; percentage targets never encode a hidden original total. Category names
and values remain observable through labels or legends.

Box sampling retains 64 base observations per category, with two additional
observations in injected mode. Quartiles use Type-7 linear interpolation and
Tukey 1.5×IQR fences. Decimal arithmetic avoids binary floating-point tails
without rounding legitimate interpolated values such as `31.7825`. Number
cleanup only shortens repeated binary tails within one ULP; it has no fixed
decimal-place or significant-digit limit. `lower` and
`upper` are actual observations inside the fences; outliers are sorted and
kept separately. Audit observations stay in config.json, never in training GT.

## Compact GT

- Both targets copy their semantic columns directly from Full `data.values`.
  Record order, category/value associations, number representations and outlier
  array order are preserved exactly. Extraction does not normalize precision,
  sort records or recompute statistics; generation-time numeric cleanup is unchanged.
- Pie: `category/value`, one `arc` mark. Theta contains `field`, `type` and the
  scientific title explicitly present in Full, e.g. `Share (%)`;
  color retains its category field/type mapping and any explicit scientific
  legend title. There is no `order` column,
  order encoding, row-number/window transform, explicit stack or color sorting.
  the actual scientific chart title is retained too. Donut hole, rotation,
  labels and presentation stay in Full. Explicit units are scientific semantics,
  not removable styling. Values 54/46 remain 54/46; a percent title does not add
  a percent formatter, which would incorrectly display 5400%/4600%. An absolute
  chart totaling 100 does not acquire percent semantics.
  Compact rendering may change sector/legend order; it must retain the correct
  category/value mapping and proportions, not reproduce Full's appearance.
- Box: `category/lower/q1/median/q3/upper/outliers`. Exactly four layers draw
  whiskers (`rule`), boxes (`bar`), medians (`tick`) and outliers (`point`).
  Category order follows the table. The top encoding contains only the category
  axis, retaining any explicit scientific category-axis title; each layer defines
  its own numeric mapping. The rule's primary numeric
  channel retains the scientific axis title/unit from Full's actual numeric
  encoding/axis once, rather than trusting stale sampling metadata. Numeric channels declare
  `type:"quantitative"`. Secondary `x2/y2` channels inherit that type: the official
  Vega-Lite Schema forbids `type` on secondary field definitions. The shared
  numeric scale uses Vega-Lite defaults; no scale, zero policy, filled switch or
  tick orientation is stored in the GT.
  A single `flatten:["outliers"]` uses the original field without an alias or
  redundant validity filter. Empty outlier arrays require no dummy points.
  Vega's empty-layer extent warning is retained as an expected diagnostic only
  when every outlier array is empty; other warnings still require review.
  Default mark appearance may differ from Full; no sampled font, color or size
  enters compact. Full's drawing logic and statistical calculations are unchanged.
- Full and compact use identical scientific data. The bounded
  compact-v4 validator rejects extra data fields, presentation settings, incorrect
  statistical mappings and invalid five-number/outlier relationships.
- Unit-bearing numeric `axis.format` values (D3 currency `$` and percentage
  `%`/`p` number formats) are retained exactly for Box Plot and the original chart types.
  Other axis styling and precision-only formats are still omitted. Titles retain
  units such as ms/°C/$ as written in Full; no unit is inferred from the numbers.
  Time/custom format types are not mistaken for D3 numeric unit formats.
- `compact_display.render_spec()` still derives `compact.preview.vl.json` without
  changing data. Pipeline rendering uses that preview as upstream does; the raw
  statistical compact target is independently renderable as well. Existing
  compact-only migration remains available.

## Generate and validate

```sh
python pipeline.py generate --config configs/statistical-smoke.json --output outputs/statistical-smoke
python pipeline.py validate --output outputs/statistical-smoke
```

Tests cover deterministic sampling, precision, controls, full/compact/preview
data equality, strict target validation and real Vega-Lite rendering. Workflow
checks additionally compare rendered sector proportions and category/value
associations, whiskers, quartiles, medians and every outlier against the source
statistics. Full retains its strict drawing-order checks; Compact Pie has no
visual-order constraint. JSON table order remains identical to Full.

Automated rendering and numeric correctness do not guarantee that every exact
statistic is recoverable from raster pixels. Dense outliers, small boxes and
label contrast can still require review before strict image-to-number training.

Implementation references: [Vega-Lite arc](https://vega.github.io/vega-lite/docs/arc.html),
[box plot](https://vega.github.io/vega-lite/docs/boxplot.html),
[layer](https://vega.github.io/vega-lite/docs/layer.html), and
[ChartArena](https://github.com/pspdada/ChartArena) for sample diversity.
