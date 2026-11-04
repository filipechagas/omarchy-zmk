import unittest

from bridge.zmkstatus import alerts, discovery, state
from tests.python.fixtures import bluez_objects as fx
from tests.python.test_protocol import status_bytes
from bridge.zmkstatus import protocol


def connected_state(objects=None):
    objects = objects or fx.old_firmware()
    selection = discovery.select_keyboard(objects)
    layout = discovery.gatt_layout(objects, selection["path"])
    s = state.KeyboardState()
    s.set_device(selection, custom_service=layout["status"] is not None)
    s.set_battery1(discovery.battery1_percent(objects, selection["path"]))
    return s


class OldFirmwareTest(unittest.TestCase):
    def test_left_from_battery1_then_bas(self):
        s = connected_state()
        snap = s.snapshot(0)
        self.assertEqual(snap["left"]["percent"], 93)
        self.assertEqual(snap["left"]["source"], "battery1")
        self.assertIsNone(snap["right"]["percent"])
        self.assertIsNone(snap["right"]["connected"])
        self.assertIsNone(snap["status"])
        self.assertFalse(snap["features"]["customService"])
        self.assertEqual(snap["device"]["source"], "keyboard-fallback")

        s.set_bas("left", [92])
        self.assertEqual(s.snapshot(0)["left"], {"percent": 92, "source": "bas", "trend": s.histories["left"].trend(0)})

    def test_no_disconnect_alert_without_status(self):
        s = connected_state()
        for t in range(0, 600, 5):
            self.assertEqual([a for a in s.observe(t, t) if a["kind"] == "right_disconnected"], [])


class NewFirmwareTest(unittest.TestCase):
    def setUp(self):
        self.s = connected_state(fx.new_firmware())

    def test_status_wins_over_bas(self):
        self.s.set_bas("left", [50])
        self.s.set_bas("right", [40])
        self.s.set_status_bytes(status_bytes(left=93, right=71))
        snap = self.s.snapshot(0)
        self.assertTrue(snap["features"]["customService"])
        self.assertEqual((snap["left"]["percent"], snap["left"]["source"]), (93, "status"))
        self.assertEqual((snap["right"]["percent"], snap["right"]["source"]), (71, "status"))
        self.assertEqual(snap["status"]["layer"], 3)

    def test_unknown_status_battery_falls_back_to_bas(self):
        self.s.set_bas("right", [40])
        self.s.set_status_bytes(status_bytes(right=0xFF))
        self.assertEqual(self.s.snapshot(0)["right"]["source"], "bas")

    def test_right_bas_zero_means_no_reading(self):
        self.s.set_bas("right", [0])
        self.assertIsNone(self.s.snapshot(0)["right"]["percent"])
        self.assertEqual(self.s.observe(0, 0), [])
        self.s.set_bas("left", [0])
        self.assertEqual(self.s.snapshot(0)["left"]["percent"], 0)

    def test_bad_payload_is_reported(self):
        self.s.set_status_bytes(status_bytes(version=7))
        snap = self.s.snapshot(0)
        self.assertIsNone(snap["status"])
        self.assertEqual(snap["statusError"], "unsupported_version")

    def test_low_battery_alerts_carry_device_name(self):
        self.s.set_status_bytes(status_bytes(left=19, right=71))
        raised = self.s.observe(0, 0)
        self.assertEqual(raised, [{"kind": "battery_low", "half": "left", "threshold": 20, "percent": 19, "device": "Corne"}])
        self.assertEqual(self.s.observe(10, 10), [])

    def test_right_disconnected_for_a_minute(self):
        self.s.set_status_bytes(status_bytes(flags=0, right=5))
        self.assertEqual(self.s.observe(1000, 0), [])  # stale right value does not alert
        snap = self.s.snapshot(1000)
        self.assertFalse(snap["right"]["connected"])
        self.assertEqual(snap["right"]["disconnectedSince"], 1000)
        raised = self.s.observe(1060, alerts.RIGHT_DISCONNECT_DELAY)
        self.assertEqual([a["kind"] for a in raised], ["right_disconnected"])
        self.s.set_status_bytes(status_bytes())
        self.s.observe(1070, 70)
        self.assertIsNone(self.s.snapshot(1070)["right"]["disconnectedSince"])

    def test_disconnect_clears_readings(self):
        self.s.set_status_bytes(status_bytes())
        self.s.set_firmware_bytes(b"abc1234")
        selection = discovery.select_keyboard(fx.old_firmware(connected=False))
        self.s.set_device(selection)
        snap = self.s.snapshot(0)
        self.assertFalse(snap["device"]["connected"])
        self.assertIsNone(snap["status"])
        self.assertIsNone(snap["firmware"])
        self.assertIsNone(snap["left"]["percent"])
        self.assertEqual(self.s.observe(0, 0), [])

    def test_firmware(self):
        self.s.set_firmware_bytes(b"07f8bdb")
        self.assertEqual(self.s.snapshot(0)["firmware"], "07f8bdb")
        self.assertTrue(self.s.snapshot(0)["features"]["firmware"])

    def test_no_device(self):
        s = state.KeyboardState()
        s.set_device(None)
        snap = s.snapshot(0)
        self.assertIsNone(snap["device"])
        self.assertEqual(snap["v"], 1)
        self.assertEqual(snap["type"], "state")


class StatusFlagsTest(unittest.TestCase):
    def test_caps_word(self):
        s = connected_state(fx.new_firmware())
        s.set_status_bytes(status_bytes(flags=protocol.FLAG_CAPS_WORD | protocol.FLAG_CAPS_WORD_SUPPORTED | 1))
        self.assertTrue(s.snapshot(0)["status"]["capsWord"])


if __name__ == "__main__":
    unittest.main()
