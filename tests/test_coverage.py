import unittest
from scraper.coverage import CoveragePlanner


class CoverageTests(unittest.TestCase):
    def test_center_first_without_history(self):
        planner = CoveragePlanner(3.5, 9)
        cells = planner.plan(-23.55, -46.63)
        self.assertEqual(cells[0].ring, 0)

    def test_less_scanned_first(self):
        planner = CoveragePlanner(3.5, 9)
        cells = planner.all_cells(-23.55, -46.63)
        history = {cells[0].key: 5}
        planned = planner.plan(-23.55, -46.63, history)
        self.assertNotEqual(planned[0].key, cells[0].key)


if __name__ == "__main__":
    unittest.main()
