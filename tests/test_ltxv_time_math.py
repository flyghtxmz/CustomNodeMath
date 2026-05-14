import importlib.util
from pathlib import Path
import unittest


_MATH_PATH = (
    Path(__file__).resolve().parents[1]
    / "ltxv_time_math.py"
)
_SPEC = importlib.util.spec_from_file_location("ltxv_time_math_under_test", _MATH_PATH)
math_module = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(math_module)

_ROOT = Path(__file__).resolve().parents[1]
_PACKAGE_NAME = "ComfyUI_LTXV_PromptRelayAutoSync_under_test"
_PACKAGE_SPEC = importlib.util.spec_from_file_location(
    _PACKAGE_NAME,
    _ROOT / "__init__.py",
    submodule_search_locations=[str(_ROOT)],
)
package_module = importlib.util.module_from_spec(_PACKAGE_SPEC)
import sys
sys.modules[_PACKAGE_NAME] = package_module
_PACKAGE_SPEC.loader.exec_module(package_module)
nodes_module = sys.modules[f"{_PACKAGE_NAME}.nodes"]


class LTXVTimeMathTests(unittest.TestCase):
    def test_safe_frames_30s_24fps_equal_segments(self):
        total = math_module.safe_ltxv_total_frames(30, 24)
        segments, mode, warnings = math_module.distribute_segments(total, 24, "equal")
        self.assertEqual(total, 721)
        self.assertEqual(segments, [181, 180, 180, 180])
        self.assertEqual(math_module.segment_start_indices(segments), [0, 181, 361, 541])
        self.assertEqual(mode, "equal")
        self.assertEqual(warnings, [])

    def test_safe_frames_10s_24fps_equal_segments(self):
        total = math_module.safe_ltxv_total_frames(10, 24)
        segments, _, _ = math_module.distribute_segments(total, 24, "equal")
        self.assertEqual(total, 241)
        self.assertEqual(segments, [61, 60, 60, 60])
        self.assertEqual(math_module.segment_start_indices(segments), [0, 61, 121, 181])

    def test_safe_frames_20s_50fps_equal_segments(self):
        total = math_module.safe_ltxv_total_frames(20, 50)
        segments, _, _ = math_module.distribute_segments(total, 50, "equal")
        self.assertEqual(total, 1001)
        self.assertEqual(segments, [251, 250, 250, 250])
        self.assertEqual(math_module.segment_start_indices(segments), [0, 251, 501, 751])

    def test_weighted_segments_sum_and_prioritize_second_segment(self):
        segments, mode, warnings = math_module.distribute_segments(
            721,
            24,
            "weights",
            weights=[1, 2, 1, 1],
        )
        self.assertEqual(sum(segments), 721)
        self.assertGreaterEqual(min(segments), 1)
        self.assertGreater(segments[1], segments[0])
        self.assertGreater(segments[1], segments[2])
        self.assertGreater(segments[1], segments[3])
        self.assertEqual(mode, "weights")
        self.assertEqual(warnings, [])

    def test_empty_prompts_warn_and_strict_mode_errors(self):
        payload = math_module.make_prompt_relay_payload(
            total_frames=241,
            fps=24,
            global_prompt="global",
            segment_prompts=["one", "", "three", ""],
            strict_prompts=False,
        )
        self.assertIn("segment_2_prompt is empty.", payload["debug_report"])
        self.assertIn("segment_4_prompt is empty.", payload["debug_report"])

        with self.assertRaisesRegex(ValueError, "segment_2_prompt"):
            math_module.make_prompt_relay_payload(
                total_frames=241,
                fps=24,
                global_prompt="global",
                segment_prompts=["one", "", "three", "four"],
                strict_prompts=True,
            )

    def test_visual_rescale_721_to_241_keeps_four_segments(self):
        scaled, changed = nodes_module._scale_lengths_to_total([181, 180, 180, 180], 241)
        self.assertTrue(changed)
        self.assertEqual(scaled, [61, 60, 60, 60])
        first_four, starts, warnings = nodes_module._first_four_outputs(scaled)
        self.assertEqual(first_four, [61, 60, 60, 60])
        self.assertEqual(starts, [0, 61, 121, 181])
        self.assertEqual(warnings, [])

    def test_visual_first_four_outputs_warn_for_extra_segments(self):
        first_four, starts, warnings = nodes_module._first_four_outputs([10, 20, 30, 40, 50])
        self.assertEqual(first_four, [10, 20, 30, 40])
        self.assertEqual(starts, [0, 10, 30, 60])
        self.assertTrue(any("first 4" in warning for warning in warnings))


if __name__ == "__main__":
    unittest.main()
