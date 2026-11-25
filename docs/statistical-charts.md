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
| `pie` | `family`: balanced/dominant/long_tail/bimodal; `donut`: boolean; `value_mode`: percent/absolute; `value_title`: optional scientific metric name and unit; `label_mode`: legend_value/value/category_value; `zero_count`: 0 to category_count − 1 (default 0) |
| `boxplot` | `family`: normal/uniform/skewed/bimodal/heavy_tail; `orientation`: horizontal/vertical; `outlier_mode`: none/natural/injected |

Visible percentage labels sum to 100%. The corresponding numeric proportions sum to 1. Absolute values are displayed in the full
chart; percentage targets never encode a hidden original total. Category names
and values remain observable through labels or legends.

Pie values are finite and nonnegative, with at least one positive value.
`controls.pie.zero_count` samples the requested number of zero categories.
Those rows stay in Full, Compact GT, Markdown and CSV in the original order.
Full displays each zero as a labeled legend entry or a separate data label below
the plot when the legend is hidden. Positive values alone determine the angles.

Box sampling retains 64 base observations per category, with two additional
observations in injected mode. Quartiles use Type-7 linear interpolation and
Tukey 1.5×IQR fences. Decimal arithmetic avoids binary floating-point tails
without rounding legitimate interpolated values such as `31.7825`. Number
cleanup only shortens repeated binary tails within one ULP; it has no fixed
decimal-place or significant-digit limit. `lower` and
`upper` are actual observations inside the fences; outliers are sorted and
kept separately. Precision V1 rounds the computed summary and outliers together, raising precision when necessary to preserve order and Tukey fence membership. Audit observations stay in config.json, outside training GT.

## Compact GT

- Both targets copy their semantic columns directly from Full `data.values`.
  Record order, category/value associations, number representations and outlier
  point order are preserved exactly. Extraction does not normalize precision,
  sort records or recompute statistics. Precision V1 quantizes the generated scientific table before Full or Compact is built.
- Pie uses `category/value`, one `arc` mark and `theta/color` mappings.
  The top-level `title` names the chart. Set `value_title` in the generation
  config to retain a scientific metric and unit as `theta.title`. Both modes
  omit this field by default. Historic `Share (%)` and `Value` title placeholders
  remain readable in archived Compact GT and are omitted when projecting Full.
  Percentage pies store fractions such as `0.54` for `54%` and carry
  `theta.format: ".4~p"` by default, matching Chart Annotation Studio. More
  precise values use `.N~p`. Historical `.0%` and `.12~%` remain valid Compact formats. Absolute values
  retain their original numbers and omit the format, including when their title
  contains `%`. The Compact GT omits sector ordering, window transforms, and
  donut and label styling. Legacy Compact without the format remains readable.
  Vega-Lite 6.5.0 uses the format when compiling the arc's accessibility
  description. Strict Schema validation rejects `theta.format`. The preview
  moves it to the supported `tooltip.format` and keeps the same data and angles.
  Compact rendering may change sector/legend order; it must retain the correct
  category/value mapping and proportions, not reproduce Full's appearance.
- Box: the summary table contains `category/lower/q1/median/q3/upper`. A separate `category/value` table stores one row per outlier. Exactly four layers draw
  whiskers (`rule`), boxes (`bar`), medians (`tick`) and outliers (`point`).
  Category order follows the table. The top encoding contains only the category
  axis and its explicit scientific title. Only the `rule` layer's primary numeric
  channel retains the title and unit format declared on Full's numeric axis.
  The `bar`, `tick` and `point` numeric channels contain only `field` and
  `type: "quantitative"`. Vertical plots use `y/y2` and horizontal plots use
  `x/x2`. Secondary `x2/y2` channels contain only `field`.
  A title containing `(%)` alone leaves the numeric mappings and tick format unchanged.
  The preview suppresses Vega-Lite's automatic field-name title when Full has
  no numeric axis title. The GT omits presentation settings such as scale zero
  policy, filled switch and tick orientation.
  The point layer directly reads its own inline `data.values`. Empty groups contribute zero rows.
  Vega's empty-layer extent warning is retained as an expected diagnostic only
  when the outlier table is empty. Other warnings require review.
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
- `compact_display.render_spec()` derives `compact.preview.vl.json` with the
  original data. Pipeline rendering and strict Schema validation use the Vega-Lite
  projection. The raw statistical Compact target also renders through the
  pinned compiler. Existing compact-only migration remains available.

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
