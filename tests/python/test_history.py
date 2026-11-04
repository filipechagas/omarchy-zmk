import unittest

from bridge.zmkstatus import history


class BatteryHistoryTest(unittest.TestCase):
    def test_steady_drain_slope(self):
        h = history.BatteryHistory(min_interval=0)
        for minute in range(0, 121, 10):
            h.add(minute * 60, 90 - minute // 30)
        trend = h.trend(120 * 60)
        self.assertAlmostEqual(trend["perHour"], -2.0, delta=0.3)
        self.assertEqual(trend["spanMinutes"], 120)

    def test_needs_span_before_slope(self):
        h = history.BatteryHistory(min_interval=0)
        h.add(0, 90)
        h.add(60, 89)
        h.add(120, 88)
        trend = h.trend(120)
        self.assertIsNone(trend["perHour"])
        self.assertEqual(trend["samples"], 3)

    def test_unchanged_readings_are_rate_limited(self):
        h = history.BatteryHistory(min_interval=300)
        self.assertTrue(h.add(0, 90))
        self.assertFalse(h.add(10, 90))
        self.assertTrue(h.add(20, 89))
        self.assertTrue(h.add(400, 89))
        self.assertFalse(h.add(399, 88))  # clock went backwards
        self.assertFalse(h.add(500, None))

    def test_old_samples_expire(self):
        h = history.BatteryHistory(max_age=100, min_interval=0)
        h.add(0, 90)
        h.add(150, 80)
        self.assertEqual(h.samples, [(150.0, 80)])

    def test_seed_ignores_zero_and_out_of_range(self):
        # UPower returned (time, 0.0, state) rows for a real Corne.
        h = history.BatteryHistory()
        count = h.seed([(1000, 0.0), (2000, 95.4), (3000, 140), (2500, None)], "upower")
        self.assertEqual(count, 1)
        self.assertEqual(h.samples, [(2000.0, 95)])
        self.assertEqual(h.trend(3000)["source"], "upower")
        self.assertEqual(history.BatteryHistory().seed([(1, 0.0)], "upower"), 0)

    def test_points_are_downsampled(self):
        h = history.BatteryHistory(min_interval=0)
        for i in range(100):
            h.add(i, 100 - i % 50)
        points = h.trend(100)["points"]
        self.assertEqual(len(points), history.SPARK_POINTS)
        self.assertEqual(points[-1], h.samples[-1][1])

    def test_empty(self):
        trend = history.BatteryHistory().trend(0)
        self.assertEqual(trend["samples"], 0)
        self.assertIsNone(trend["perHour"])


if __name__ == "__main__":
    unittest.main()
