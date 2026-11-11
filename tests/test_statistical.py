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
                    self.assertEqual(validate_statistics(kind, cfg, source['rows']), [])
                    expected = {'category', 'value'} if kind == 'pie' else {'category', 'lower', 'q1', 'median', 'q3', 'upper', 'outliers'}
                    self.assertTrue(all(set(row) == expected for row in target['data']['values']))
                    self.assertNotIn('observations', json.dumps(target))
                    self.assertNotIn('row_id', json.dumps(target))

    def test_percentage_totals_and_explicit_order_for_all_counts(self):
        for count in range(2, 9):
            for family in FAMILIES['pie']:
                cfg = sample_config('pie', 81, {'category_count': count, 'family': family, 'value_mode': 'percent'})
                full, target, source = build_pair('pie', cfg)
                self.assertEqual(sum(row['value'] for row in cfg['rows']), 100)
                self.assertIsNone(target['encoding']['color']['sort'])
                self.assertEqual(target['encoding']['order']['field'], 'order')
                self.assertEqual(target['transform'], [{'window': [{'op': 'row_number', 'as': 'order'}]}])
                bad = copy.deepcopy(source['rows'])
                bad[0]['value'] += 1
                self.assertTrue(validate_statistics('pie', cfg, bad))

    def test_orientation_and_outlier_controls(self):
        for orientation in ('horizontal', 'vertical'):
            for mode in ('none', 'natural', 'injected'):
                for family in FAMILIES['boxplot']:
                    cfg = sample_config('boxplot', 42, {'orientation': orientation, 'outlier_mode': mode, 'family': family})
                    full, target, source = build_pair('boxplot', cfg)
                    self.assertEqual(validate_statistics('boxplot', cfg, source['rows']), [])
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
        cfg = sample_config('pie', 18, {'show_legend': False})
        self.assertEqual(cfg['label_mode'], 'category_value')

    def test_compact_has_no_sampled_visual_settings_or_duplicate_order_arrays(self):
        forbidden = {'width', 'height', 'font', 'fontSize', 'fontWeight', 'background', 'grid', 'strokeWidth',
                     'size', 'thickness', 'radius', 'innerRadius', 'outerRadius', 'name', 'labelExpr', 'calculate',
                     'range', 'scheme', 'config', 'usermeta'}
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
            self.assertEqual(target['data']['values'], cfg['rows'])

    def test_legacy_full_projection_cleans_precision_without_mutating_input(self):
        cfg = sample_config('boxplot', 42)
        full, target, source = build_pair('boxplot', cfg)
        full['data']['values'][0].update(lower=.1, q1=.30000000000000004, median=.5, q3=.7,
                                       upper=.9, outliers=[1.9999999999999998])
        original = copy.deepcopy(full)
        target = normalize(full)
        self.assertEqual(full, original)
        self.assertEqual(project_rows(full), semantic_rows(target))
        self.assertEqual(target['data']['values'][0]['q1'], .3)
        self.assertEqual(target['data']['values'][0]['outliers'], [2])

    def test_real_shuffled_table_order_controls_arc_angles_and_box_positions(self):
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
        for (kind, cfg), result in zip(cases, render_specs(specs)):
            self.assertEqual(result['warnings'], [])
            if kind == 'pie':
                arcs = [mark for mark in result['marks'] if mark['marktype'] == 'arc']
                self.assertEqual([mark['datum']['category'] for mark in arcs], cfg['categories'])
                previous = 0
                for mark, row in zip(arcs, cfg['rows']):
                    self.assertAlmostEqual(mark['datum']['value_start'], previous)
                    previous += row['value']
                    self.assertAlmostEqual(mark['datum']['value_end'], previous)
                self.assertEqual(result['scales']['color']['domain'], cfg['categories'])
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

    def test_compact_geometry_rejects_changed_values_angles_and_legend_order(self):
        cfg = sample_config('pie', 31, {'category_count': 3, 'value_mode': 'percent'})
        full, target, source = build_pair('pie', cfg)
        geometry = {'marks': [{'mark_id': 'arcs', 'name': 'marks'}], 'elements': [],
                    'texts': [{'role': 'legend-label', 'text': row['category']} for row in cfg['rows']]}
        angle = 0
        for row in cfg['rows']:
            end = angle + row['value'] * 2 * 3.141592653589793 / 100
            geometry['elements'].append({'mark_id': 'arcs', 'mark_type': 'arc', 'datum': copy.deepcopy(row),
                                         'arc': {'startAngle': angle, 'endAngle': end, 'innerRadius': 0}})
            angle = end
        self.assertEqual(audit_geometry('pie', cfg, target, geometry), [])
        for corruption in ('values', 'angles', 'legend'):
            damaged = copy.deepcopy(geometry)
            if corruption == 'values':
                damaged['elements'][0]['datum']['value'] += 1
            elif corruption == 'angles':
                damaged['elements'][0]['arc']['endAngle'] += .1
            else:
                damaged['texts'].reverse()
            self.assertTrue(audit_geometry('pie', cfg, target, damaged))

    def test_real_compilation_and_independent_compact_rendering(self):
        specs = []
        for kind, controls in (('pie', {'donut': True, 'label_mode': 'value'}),
                               ('pie', {'donut': False, 'show_legend': False}),
                               ('boxplot', {'orientation': 'horizontal', 'outlier_mode': 'none'}),
                               ('boxplot', {'orientation': 'vertical', 'outlier_mode': 'injected'})):
            full, target, source = build_pair(kind, sample_config(kind, 14, controls))
            specs.extend((full, target, render_spec(target)))
        for result in render_specs(specs):
            self.assertEqual(result['warnings'], [])
            self.assertIn('<svg', result['svg'])


if __name__ == '__main__':
    unittest.main()
