import unittest

from generation.controls import KINDS
from generation.sampling_policy import EXTENSIONS, LABEL_KINDS, plan, radar_label_factor, validate
from workflow.config import task_seed


class SamplingPolicyTest(unittest.TestCase):
    def test_general_defaults_are_deterministic_and_vary_with_seed(self):
        for kind in (*KINDS, *EXTENSIONS):
            draws = [plan(kind, seed, {}) for seed in range(20)]
            self.assertEqual(draws, [plan(kind, seed, {}) for seed in range(20)])
            self.assertEqual(len({observation["aspect_ratio"] for observation, _ in draws}), 20)

    def test_ranges_and_explicit_controls(self):
        policy = {"ranges": {"all": {"aspect_ratio": [1.27, 1.42]}, "radar": {
            "category_count": [24, 36], "series_count": [2, 3], "rotation": [-180, 180],
            "radial_exponent": [0, 1], "tick_count": [4, 7], "stroke_width": [1.2, 2.3],
        }}}
        validate(policy, ("radar",))
        for seed in range(80):
            info, choices = plan("radar", seed, policy)
            self.assertTrue(1.27 <= info["aspect_ratio"] <= 1.42)
            self.assertTrue(24 <= choices["category_count"] <= 36)
            self.assertIn(choices["series_count"], (2, 3))
            self.assertTrue(-180 <= choices["rotation"] < 180)
            self.assertTrue(4 <= choices["tick_count"] <= 7)
        _, forced = plan("radar", 1, {}, controls={"category_count": 4, "series_count": 8,
                                                 "variant": "line", "radial_max": 123, "rotation": 17.2})
        self.assertEqual(forced["radial_max"], 123)
        self.assertEqual(forced["series_count"], 8)
        self.assertEqual(forced["rotation"], 17.2)
        with self.assertRaisesRegex(ValueError, "series_count"):
            plan("radar", 1, {}, controls={"category_count": 36, "series_count": 8})
        with self.assertRaisesRegex(ValueError, "category_count"):
            plan("pie", 1, {}, controls={"category_count": 2, "zero_count": 2})
        with self.assertRaisesRegex(ValueError, "four attempts"):
            plan("scatter_n", 0, {"ranges": {"scatter_n": {"point_count": [12, 12], "series_count": [5, 5]}}})
        _, scatter = plan("scatter_n", 10, {}, controls={"point_count": 12})
        self.assertEqual(scatter["series_count"], 2)
        forced = {"category_count": 4, "series_count": 2, "variant": "line", "radial_max": 20}
        small = plan("radar", 10, {}, controls=forced, target_side=380)[1]["tick_count"]
        large = plan("radar", 10, {}, controls=forced, target_side=1036)[1]["tick_count"]
        dense = plan("radar", 10, {}, controls={**forced, "category_count": 30})[1]["tick_count"]
        self.assertLess(small, large)
        self.assertLess(dense, large)

    def test_fixed_probabilities_are_reproducible_for_all_templates(self):
        for kind in (*KINDS, *EXTENSIONS):
            with self.subTest(kind=kind):
                policy = {"zh_probability": .5}
                if kind in LABEL_KINDS:
                    policy["label_probability"] = {kind: .25}
                validate(policy, (kind,))
                selections = [plan(kind, task_seed(20261124, kind, index), policy)
                              for index in range(1000)]
                observations = [info for info, _ in selections]
                language_count = sum(row["language"] == "zh" for row in observations)
                self.assertTrue(440 <= language_count <= 560)
                if kind == "radar":
                    expected = .25 * sum(radar_label_factor(p["category_count"] * p["series_count"])
                                         for _, p in selections)
                    self.assertLess(abs(sum(row["value_labels"] for row in observations) - expected), 35)
                elif kind in LABEL_KINDS:
                    self.assertTrue(200 <= sum(row["value_labels"] for row in observations) <= 300)
                else:
                    self.assertTrue(all("value_labels" not in row for row in observations))

    def test_weighted_overrides_do_not_change_language_or_labels(self):
        policy = {"zh_probability": .5, "label_probability": {"line_n": .25}}
        weighted = {"all": {"profile": [{"value": "compact_report", "weight": 1}]},
                    "line_n": {"profile": [{"value": "publication_clean", "weight": 1}],
                               "x_mode": [{"value": "temporal", "weight": 1}]}}
        before, _ = plan("line_n", 52, policy)
        after, options = plan("line_n", 52, {**policy, "weighted": weighted})
        self.assertEqual(before, after)
        self.assertEqual(options["profile"], "publication_clean")
        self.assertEqual(options["x_mode"], "temporal")

    def test_rejects_unused_or_invalid_sampling_options(self):
        for policy, kinds in [
            ({"zh_probability": 1.1}, KINDS),
            ({"ranges": {"radar": {"category_count": [3, 36]}}}, EXTENSIONS),
            ({"ranges": {"combination": {"category_count": [5.5, 8]}}}, EXTENSIONS),
            ({"label_probability": {"radar": 1.25}}, EXTENSIONS),
            ({"weighted": {"combination": {"series_count": [{"value": 3, "weight": 1}]}}}, EXTENSIONS),
            ({"weighted": {"all": {"profile": [{"value": "unknown", "weight": 1}]}}}, EXTENSIONS),
            ({"weighted": {"pie": {"donut": [{"value": True, "weight": 0}]}}}, KINDS),
        ]:
            with self.subTest(policy=policy):
                with self.assertRaises(ValueError):
                    validate(policy, kinds)


    def test_numeric_annotations_preserve_guides_and_compact_target(self):
        from adapter import build_pair
        from generation.core import sample_config
        cfg = sample_config("barh_1", 137, {"category_count": 12})
        _, expected, _ = build_pair("barh_1", cfg)
        cfg["sampling"] = {"value_labels": True}
        full, compact, _ = build_pair("barh_1", cfg)
        self.assertEqual(expected, compact)
        primary = full["layer"][0]["encoding"]
        labels = [layer for layer in full["layer"] if "value_labels" in layer.get("name", "")]
        self.assertTrue(labels)
        for layer in labels:
            for axis in ("x", "y"):
                self.assertEqual(primary[axis]["axis"], layer["encoding"][axis]["axis"])
