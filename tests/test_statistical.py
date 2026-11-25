"""Semantic, deterministic and actual Vega-Lite regressions for summary charts."""
import copy
import json
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from adapter import build_pair, normalize
from compact import project_rows, semantic_rows, validate_target
from compact_display import render_spec
from generation.core import sample_config
from generation.controls import FAMILIES, normalize_controls
from generation.summaries import canonical_numbers, tukey_summary
from workflow.statistical_validation import audit_geometry, validate_statistics
from render_support import render_specs


class StatisticalTests(unittest.TestCase):
    def assert_render_warnings(self, spec, result):
        layers = spec.get('layer', [])
        empty = any(layer.get('mark', {}).get('type') == 'point' and layer.get('data', {}).get('values') == [] for layer in layers)
        expected = ['Infinite extent for field "value": [Infinity, -Infinity]'] if empty else []
        self.assertEqual(result['warnings'], expected)

    def test_box_compact_has_explicit_numeric_types_and_inferred_domain(self):
        for orientation in ('horizontal', 'vertical'):
            for mode in ('none', 'natural', 'injected'):
                cfg = sample_config('boxplot', 42, {'orientation': orientation, 'outlier_mode': mode})
                full, target, source = build_pair('boxplot', cfg)
                axis = 'x' if orientation == 'horizontal' else 'y'
                self.assertNotIn(axis, target['encoding'])
                self.assertEqual([layer['mark']['type'] for layer in target['layer']], ['rule', 'bar', 'tick', 'point'])
                self.assertTrue(all(set(layer['mark']) == {'type'} for layer in target['layer']))
                self.assertEqual(target['layer'][0]['encoding'][axis]['title'], cfg['value_title'])
                self.assertNotIn('transform', target['layer'][3])
                self.assertEqual(target['layer'][3]['encoding'][axis]['field'], 'value')
                for layer in target['layer']:
                    for channel, encoding in layer.get('encoding', {}).items():
                        self.assertIn(channel, (axis, axis + '2'))
                        if channel == axis:
                            self.assertEqual(encoding['type'], 'quantitative')
                        else:
                            self.assertEqual(set(encoding), {'field'})
                validate_target(target)

    def test_no_outlier_boxes_render_with_automatic_axis_extent(self):
        specs = []
        for orientation in ('horizontal', 'vertical'):
            cfg = sample_config('boxplot', 42, {'orientation': orientation, 'outlier_mode': 'none'})
            full, target, source = build_pair('boxplot', cfg)
            for index, row in enumerate(target['data']['values']):
                row['row_id'] = str(index)
            specs.append(target)
        for axis, spec, result in zip(('x', 'y'), specs, render_specs(specs)):
            self.assert_render_warnings(spec, result)
            domain = result['scales'][axis]['domain']
            rows = spec['data']['values']
            self.assertLessEqual(min(domain), min(row['lower'] for row in rows))
            self.assertGreaterEqual(max(domain), max(row['upper'] for row in rows))
            self.assertEqual(sum(mark['name'].startswith('layer_1_') for mark in result['marks']), len(rows))
            self.assertFalse(any(mark['marktype'] == 'symbol' for mark in result['marks']))

    def test_pipeline_preserves_compact_v4_preview_separation(self):
        import tempfile
        from pipeline import produce, write_render_jobs
        from workflow.io import read
        for kind in ('pie', 'boxplot'):
            with tempfile.TemporaryDirectory() as directory:
                root = Path(directory)
                sample = root / 'samples' / kind
                row = produce(dict(id=kind, kind=kind, index=0, seed=81,
                                   output=str(sample), controls={'category_count': 4}))
                self.assertEqual(row['status'], 'generated', row)
                full = read(sample / 'full.vl.json')
                target = read(sample / 'compact.vl.json')
                preview = read(sample / 'compact.preview.vl.json')
                self.assertEqual(preview, render_spec(target))
                self.assertEqual(preview['data'], target['data'])
                self.assertEqual(semantic_rows(target), project_rows(full))
                before = (sample / 'compact.vl.json').read_bytes()
                jobs = write_render_jobs(root, [row])
                self.assertTrue(jobs[0]['compact'].endswith('compact.preview.vl.json'))
                self.assertEqual((sample / 'compact.vl.json').read_bytes(), before)

    def test_compact_v4_preview_and_object_mark_contract(self):
        from workflow.io import serialize
        for kind in ('pie', 'boxplot'):
            full, target, source = build_pair(kind, sample_config(kind, 47))
            original = copy.deepcopy(target)
            validate_target(target)
            preview = render_spec(target)
            self.assertEqual(target, original)
            self.assertEqual(preview['data'], target['data'])
            self.assertEqual(semantic_rows(preview), project_rows(full))
            self.assertEqual(serialize(normalize(target)), serialize(target))
            views = target.get('layer', [target])
            self.assertTrue(all(isinstance(view['mark'], dict) for view in views))
            priority = ['title', 'data', 'encoding', 'layer'] if kind == 'boxplot' else ['title', 'data', 'mark', 'encoding']
            self.assertEqual(list(target)[:len(priority)], priority)

    def test_compact_v4_rejects_visual_settings_and_wrong_mappings(self):
        for kind in ('pie', 'boxplot'):
            full, target, source = build_pair(kind, sample_config(kind, 81))
            for key, value in (('width', 500), ('config', {'font': 'Arial'}), ('background', 'white')):
                bad = copy.deepcopy(target)
                bad[key] = value
                with self.subTest(kind=kind, field=key), self.assertRaises(ValueError):
                    validate_target(bad)
            bad = copy.deepcopy(target)
            if kind == 'pie':
                bad['encoding']['theta']['field'] = 'category'
            else:
                bad['layer'][2]['encoding']['x' if 'x' in bad['layer'][2]['encoding'] else 'y']['field'] = 'q1'
            with self.assertRaises(ValueError):
                validate_target(bad)
            bad = copy.deepcopy(target)
            bad['data']['values'][0]['observations'] = [1, 2, 3]
            with self.assertRaises(ValueError):
                validate_target(bad)

    def test_tukey_actual_observed_extrema_and_linear_quartiles(self):
        result = tukey_summary([1, 2, 3, 4, 5, 6, 7, 100])
        self.assertEqual(result, dict(lower=1, q1=2.75, median=4.5, q3=6.25, upper=7, outliers=[100]))
        self.assertEqual(tukey_summary([3] * 8)['outliers'], [])
        for invalid in ([], [1, 2, 3], [1, 2, 3, float('nan')]):
            with self.assertRaises(ValueError):
                tukey_summary(invalid)

    def test_all_families_are_deterministic_and_gt_has_only_semantic_rows(self):
        for kind in ('pie', 'boxplot'):
            for family in FAMILIES[kind]:
                with self.subTest(kind=kind, family=family):
                    cfg = sample_config(kind, 74, {'family': family, 'category_count': 8})
                    self.assertEqual(cfg, sample_config(kind, 74, {'family': family, 'category_count': 8}))
                    full, target, source = build_pair(kind, cfg)
                    self.assertEqual(normalize(full), target)
                    self.assertEqual(normalize(target), target)
                    self.assertEqual(project_rows(full), semantic_rows(target))
                    self.assertEqual(validate_statistics(kind, cfg, source['rows'], target['layer'][3]['data']['values'] if kind == 'boxplot' else None), [])
                    expected = {'category', 'value'} if kind == 'pie' else {'category', 'lower', 'q1', 'median', 'q3', 'upper'}
                    self.assertTrue(all(set(row) == expected for row in target['data']['values']))
                    self.assertNotIn('observations', json.dumps(target))
                    self.assertNotIn('row_id', json.dumps(target))

    def test_percentage_totals_and_unmodified_table_order_for_all_counts(self):
        for count in range(2, 9):
            for family in FAMILIES['pie']:
                cfg = sample_config('pie', 81, {'category_count': count, 'family': family, 'value_mode': 'percent'})
                full, target, source = build_pair('pie', cfg)
                self.assertEqual(sum(row['value'] for row in cfg['rows']), 100)
                self.assertEqual(target['data']['values'], [dict(row, value=row['value'] / 100) for row in cfg['rows']])
                self.assertEqual(target['encoding'], {'theta': {'field': 'value', 'type': 'quantitative', 'format': full['usermeta']['semantic']['options']['percent_format']},
                                                      'color': {'field': 'category', 'type': 'nominal'}})
                self.assertNotIn('transform', target)
                bad = copy.deepcopy(source['rows'])
                bad[0]['value'] += 1
                self.assertTrue(validate_statistics('pie', cfg, bad))

    def test_orientation_and_outlier_controls(self):
        for orientation in ('horizontal', 'vertical'):
            for mode in ('none', 'natural', 'injected'):
                for family in FAMILIES['boxplot']:
                    cfg = sample_config('boxplot', 42, {'orientation': orientation, 'outlier_mode': mode, 'family': family})
                    full, target, source = build_pair('boxplot', cfg)
                    self.assertEqual(validate_statistics('boxplot', cfg, source['rows'], target['layer'][3]['data']['values']), [])
                    self.assertEqual(len(target['layer']), 4)
                    category_axis = 'y' if orientation == 'horizontal' else 'x'
                    self.assertEqual(target['encoding'][category_axis]['field'], 'category')
                    self.assertIsNone(target['encoding'][category_axis]['sort'])
                    if mode == 'none':
                        self.assertFalse(any(row['outliers'] for row in cfg['rows']))
                        self.assertEqual(target['layer'][-1]['mark'], {'type': 'point'})
                    if mode == 'injected':
                        self.assertTrue(all(row['outliers'] for row in cfg['rows']))

    def test_pie_donut_and_absolute_values_remain_visible(self):
        for donut in (False, True):
            cfg = sample_config('pie', 18, {'donut': donut, 'value_mode': 'absolute', 'label_mode': 'legend_value'})
            full, target, source = build_pair('pie', cfg)
            self.assertEqual(full['layer'][0]['mark']['innerRadius'] > 0, donut)
            self.assertEqual(target['mark'], {'type': 'arc'})
            self.assertNotIn('layer', target)
            labels = full['encoding']['color']['legend']['labelExpr']
            for row in cfg['rows']:
                self.assertIn(f'{row["value"]:g}', labels)
        cfg = sample_config('pie', 18, {'show_legend': False, 'value_mode': 'absolute'})
        self.assertEqual(cfg['label_mode'], 'category_value')

    def test_pie_resolves_label_sampling_by_mode_and_legend(self):
        for donut in (False, True):
            for legend in (False, True):
                for mode in ("absolute", "percent"):
                    with self.subTest(donut=donut, legend=legend, mode=mode):
                        cfg = sample_config("pie", 81, {
                            "value_mode": mode, "donut": donut, "show_legend": legend, "zero_count": 1,
                        }, sampling={"value_labels": False})
                        self.assertEqual(cfg["show_legend"], legend)
                        if mode == "absolute":
                            self.assertIn(cfg["label_mode"], {"legend_value", "value", "category_value"})
                            if not legend:
                                self.assertEqual(cfg["label_mode"], "category_value")
                        else:
                            self.assertEqual(cfg["label_mode"], "none" if legend else "category")
                        full, target, source = build_pair("pie", cfg, precision_v1=True)
                        self.assertEqual(full["layer"][0]["mark"]["innerRadius"] > 0, donut)
                        self.assertEqual(project_rows(full), source["rows"])
                        self.assertEqual(target["data"]["values"], source["rows"])
                        self.assertEqual(target["usermeta"]["table_export"]["tables"], [{"id": "data", "path": "/data/values"}])
                        self.assertEqual(target["encoding"]["theta"].get("format"), ".4~p" if mode == "percent" else None)
                        zero_layer = any(layer["name"] == "zero_labels" for layer in full["layer"])
                        self.assertEqual(zero_layer, not legend)

        cfg = sample_config("pie", 81, {"value_mode": "absolute", "label_mode": "none"})
        self.assertEqual(cfg["label_mode"], "legend_value")
        cfg["label_mode"] = "none"  # Historical saved configuration.
        full, _, _ = build_pair("pie", cfg)
        self.assertEqual(full["usermeta"]["semantic"]["options"]["label_mode"], "legend_value")

    def test_percent_precision_is_declared_even_with_numeric_labels_disabled(self):
        for values, fractional, fmt in (
            ((12.34, 87.66), (.1234, .8766), ".4~p"),
            ((12.3456789, 87.6543211), (.1235, .8765), ".4~p"),
        ):
            with self.subTest(format=fmt):
                cfg = sample_config("pie", 127, {
                    "category_count": 2, "value_mode": "percent", "label_mode": "none",
                })
                cfg["rows"] = [dict(category=name, value=value) for name, value in zip(cfg["categories"], values)]
                full, target, _ = build_pair("pie", cfg, precision_v1=True)
                self.assertEqual([row["value"] for row in target["data"]["values"]], list(fractional))
                self.assertEqual(project_rows(full), target["data"]["values"])
                self.assertEqual(target["encoding"]["theta"]["format"], fmt)
                self.assertEqual(render_spec(target)["encoding"]["tooltip"]["format"], fmt)
                self.assertEqual(len(full["layer"]), 1)

    def test_rendered_pie_labels_match_precision_and_show_zero_categories(self):
        configs = [
            ("absolute", True, "legend_value", (1234567.125, 1234567.126, 0),
             ("A: 1234567.13", "B: 1234567.13", "C: 0")),
            ("absolute", False, "category_value", (1234567.125, 1234567.126, 0),
             ("A: 1234567.13", "B: 1234567.13", "C: 0")),
            ("absolute", True, "value", (1234567.125, 1234567.126, 0),
             ("1234567.13", "1234567.13", "C: 0")),
            ("percent", False, "category", (12.3456789, 87.6543211, 0), ("A", "B", "C: 0%")),
            ("percent", True, "legend_value", (12.3456789, 87.6543211, 0),
             ("A: 12.35%", "B: 87.65%", "C: 0%")),
        ]
        specs = []
        for mode, legend, labels, values, expected in configs:
            cfg = sample_config("pie", 81, {
                "category_count": 3, "value_mode": mode, "donut": not legend,
                "show_legend": legend, "label_mode": labels,
            })
            cfg.update(categories=["A", "B", "C"],
                       rows=[dict(category=name, value=value) for name, value in zip("ABC", values)])
            full, target, _ = build_pair("pie", cfg, precision_v1=True)
            if mode == "absolute":
                self.assertEqual([row["value"] for row in target["data"]["values"]], [1234567.13, 1234567.13, 0])
            if labels in {"category", "category_value"}:
                self.assertIsNone(full["config"]["view"]["stroke"])
            specs.append(full)
        from xml.etree import ElementTree
        for spec, result, (_, _, _, _, expected) in zip(specs, render_specs(specs), configs):
            self.assert_render_warnings(spec, result)
            text = ["".join(node.itertext()) for node in ElementTree.fromstring(result["svg"]).iter()
                    if node.tag.endswith("}text")]
            for label in expected:
                self.assertIn(label, text)

    def test_compact_has_no_sampled_visual_settings_or_duplicate_order_arrays(self):
        forbidden = {'width', 'height', 'font', 'fontSize', 'fontWeight', 'background', 'grid', 'strokeWidth',
                     'size', 'thickness', 'radius', 'innerRadius', 'outerRadius', 'name', 'labelExpr', 'calculate',
                     'range', 'scheme', 'config', 'transform', 'filled', 'orient', 'scale'}
        def check(node):
            if isinstance(node, dict):
                self.assertFalse(forbidden & node.keys())
                for key, value in node.items():
                    if key != 'data':
                        check(value)
                    if key == 'sort':
                        self.assertIsNone(value)
            elif isinstance(node, list):
                for child in node:
                    check(child)
        for kind in ('pie', 'boxplot'):
            cfg = sample_config(kind, 47)
            original = copy.deepcopy(cfg)
            full, target, source = build_pair(kind, cfg)
            self.assertEqual(cfg, original)
            check(target)
            if kind == 'boxplot':
                self.assertNotIn('color', target['encoding'])
                self.assertEqual([layer['mark'] if isinstance(layer['mark'], str) else layer['mark']['type'] for layer in target['layer']],
                                 ['rule', 'bar', 'tick', 'point'])

    def test_numbers_are_canonical_and_decimal_fence_boundaries_stay_inside(self):
        self.assertEqual(canonical_numbers([.30000000000000004, 32.099999999999994, 1e-14, 2.0]), [.3, 32.1, 1e-14, 2])
        summary = tukey_summary([0, .3, .3, .3, .5, .5, .5, .8])
        self.assertEqual(summary['outliers'], [])
        self.assertEqual(summary['lower'], 0)
        self.assertEqual(summary['upper'], .8)
        for kind in ('pie', 'boxplot'):
            cfg = sample_config(kind, 42, {'category_count': 8})
            self.assertEqual(cfg['rows'], canonical_numbers(cfg['rows']))
            full, target, source = build_pair(kind, cfg)
            self.assertEqual(project_rows(full), target['data']['values'])
            self.assertEqual(validate_statistics(kind, cfg, target['data']['values'], target['layer'][3]['data']['values'] if kind == 'boxplot' else None), [])

    def test_full_projection_preserves_exact_precision_outlier_order_and_input(self):
        cfg = sample_config('boxplot', 42, {'outlier_mode': 'injected'})
        full, target, source = build_pair('boxplot', cfg)
        full['data']['values'][0].update(lower=.1, q1=.30000000000000004, median=.5, q3=.7,
                                       upper=.9)
        points = full['layer'][-1]['data']['values']
        category = full['data']['values'][0]['category']
        points[:] = [dict(category=category, value=value) for value in (1.9999999999999998, -1.0000000000000002)] + [p for p in points if p['category'] != category]
        original = copy.deepcopy(full)
        target = normalize(full)
        self.assertEqual(full, original)
        self.assertEqual(project_rows(full), semantic_rows(target))
        expected = [{key: value for key, value in row.items() if key != 'row_id'} for row in original['data']['values']]
        self.assertEqual(json.dumps(target['data']['values']), json.dumps(expected))
        self.assertEqual(target['layer'][-1]['data']['values'], points)
        target['layer'][-1]['data']['values'][0]['value'] = 100
        self.assertEqual(full, original)

    def test_pie_projection_drops_order_helpers_without_rewriting_observations(self):
        full, target, source = build_pair('pie', sample_config('pie', 81, {'category_count': 4}))
        values = [.30000000000000004, 32.099999999999994, 1e-14, 2.0]
        expected = []
        for index, (row, value) in enumerate(zip(full['data']['values'], values)):
            row.update(value=value, order=3-index)
            expected.append(dict(category=row['category'], value=value))
        original = copy.deepcopy(full)
        target = normalize(full)
        self.assertEqual(full, original)
        self.assertEqual(json.dumps(target['data']['values']), json.dumps(expected))
        self.assertEqual(project_rows(full), target['data']['values'])
        self.assertNotIn('order', target['encoding'])
        self.assertNotIn('transform', target)

    def test_real_shuffled_table_preserves_full_order_and_compact_data_mappings(self):
        specs = []
        cases = []
        for kind, controls in (('pie', {'value_mode': 'percent'}),
                               ('boxplot', {'orientation': 'horizontal', 'outlier_mode': 'none'}),
                               ('boxplot', {'orientation': 'vertical', 'outlier_mode': 'injected'})):
            cfg = sample_config(kind, 81, {'category_count': 4, **controls})
            categories = ['Zebra', 'Alpha', 'Mike', 'Bravo']
            cfg['categories'] = categories
            for index, row in enumerate(cfg['rows']):
                row['category'] = categories[index]
            full, compact, source = build_pair(kind, cfg)
            for spec in (full, compact):
                for index, row in enumerate(spec['data']['values']):
                    row['row_id'] = str(index)
                specs.append(spec)
                cases.append((kind, cfg))
        for (kind, cfg), spec, result in zip(cases, specs, render_specs(specs)):
            self.assert_render_warnings(spec, result)
            if kind == 'pie':
                arcs = [mark for mark in result['marks'] if mark['marktype'] == 'arc']
                self.assertCountEqual([mark['datum']['category'] for mark in arcs], cfg['categories'])
                values = {row['category']: row['value'] for row in spec['data']['values']}
                for mark in arcs:
                    datum = mark['datum']
                    self.assertAlmostEqual(datum['value_end'] - datum['value_start'], values[datum['category']])
                if 'semantic' in spec.get('usermeta', {}):
                    self.assertEqual([mark['datum']['category'] for mark in arcs], cfg['categories'])
                    self.assertEqual(result['scales']['color']['domain'], cfg['categories'])
                else:
                    self.assertCountEqual(result['scales']['color']['domain'], cfg['categories'])
            else:
                axis = 'y' if cfg['orientation'] == 'horizontal' else 'x'
                self.assertEqual(result['scales'][axis]['domain'], cfg['categories'])
                self.assertEqual(len([mark for mark in result['marks'] if mark['name'].startswith(('boxes_', 'layer_1_'))]), 4)

    def test_controls_reject_inapplicable_or_invalid_values(self):
        for kind, controls in (('pie', {'category_count': 9}), ('pie', {'donut': 1}),
                               ('pie', {'orientation': 'vertical'}), ('boxplot', {'point_count': 10}),
                               ('boxplot', {'orientation': 'diagonal'}), ('pie', {'series_count': 2})):
            with self.subTest(kind=kind, controls=controls), self.assertRaises(ValueError):
                normalize_controls(kind, controls)

    def test_compact_geometry_checks_semantics_without_enforcing_pie_order(self):
        cfg = sample_config('pie', 31, {'category_count': 3, 'value_mode': 'percent'})
        full, target, source = build_pair('pie', cfg)
        geometry = {'marks': [{'mark_id': 'arcs', 'name': 'marks'}], 'elements': [],
                    'texts': [{'role': 'legend-label', 'text': row['category']} for row in cfg['rows']]}
        angle = 0
        for row in target['data']['values']:
            end = angle + row['value'] * 2 * 3.141592653589793
            geometry['elements'].append({'mark_id': 'arcs', 'mark_type': 'arc', 'datum': copy.deepcopy(row),
                                         'arc': {'startAngle': angle, 'endAngle': end, 'innerRadius': 0}})
            angle = end
        self.assertEqual(audit_geometry('pie', cfg, target, geometry), [])
        reordered = copy.deepcopy(geometry)
        reordered['texts'].reverse()
        reordered['elements'].reverse()
        self.assertEqual(audit_geometry('pie', cfg, target, reordered), [])
        for corruption in ('values', 'angles', 'legend'):
            damaged = copy.deepcopy(geometry)
            if corruption == 'values':
                damaged['elements'][0]['datum']['value'] += 1
            elif corruption == 'angles':
                damaged['elements'][0]['arc']['endAngle'] += .1
            else:
                damaged['texts'][0]['text'] = 'Unknown category'
            self.assertTrue(audit_geometry('pie', cfg, target, damaged))

    def test_real_compilation_and_independent_compact_rendering(self):
        specs = []
        for kind, controls in (('pie', {'donut': True, 'label_mode': 'value'}),
                               ('pie', {'donut': False, 'show_legend': False}),
                               ('boxplot', {'orientation': 'horizontal', 'outlier_mode': 'none'}),
                               ('boxplot', {'orientation': 'vertical', 'outlier_mode': 'injected'})):
            full, target, source = build_pair(kind, sample_config(kind, 14, controls))
            specs.extend((full, target, render_spec(target)))
        for spec, result in zip(specs, render_specs(specs)):
            self.assert_render_warnings(spec, result)
            self.assertIn('<svg', result['svg'])


if __name__ == '__main__':
    unittest.main()
