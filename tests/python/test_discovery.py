import copy
import unittest

from bridge.zmkstatus import discovery, protocol
from tests.python.fixtures import bluez_objects as fx


class SelectKeyboardTest(unittest.TestCase):
    def test_old_firmware_falls_back_to_keyboard_icon_with_battery(self):
        selection = discovery.select_keyboard(fx.old_firmware())
        self.assertEqual(selection["path"], fx.KEYBOARD)
        self.assertEqual(selection["name"], "Corne")
        self.assertEqual(selection["source"], discovery.SOURCE_KEYBOARD_FALLBACK)
        self.assertTrue(selection["connected"])

    def test_custom_service_wins(self):
        objects = fx.new_firmware()
        objects[fx.OTHER_KEYBOARD] = fx.device("Office keyboard", battery=80)
        selection = discovery.select_keyboard(objects)
        self.assertEqual(selection["path"], fx.KEYBOARD)
        self.assertEqual(selection["source"], discovery.SOURCE_CUSTOM_SERVICE)

    def test_device_name_beats_icon_fallback(self):
        objects = fx.old_firmware()
        objects[fx.OTHER_KEYBOARD] = fx.device("Zebra", icon="input-gaming")
        selection = discovery.select_keyboard(objects, "zebra")
        self.assertEqual(selection["path"], fx.OTHER_KEYBOARD)
        self.assertEqual(selection["source"], discovery.SOURCE_DEVICE_NAME)

    def test_device_name_disambiguates_icon_fallback(self):
        objects = fx.old_firmware()
        objects[fx.OTHER_KEYBOARD] = fx.device("Alpha", battery=40)
        self.assertEqual(discovery.select_keyboard(objects)["path"], fx.KEYBOARD)
        self.assertEqual(discovery.select_keyboard(objects)["candidates"], 2)

    def test_keyboard_without_battery_is_not_a_fallback(self):
        objects = fx.old_firmware()
        del objects[fx.KEYBOARD]["org.bluez.Battery1"]
        self.assertIsNone(discovery.select_keyboard(objects))

    def test_disconnected_paired_keyboard_is_reported(self):
        selection = discovery.select_keyboard(fx.old_firmware(connected=False))
        self.assertEqual(selection["path"], fx.KEYBOARD)
        self.assertFalse(selection["connected"])

    def test_connected_wins_over_disconnected_named(self):
        objects = fx.old_firmware()
        objects[fx.OTHER_KEYBOARD] = fx.device("Wanted", connected=False)
        selection = discovery.select_keyboard(objects, "Wanted")
        self.assertEqual(selection["path"], fx.KEYBOARD)

    def test_nothing(self):
        self.assertIsNone(discovery.select_keyboard({fx.ADAPTER: {"org.bluez.Adapter1": {"Powered": False}}}))

    def test_adapter_state(self):
        self.assertEqual(discovery.adapter_state(fx.old_firmware()), {"present": True, "powered": True})
        self.assertEqual(discovery.adapter_state({}), {"present": False, "powered": False})


class GattLayoutTest(unittest.TestCase):
    def test_old_firmware_layout(self):
        layout = discovery.gatt_layout(fx.old_firmware(), fx.KEYBOARD)
        self.assertIsNone(layout["status"])
        self.assertIsNone(layout["firmware"])
        self.assertEqual(
            layout["bas"],
            [{"char": fx.KEYBOARD + "/service0010/char0011", "cud": None, "cpf": fx.KEYBOARD + "/service0010/char0011/desc0014"}],
        )

    def test_new_firmware_layout(self):
        layout = discovery.gatt_layout(fx.new_firmware(), fx.KEYBOARD)
        self.assertEqual(layout["status"], fx.KEYBOARD + "/service0030/char0031")
        self.assertEqual(layout["firmware"], fx.KEYBOARD + "/service0030/char0034")
        self.assertEqual(len(layout["bas"]), 2)
        self.assertEqual(layout["bas"][1]["cud"], fx.KEYBOARD + "/service0040/char0041/desc0045")

    def test_battery1(self):
        self.assertEqual(discovery.battery1_percent(fx.old_firmware(), fx.KEYBOARD), 93)
        self.assertIsNone(discovery.battery1_percent(fx.old_firmware(), fx.ADAPTER))

    def test_ignores_grandchildren_of_other_devices(self):
        objects = copy.deepcopy(fx.new_firmware())
        objects[fx.HEADPHONES + "/service0030"] = fx.service(protocol.SERVICE_UUID)
        layout = discovery.gatt_layout(objects, fx.KEYBOARD)
        self.assertEqual(layout["status"], fx.KEYBOARD + "/service0030/char0031")


class ClassifyBasTest(unittest.TestCase):
    def test_single_main_bas_is_left(self):
        halves = discovery.classify_bas([{"char": "a", "cud": None, "cpf": protocol.CPF_DESCRIPTION_MAIN}])
        self.assertEqual(halves, {"left": "a", "right": None})

    def test_without_descriptors_first_is_left(self):
        halves = discovery.classify_bas([{"char": "a", "cud": None, "cpf": None}])
        self.assertEqual(halves, {"left": "a", "right": None})

    def test_zmk_proxy_is_right(self):
        halves = discovery.classify_bas([
            {"char": "a", "cud": None, "cpf": protocol.CPF_DESCRIPTION_MAIN},
            {"char": "b", "cud": "Peripheral 0", "cpf": protocol.CPF_DESCRIPTION_AUXILIARY},
        ])
        self.assertEqual(halves, {"left": "a", "right": "b"})

    def test_auxiliary_cpf_alone_marks_right(self):
        halves = discovery.classify_bas([
            {"char": "b", "cud": None, "cpf": protocol.CPF_DESCRIPTION_AUXILIARY},
            {"char": "a", "cud": None, "cpf": None},
        ])
        self.assertEqual(halves, {"left": "a", "right": "b"})

    def test_lowest_peripheral_index_is_right(self):
        halves = discovery.classify_bas([
            {"char": "p1", "cud": "Peripheral 1", "cpf": None},
            {"char": "p0", "cud": "Peripheral 0", "cpf": None},
            {"char": "main", "cud": None, "cpf": None},
        ])
        self.assertEqual(halves, {"left": "main", "right": "p0"})


if __name__ == "__main__":
    unittest.main()
