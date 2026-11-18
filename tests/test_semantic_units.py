"""Scientific units survive projection without rescaling observations."""
import copy
import unittest

from adapter import build_pair, normalize
from compact import project_rows, semantic_rows, validate_target
from compact_display import render_spec
from generation.core import sample_config
from test_adapter import fixture
from render_support import render_specs


class SemanticUnitTests(unittest.TestCase):
    def assert_fidelity(self, full, target):
        self.assertEqual(project_rows(full), semantic_rows(target))
        self.assertEqual(normalize(target), target)
        self.assertEqual(render_spec(target)['data'], target['data'])
        validate_target(target)

    def test_pie_percent_uses_explicit_full_title_without_percent_format(self):
        cfg = sample_config('pie', 51, {'category_count': 2, 'value_mode': 'percent'})
        cfg['rows'] = [dict(category=cfg['categories'][0], value=54),
                       dict(category=cfg['categories'][1], value=46)]
        full, target, source = build_pair('pie', cfg)
        full['usermeta']['semantic']['options']['value_mode'] = 'absolute'
        before = copy.deepcopy(full)
        target = normalize(full)
        self.assertEqual(target['encoding']['theta'],
                         {'field': 'value', 'type': 'quantitative', 'title': 'Share (%)'})
        self.assertEqual(target['data']['values'][0]['value'], 54)
        self.assertNotIn('format', str(target['encoding']['theta']))
        self.assertEqual(full, before)
        self.assert_fidelity(full, target)

    def test_sum_100_never_implies_percentage(self):
        cfg = sample_config('pie', 51, {'category_count': 2, 'value_mode': 'absolute'})
        cfg['rows'] = [dict(category=category, value=value) for category, value in zip(cfg['categories'], (54, 46))]
        full, target, source = build_pair('pie', cfg)
        self.assertEqual(target['encoding']['theta']['title'], 'Value')
        self.assertNotIn('%', str(target))
        self.assert_fidelity(full, target)

    def test_box_titles_come_from_actual_full_axes(self):
        for orientation in ('horizontal', 'vertical'):
            for title in ('Latency (ms)', 'Temperature (°C)', 'Cost ($)'):
                full, _, _ = build_pair('boxplot', sample_config('boxplot', 42, {'orientation': orientation}))
                axis = 'x' if orientation == 'horizontal' else 'y'
                full['usermeta']['semantic']['options']['value_title'] = 'Stale title'
                for layer in full['layer']:
                    layer['encoding'][axis]['axis']['title'] = title
                before = copy.deepcopy(full)
                target = normalize(full)
                self.assertEqual(target['layer'][0]['encoding'][axis]['title'], title)
                self.assertEqual(full, before)
                self.assert_fidelity(full, target)

    def test_axis_unit_formats_survive_box_and_legacy_charts(self):
        for kind in ('boxplot', 'barv_1', 'line_1', 'scatter_1'):
            for fmt in ('$,.2f', '.0%', '.2p'):
                if kind == 'boxplot':
                    full, _, _ = build_pair(kind, sample_config(kind, 42, {'orientation': 'vertical'}))
                    definitions = [layer['encoding']['y'] for layer in full['layer']]
                else:
                    full, _, _ = build_pair(kind, fixture(kind))
                    definitions = [(full.get('encoding') or full['layer'][0]['encoding'])['y']]
                for definition in definitions:
                    definition.setdefault('axis', {})['format'] = fmt
                before = copy.deepcopy(full)
                target = normalize(full)
                value = target['layer'][0]['encoding']['y'] if kind == 'boxplot' else target['encoding']['y']
                self.assertEqual(value['axis'], {'format': fmt})
                self.assertEqual(full, before)
                self.assert_fidelity(full, target)

    def test_absent_units_and_precision_only_formats_are_not_invented(self):
        full, _, _ = build_pair('boxplot', sample_config('boxplot', 42, {'orientation': 'vertical'}))
        for layer in full['layer']:
            layer['encoding']['y']['axis'] = {'format': '.2f', 'grid': True}
        target = normalize(full)
        value = target['layer'][0]['encoding']['y']
        self.assertNotIn('title', value)
        self.assertNotIn('axis', value)
        self.assert_fidelity(full, target)

    def test_actual_chart_title_units_are_preserved(self):
        full, _, _ = build_pair('pie', sample_config('pie', 51))
        full['title']['text'] = 'Revenue ($)'
        self.assertEqual(normalize(full)['title'], 'Revenue ($)')

    def test_category_and_legend_titles_keep_explicit_units(self):
        full, _, _ = build_pair('boxplot', sample_config('boxplot', 42, {'orientation': 'vertical'}))
        full['encoding']['x']['axis']['title'] = 'Dose (mg)'
        target = normalize(full)
        self.assertEqual(target['encoding']['x']['title'], 'Dose (mg)')
        self.assert_fidelity(full, target)
        full, _, _ = build_pair('pie', sample_config('pie', 42, {'show_legend': True}))
        full['encoding']['color']['legend']['title'] = 'Dose (mg)'
        target = normalize(full)
        self.assertEqual(target['encoding']['color']['title'], 'Dose (mg)')
        self.assert_fidelity(full, target)

    def test_time_format_percent_tokens_do_not_invent_percentage_units(self):
        full, _, _ = build_pair('line_1', fixture('line_1'))
        enc = full.get('encoding') or full['layer'][0]['encoding']
        enc['y']['axis'] = {'format': '%p', 'formatType': 'time'}
        target = normalize(full)
        self.assertNotIn('axis', target['encoding']['y'])
        self.assert_fidelity(full, target)

    def test_real_unit_format_rendering_keeps_original_values(self):
        full, _, _ = build_pair('line_1', fixture('line_1'))
        enc = full.get('encoding') or full['layer'][0]['encoding']
        enc['y'].setdefault('axis', {})['format'] = '$,.2f'
        target = normalize(full)
        result = render_specs([target])[0]
        self.assertEqual(result['warnings'], [])
        self.assertTrue(any('$' in str(label['text']) for label in result['labels']))
        self.assert_fidelity(full, target)


if __name__ == '__main__':
    unittest.main()
