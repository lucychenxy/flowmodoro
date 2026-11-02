import unittest

from flowmo.app import heatmap_intensity


class HeatmapIntensityTests(unittest.TestCase):
    def test_heatmap_reaches_maximum_at_eight_hours(self) -> None:
        self.assertEqual(heatmap_intensity(0), 0.0)
        self.assertEqual(heatmap_intensity(4 * 60 * 60), 0.5)
        self.assertEqual(heatmap_intensity(8 * 60 * 60), 1.0)

    def test_heatmap_is_capped_after_eight_hours(self) -> None:
        self.assertEqual(heatmap_intensity(9 * 60 * 60), 1.0)
        self.assertEqual(heatmap_intensity(24 * 60 * 60), 1.0)


if __name__ == "__main__":
    unittest.main()
