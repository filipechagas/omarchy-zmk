import unittest

from bridge.zmkstatus import protocol


def status_bytes(**overrides):
    fields = {
        "version": 1,
        "layer": 3,
        "mask": (1 << 0) | (1 << 3),
        "profile": 2,
        "flags": protocol.FLAG_RIGHT_CONNECTED | protocol.FLAG_CAPS_WORD_SUPPORTED,
        "left": 93,
        "right": 71,
    }
    fields.update(overrides)
    return (
        bytes([fields["version"], fields["layer"]])
        + int(fields["mask"]).to_bytes(4, "little")
        + bytes([fields["profile"], fields["flags"], fields["left"], fields["right"]])
    )


class DecodeStatusTest(unittest.TestCase):
    def test_decodes_all_fields(self):
        status = protocol.decode_status(status_bytes())
        self.assertEqual(status["version"], 1)
        self.assertEqual(status["layer"], 3)
        self.assertEqual(status["layerMask"], 9)
        self.assertEqual(status["activeLayers"], [0, 3])
        self.assertEqual(status["profile"], 2)
        self.assertTrue(status["rightConnected"])
        self.assertTrue(status["capsWordSupported"])
        self.assertFalse(status["capsWord"])
        self.assertEqual(status["leftBattery"], 93)
        self.assertEqual(status["rightBattery"], 71)

    def test_mask_is_little_endian_and_reaches_bit_31(self):
        status = protocol.decode_status(status_bytes(mask=0x80000002))
        self.assertEqual(status["activeLayers"], [1, 31])

    def test_accepts_dbus_style_int_list(self):
        status = protocol.decode_status(list(status_bytes()))
        self.assertEqual(status["layer"], 3)

    def test_unknown_battery_is_none(self):
        status = protocol.decode_status(status_bytes(left=0xFF, right=101))
        self.assertIsNone(status["leftBattery"])
        self.assertIsNone(status["rightBattery"])

    def test_caps_word_is_none_when_unsupported(self):
        status = protocol.decode_status(status_bytes(flags=protocol.FLAG_CAPS_WORD))
        self.assertFalse(status["capsWordSupported"])
        self.assertIsNone(status["capsWord"])
        self.assertFalse(status["rightConnected"])

    def test_caps_word_active(self):
        flags = protocol.FLAG_CAPS_WORD | protocol.FLAG_CAPS_WORD_SUPPORTED
        self.assertTrue(protocol.decode_status(status_bytes(flags=flags))["capsWord"])

    def test_out_of_range_profile_is_none(self):
        self.assertIsNone(protocol.decode_status(status_bytes(profile=9))["profile"])

    def test_rejects_other_versions_before_length(self):
        with self.assertRaises(protocol.StatusError) as caught:
            protocol.decode_status(bytes([2, 0, 0]))
        self.assertEqual(caught.exception.code, "unsupported_version")

    def test_rejects_short_payload(self):
        with self.assertRaises(protocol.StatusError) as caught:
            protocol.decode_status(status_bytes()[:9])
        self.assertEqual(caught.exception.code, "short_payload")

    def test_rejects_empty_payload(self):
        for payload in (b"", None, []):
            with self.assertRaises(protocol.StatusError) as caught:
                protocol.decode_status(payload)
            self.assertEqual(caught.exception.code, "empty")

    def test_ignores_trailing_bytes(self):
        status = protocol.decode_status(status_bytes() + b"\x01\x02")
        self.assertEqual(status["rightBattery"], 71)


class OtherCharacteristicsTest(unittest.TestCase):
    def test_firmware_sha(self):
        self.assertEqual(protocol.decode_firmware(b"07f8bdb\x00\x00"), "07f8bdb")
        self.assertEqual(protocol.decode_firmware(list(b"  abc123\n")), "abc123")
        self.assertIsNone(protocol.decode_firmware(b""))
        self.assertEqual(len(protocol.decode_firmware(b"a" * 200)), protocol.MAX_FIRMWARE_CHARS)

    def test_firmware_invalid_utf8_is_replaced_not_raised(self):
        self.assertTrue(protocol.decode_firmware(b"\xffab"))

    def test_battery_level(self):
        self.assertEqual(protocol.decode_battery_level([0x5D]), 93)
        self.assertIsNone(protocol.decode_battery_level([]))
        self.assertIsNone(protocol.decode_battery_level([0xFF]))

    def test_cpf_description_from_real_main_bas(self):
        # Bytes read from a stock ZMK Corne's Battery Level CPF descriptor.
        raw = [0x04, 0x00, 0xAD, 0x27, 0x01, 0x06, 0x01]
        self.assertEqual(protocol.decode_cpf_description(raw), protocol.CPF_DESCRIPTION_MAIN)
        self.assertIsNone(protocol.decode_cpf_description([0x04]))

    def test_peripheral_cud(self):
        self.assertEqual(protocol.peripheral_index(protocol.decode_cud(b"Peripheral 0")), 0)
        self.assertEqual(protocol.peripheral_index("peripheral 2 "), 2)
        self.assertIsNone(protocol.peripheral_index("Battery"))
        self.assertIsNone(protocol.peripheral_index(None))


if __name__ == "__main__":
    unittest.main()
