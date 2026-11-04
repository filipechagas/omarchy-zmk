import unittest

from bridge.zmkstatus import alerts


def run(levels, half="left"):
    tracker = alerts.BatteryAlerts()
    fired = []
    for level in levels:
        alert = tracker.update(half, level)
        if alert:
            fired.append(alert["threshold"])
    return fired


class BatteryAlertsTest(unittest.TestCase):
    def test_each_threshold_once_on_the_way_down(self):
        self.assertEqual(run(range(100, -1, -1)), [20, 10, 5])

    def test_wobble_at_threshold_does_not_repeat(self):
        self.assertEqual(run([22, 21, 20, 21, 20, 22, 20, 19]), [20])

    def test_rearms_after_charging_past_margin(self):
        self.assertEqual(run([21, 20, 23, 20]), [20, 20])

    def test_big_drop_reports_lowest_threshold_once(self):
        self.assertEqual(run([50, 4, 3, 2]), [5])

    def test_first_reading_already_low(self):
        self.assertEqual(run([15, 14]), [20])

    def test_unknown_readings_are_ignored(self):
        self.assertEqual(run([None, 25, None, 20, None]), [20])

    def test_halves_are_independent(self):
        tracker = alerts.BatteryAlerts()
        self.assertEqual(tracker.update("left", 19)["half"], "left")
        self.assertEqual(tracker.update("right", 19)["half"], "right")
        self.assertIsNone(tracker.update("left", 18))

    def test_alert_payload(self):
        alert = alerts.BatteryAlerts().update("right", 9)
        self.assertEqual(alert, {"kind": "battery_low", "half": "right", "threshold": 10, "percent": 9})


class RightDisconnectWatchTest(unittest.TestCase):
    def test_fires_once_after_delay(self):
        watch = alerts.RightDisconnectWatch(delay=60)
        self.assertIsNone(watch.update(0, True, False))
        self.assertIsNone(watch.update(59, True, False))
        alert = watch.update(60, True, False)
        self.assertEqual(alert["kind"], "right_disconnected")
        self.assertEqual(alert["seconds"], 60)
        self.assertIsNone(watch.update(500, True, False))

    def test_reconnect_resets(self):
        watch = alerts.RightDisconnectWatch(delay=60)
        watch.update(0, True, False)
        watch.update(30, True, True)
        self.assertIsNone(watch.update(70, True, False))
        self.assertIsNotNone(watch.update(130, True, False))

    def test_rearms_after_reconnect_following_alert(self):
        watch = alerts.RightDisconnectWatch(delay=60)
        watch.update(0, True, False)
        self.assertIsNotNone(watch.update(61, True, False))
        watch.update(62, True, True)
        watch.update(100, True, False)
        self.assertIsNotNone(watch.update(160, True, False))

    def test_keyboard_disconnect_or_unknown_state_never_fires(self):
        watch = alerts.RightDisconnectWatch(delay=60)
        self.assertIsNone(watch.update(0, False, False))
        self.assertIsNone(watch.update(100, False, False))
        self.assertIsNone(watch.update(200, True, None))
        self.assertIsNone(watch.update(400, True, None))
        self.assertIsNone(watch.disconnected_since)


if __name__ == "__main__":
    unittest.main()
