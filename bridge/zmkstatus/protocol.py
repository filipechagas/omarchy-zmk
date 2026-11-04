"""Wire contract between ZMK firmware and the bridge.

The keyboard exposes a custom GATT service with a 10-byte status
characteristic and a firmware-revision characteristic. Battery levels also
arrive through the standard Battery Service (0x180F / 0x2A19).
"""

import re

SERVICE_UUID = "7a6f0001-2c1e-4b8a-9d33-5e4c0f1a9b20"
STATUS_UUID = "7a6f0002-2c1e-4b8a-9d33-5e4c0f1a9b20"
FIRMWARE_UUID = "7a6f0003-2c1e-4b8a-9d33-5e4c0f1a9b20"

BAS_UUID = "0000180f-0000-1000-8000-00805f9b34fb"
BATTERY_LEVEL_UUID = "00002a19-0000-1000-8000-00805f9b34fb"
CUD_UUID = "00002901-0000-1000-8000-00805f9b34fb"
CPF_UUID = "00002904-0000-1000-8000-00805f9b34fb"

# Characteristic Presentation Format "description" values from the Bluetooth
# SIG namespace. Zephyr's BAS uses "main"; ZMK's split battery proxy uses
# "auxiliary" (zmk/app/src/split/bluetooth/central_bas_proxy.c).
CPF_DESCRIPTION_MAIN = 0x0106
CPF_DESCRIPTION_AUXILIARY = 0x0108

STATUS_VERSION = 1
STATUS_LENGTH = 10
MAX_BLE_PROFILE = 4

FLAG_RIGHT_CONNECTED = 0x01
FLAG_CAPS_WORD = 0x02
FLAG_CAPS_WORD_SUPPORTED = 0x04

BATTERY_UNKNOWN = 0xFF
MAX_FIRMWARE_CHARS = 64

_PERIPHERAL_CUD = re.compile(r"^\s*peripheral\s+(\d+)\s*$", re.IGNORECASE)


class StatusError(ValueError):
    """Raised when a status payload cannot be trusted."""

    def __init__(self, code, detail=""):
        super().__init__(code if not detail else "%s: %s" % (code, detail))
        self.code = code
        self.detail = detail


def to_bytes(value):
    """Convert a D-Bus byte array (or any iterable of ints) to bytes."""
    if value is None:
        return b""
    if isinstance(value, (bytes, bytearray)):
        return bytes(value)
    try:
        return bytes(int(item) & 0xFF for item in value)
    except (TypeError, ValueError):
        return b""


def battery_percent(raw):
    """Return 0..100 or None for unknown/out-of-range values."""
    if raw is None:
        return None
    try:
        value = int(raw)
    except (TypeError, ValueError):
        return None
    if value == BATTERY_UNKNOWN or value < 0 or value > 100:
        return None
    return value


def decode_status(data):
    """Decode the 10-byte status characteristic.

    Raises StatusError with code "empty", "unsupported_version", or
    "short_payload". Extra trailing bytes are ignored so a later minor
    revision can append fields without breaking version-1 readers.
    """
    payload = to_bytes(data)
    if len(payload) == 0:
        raise StatusError("empty")
    version = payload[0]
    if version != STATUS_VERSION:
        raise StatusError("unsupported_version", str(version))
    if len(payload) < STATUS_LENGTH:
        raise StatusError("short_payload", "%d bytes" % len(payload))

    layer = payload[1]
    mask = int.from_bytes(payload[2:6], "little")
    profile = payload[6]
    flags = payload[7]
    active_layers = [index for index in range(32) if mask & (1 << index)]
    caps_supported = bool(flags & FLAG_CAPS_WORD_SUPPORTED)

    return {
        "version": version,
        "layer": layer,
        "layerMask": mask,
        "activeLayers": active_layers,
        "profile": profile if profile <= MAX_BLE_PROFILE else None,
        "rightConnected": bool(flags & FLAG_RIGHT_CONNECTED),
        "capsWordSupported": caps_supported,
        "capsWord": bool(flags & FLAG_CAPS_WORD) if caps_supported else None,
        "leftBattery": battery_percent(payload[8]),
        "rightBattery": battery_percent(payload[9]),
    }


def decode_firmware(data):
    """Decode the firmware characteristic into a short printable string."""
    payload = to_bytes(data)
    text = payload.split(b"\x00", 1)[0].decode("utf-8", errors="replace")
    text = "".join(ch for ch in text if ch.isprintable()).strip()
    if not text:
        return None
    return text[:MAX_FIRMWARE_CHARS]


def decode_battery_level(data):
    payload = to_bytes(data)
    if not payload:
        return None
    return battery_percent(payload[0])


def decode_cpf_description(data):
    """Return the 16-bit description field of a CPF descriptor, or None."""
    payload = to_bytes(data)
    if len(payload) < 7:
        return None
    return int.from_bytes(payload[5:7], "little")


def decode_cud(data):
    payload = to_bytes(data)
    text = payload.split(b"\x00", 1)[0].decode("utf-8", errors="replace").strip()
    return text or None


def peripheral_index(cud):
    """Parse ZMK's "Peripheral N" user description; None if absent."""
    if not cud:
        return None
    match = _PERIPHERAL_CUD.match(cud)
    return int(match.group(1)) if match else None
