"""Regression checks for production precision and quantized chart geometry."""
from decimal import Decimal
from unittest import TestCase
from unittest.mock import patch

from adapter import build_pair
from generation.core import sample_at_precision, sample_config
from precision import PrecisionError, box_projection, extension_observations, percentage_parts, quantize
from test_adapter import fixture


class PrecisionTests(TestCase):
    def test_decimal_rounding_and_numeric_types(self):
        pairs = [
            (123456789, 123456789), (14.773, 14.77), (5.6801, 5.68),
            (-0.46843, -.4684), (1.005, 1.01), (-1.005, -1.01),
            (-.000000000123456, -1.235e-10), (1.234567e20, 123500000000000000000),
            (2.0, 2), (-0.0, 0),
        ]
        for original, expected in pairs:
            with self.subTest(original=original):
                result = quantize(original)
                self.assertIs(type(result), type(expected))
                self.assertEqual(result, expected)
        self.assertEqual(quantize(12.3456, percent=True), 12.35)
        self.assertEqual(quantize(.123456, percent=True, fraction=True), .1235)
        self.assertEqual(quantize(-.00001, percent=True, fraction=True), 0)

    def test_percentage_parts_preserve_total_zeros_and_order(self):
        result = percentage_parts([0, 33.3333, 33.3333, 33.3334])
        self.assertEqual(result, [0, 33.33, 33.33, 33.34])
        self.assertEqual(sum(Decimal(str(value)) for value in result), 100)
        with self.assertRaisesRegex(PrecisionError, 'erase'):
            percentage_parts([.001, 99.999])

    def test_line_observation_ties_and_position_collisions(self):
        cfg = fixture('line_1')
        cfg.update(matrix=[[1.001, 1.002, 1.003]], x_values=[1.01, 2.02, 3.03])
        full, compact, _ = build_pair('line_1', cfg, precision_v1=True)
        self.assertEqual([row['y'] for row in compact['data']['values']], [1, 1, 1])
        self.assertEqual([row['plot_y'] for row in full['data']['values']], [1, 1, 1])
        cfg['x_values'] = [1.001, 1.002, 3.03]
        with self.assertRaisesRegex(PrecisionError, 'continuous positions'):
            build_pair('line_1', cfg, precision_v1=True)

    def test_collapsed_error_interval_and_fence_membership(self):
        with self.assertRaisesRegex(PrecisionError, 'Uncertainty'):
            extension_observations([dict(percent=False, rows=[dict(value=1.002, lower=1.001, upper=1.003)])])
        row = dict(lower=1, q1=1, median=2, q3=3, upper=4, outliers=[6.001])
        with self.assertRaisesRegex(PrecisionError, 'Box statistics'):
            box_projection(row)

    def test_radar_checks_sum_after_rounding(self):
        rows = [dict(category='A', value=1.006), dict(category='A', value=1.006)]
        with self.assertRaisesRegex(PrecisionError, 'stack exceeds'):
            extension_observations([dict(percent=False, rows=rows)], radial_max=2.013, stacked=True)

    def test_absolute_pie_rounds_scientific_notation_before_labeling(self):
        cfg = sample_config('pie', 23, {'category_count': 2, 'value_mode': 'absolute'})
        cfg['rows'] = [dict(category=name, value=value)
                       for name, value in zip(cfg['categories'], (1.234567e20, 1.234567e-12))]
        full, compact, _ = build_pair('pie', cfg, precision_v1=True)
        self.assertEqual([row['value'] for row in compact['data']['values']],
                         [123500000000000000000, 1.235e-12])
        self.assertEqual([row['value'] for row in full['data']['values']],
                         [123500000000000000000, 1.235e-12])

    def test_retry_is_bounded_and_reproducible(self):
        valid = sample_config('line_1', 47, {'x_mode': 'numeric', 'point_count': 3})
        bad = {**valid, 'x_values': [1.001, 1.002, 3]}
        outcomes = []
        for _ in range(2):
            with patch('generation.core.sample_config', side_effect=[bad, valid]):
                outcomes.append(sample_at_precision('line_1', 47, {}, None))
        self.assertEqual(outcomes[0], outcomes[1])
        self.assertEqual(outcomes[0][2], 2)
        self.assertNotEqual(outcomes[0][1], 47)
        with patch('generation.core.sample_config', return_value=bad) as sampler:
            with self.assertRaisesRegex(PrecisionError, '4 draws'):
                sample_at_precision('line_1', 47, {}, None)
        self.assertEqual(sampler.call_count, 4)
