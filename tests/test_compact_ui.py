import importlib.util
import pathlib
import unittest


MODULE_PATH = (
    pathlib.Path(__file__).resolve().parents[1]
    / "src"
    / "image_occlusion_enhanced"
    / "compact_ui.py"
)
SPEC = importlib.util.spec_from_file_location("compact_ui", MODULE_PATH)
compact_ui = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(compact_ui)


class CompactUiTests(unittest.TestCase):
    def test_compact_labels_are_exact(self):
        self.assertEqual(compact_ui.TAB_LABELS, ("1", "2"))
        self.assertEqual(compact_ui.TAB_NAMES, ("Default", "Fields"))
        self.assertEqual(
            compact_ui.ADD_BUTTON_LABELS, ("Hide All", "Hide One", "X")
        )

    def test_front_editor_uses_natural_height_below_cap(self):
        self.assertEqual(compact_ui.bounded_default_editor_height(96, 800), 96)

    def test_front_editor_is_capped_at_thirty_percent(self):
        self.assertEqual(compact_ui.bounded_default_editor_height(500, 800), 240)

    def test_front_editor_height_never_reaches_zero(self):
        self.assertEqual(compact_ui.bounded_default_editor_height(0, 0), 1)


if __name__ == "__main__":
    unittest.main()
