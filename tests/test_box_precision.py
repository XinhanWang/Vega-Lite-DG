"""Regression checks for decimal Type-7 statistics without precision sampling."""
from decimal import Decimal
import json
import unittest

from adapter import build_pair
from generation.core import sample_config
from generation.summaries import canonical_numbers, tukey_summary
from workflow.statistical_validation import validate_statistics


class BoxPrecisionTests(unittest.TestCase):
    def test_cleanup_has_no_fixed_significant_digit_limit(self):
        precise = [31.7825, 1.1234567890126, 1.2345678901234567, 1e-14, 99.99999999]
        self.assertEqual(canonical_numbers(precise), precise)
        self.assertEqual(canonical_numbers([86.89500000000001, 93.85749999999999, 31.782500000000003]),
                         [86.895, 93.8575, 31.7825])

    def test_full_and_compact_keep_fine_statistical_precision(self):
        cfg = sample_config('boxplot', 47, {'category_count': 2})
        observations = [1.1234567890123, 1.1234567890127, 1.1234567890131, 1.1234567890135]
        cfg['observations'] = [observations[:] for category in cfg['categories']]
        cfg['rows'] = [dict(category=category, **tukey_summary(observations)) for category in cfg['categories']]
        full, compact, source = build_pair('boxplot', cfg)
        self.assertEqual(compact['data']['values'], cfg['rows'])
        self.assertEqual(full['data']['values'][0]['q1'], 1.1234567890126)
        self.assertEqual(compact['data']['values'][0]['q3'], 1.1234567890132)
        self.assertEqual(validate_statistics('boxplot', cfg, source['rows']), [])

    def test_legitimate_quartile_digits_survive(self):
        summary = tukey_summary([86.88, 86.9, 93.85, 93.88])
        self.assertEqual(summary['q1'], 86.895)
        self.assertEqual(summary['q3'], 93.8575)
        self.assertEqual(tukey_summary([31.76, 31.79, 32.01, 32.09])['q1'], 31.7825)
        self.assertNotIn('00000000001', json.dumps(summary))
        self.assertNotIn('99999999999', json.dumps(summary))

    def test_input_precision_and_tukey_boundaries(self):
        values = [Decimal('1.1234567890123'), Decimal('1.1234567890127'),
                  Decimal('1.1234567890131'), Decimal('1.1234567890135')]
        summary = tukey_summary(values)
        self.assertEqual(summary['q1'], 1.1234567890126)
        self.assertEqual(summary['q3'], 1.1234567890132)
        self.assertEqual(tukey_summary([0, .3, .3, .3, .5, .5, .5, .8])['outliers'], [])
        self.assertEqual(tukey_summary([1, 2, 3, 4, 5, 6, 7, 100]),
                         dict(lower=1, q1=2.75, median=4.5, q3=6.25, upper=7, outliers=[100]))

    def test_shared_generated_data_and_no_precision_resampling(self):
        for seed in range(30):
            cfg = sample_config('boxplot', seed)
            self.assertNotIn('statistic_decimals', cfg)
            self.assertNotIn('precision_resamples', cfg)
            full, compact, source = build_pair('boxplot', cfg)
            self.assertEqual(compact['data']['values'], cfg['rows'])
            self.assertEqual([{k: v for k, v in row.items() if k != 'row_id'}
                              for row in full['data']['values']], cfg['rows'])
            self.assertEqual(len(compact['layer']), 4)
            self.assertEqual(validate_statistics('boxplot', cfg, source['rows']), [])
            for row, observations in zip(cfg['rows'], cfg['observations']):
                self.assertEqual(row, dict(category=row['category'], **tukey_summary(observations)))


if __name__ == '__main__':
    unittest.main()
