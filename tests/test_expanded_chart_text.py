import hashlib
import unittest

from adapter import build_pair
from generation.chart_text import chinese_words, sample_chart_text
from generation.controls import KINDS
from generation.core import sample_config
from generation.sampling_policy import EXTENSIONS, plan, validate
from workflow.config import task_seed


class ExpandedChartTextTest(unittest.TestCase):
    def test_vocabulary_is_pinned_and_unique(self):
        words = chinese_words()
        self.assertEqual(221690, len(words))
        self.assertEqual(len(words), len(set(words)))
        digest = hashlib.sha256(("\n".join(words) + "\n").encode()).hexdigest()
        self.assertEqual("78129389f58d273f4cedc30c16d2544092e06ea55f4c549e088b4f20885d9995", digest)

    def test_all_chart_roles_are_reproducible_and_diverse(self):
        for kind in (*KINDS, *sorted(EXTENSIONS)):
            for language in ("en", "zh"):
                with self.subTest(kind=kind, language=language):
                    seeds = [task_seed(20261125, kind, index) for index in range(120)]
                    examples = [sample_chart_text(kind, seed, language, 12, 4) for seed in seeds]
                    self.assertEqual(examples[0], sample_chart_text(kind, seeds[0], language, 12, 4))
                    self.assertGreaterEqual(len({text["title"] for text in examples}), 112)
                    self.assertGreaterEqual(len({c for text in examples for c in text["categories"]}), 900)
                    self.assertTrue(all(len(set(text["categories"])) == 12 for text in examples))
                    self.assertTrue(all(len(set(text["series"])) == 4 for text in examples))

    def test_language_value_labels_and_weighted_choices_are_independent(self):
        policy = {"zh_probability": .5, "label_probability": {"barv_n": .25}}
        enhanced = {**policy, "text_profile": "expanded-v1"}
        validate(enhanced, KINDS)
        for seed in range(100):
            before, choices_before = plan("barv_n", seed, policy)
            after, choices_after = plan("barv_n", seed, enhanced)
            self.assertEqual(after.pop("text_profile"), "expanded-v1")
            self.assertEqual(before, after)
            self.assertEqual(choices_before, choices_after)
        with self.assertRaises(ValueError):
            validate({"text_profile": "unknown"}, KINDS)

    def test_native_text_updates_preserve_numeric_data_and_source_order(self):
        controls = {"x_mode": "categorical", "point_count": 8, "show_legend": True}
        base = sample_config("line_n", 892013, controls)
        cfg = sample_config("line_n", 892013, controls,
                            {"language": "en", "text_profile": "expanded-v1"})
        for key in ("style", "matrix", "x_values", "n_series"):
            self.assertEqual(base[key], cfg[key], key)
        _, compact, source = build_pair("line_n", cfg)
        self.assertEqual(cfg["title"], compact["title"])
        self.assertEqual({row["x"] for row in compact["data"]["values"]}, set(cfg["x_labels"]))
        self.assertEqual({row["x"] for row in source["rows"]}, set(cfg["x_labels"]))
