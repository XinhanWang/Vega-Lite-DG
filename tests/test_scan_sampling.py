import unittest

from generation.controls import KINDS
from generation.sampling_policy import EXTENSIONS, LABEL_KINDS, plan, validate
from workflow.config import task_seed


class SamplingPolicyTest(unittest.TestCase):
    def test_legacy_options_do_not_emit_new_fields(self):
        for kind in (*KINDS, *EXTENSIONS):
            self.assertEqual(({}, {}), plan(kind, 137, {}))

    def test_fixed_probabilities_are_reproducible_for_all_templates(self):
        for kind in (*KINDS, *EXTENSIONS):
            with self.subTest(kind=kind):
                policy = {"zh_probability": .5}
                if kind in LABEL_KINDS:
                    policy["label_probability"] = {kind: .25}
                validate(policy, (kind,))
                observations = [plan(kind, task_seed(20261124, kind, index), policy)[0]
                                for index in range(1000)]
                language_count = sum(row["language"] == "zh" for row in observations)
                self.assertTrue(440 <= language_count <= 560)
                if kind in LABEL_KINDS:
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
        self.assertEqual({"profile": "publication_clean", "x_mode": "temporal"}, options)

    def test_rejects_unused_or_invalid_sampling_options(self):
        for policy, kinds in [
            ({"zh_probability": 1.1}, KINDS),
            ({"label_probability": {"radar": .25}}, EXTENSIONS),
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
